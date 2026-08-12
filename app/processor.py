import json
import logging
import re
import time
from pathlib import Path

from . import DATA_DIR
from .config import Settings
from .models import WebhookPayload
from .postprocess import clean_transcript
from .title_generator import TitleGenerator
from .transcriber import Transcriber
from .zammad import ZammadClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Normalisation numéros français (local ↔ international)
# ──────────────────────────────────────────────────────────────

# Indicatifs français valides (métropole + DOM/TOM)
_FR_PREFIXES = (
    "1", "2", "3", "4", "5",  # métropole
    "6", "7",                 # mobile
    "9",                      # VOIP / numéros spéciaux
    "590", "594", "596", "262", "269", "681", "689",  # DOM/TOM
)

def _normalize_french_phone(raw: str) -> str | None:
    """
    Normalise un numéro français en format E.164 (+33XXXXXXXXX).
    Retourne None si invalide.
    Gère :
    - local 0XXXXXXXXX → +33XXXXXXXXX
    - international +33XXXXXXXXX (déjà ok)
    - correction zéro en trop : +3302... → +332...
    - formats avec espaces, points, tirets, parenthèses
    """
    if not raw:
        return None

    # Nettoyage : garder seulement + et chiffres
    cleaned = re.sub(r"[^\d+]", "", raw)

    # Déjà international ?
    if cleaned.startswith("+33"):
        # Correction zéro en trop : +330X... → +33X...
        # Ex: +330243404040 → +33243404040 (le 0 après +33 est en trop)
        if len(cleaned) > 4 and cleaned[3] == "0":
            rest = cleaned[4:]  # partie après +330
            for prefix in _FR_PREFIXES:
                if rest.startswith(prefix):
                    return "+33" + rest  # retire le 0 en trop, garde le reste complet
        return cleaned

    # Format local 0XXXXXXXXX (10 chiffres commençant par 0)
    if cleaned.startswith("0") and len(cleaned) == 10:
        return "+33" + cleaned[1:]

    # Format local sans le 0 initial (9 chiffres) - rare mais possible
    if len(cleaned) == 9 and cleaned[0] in "12345679":
        return "+33" + cleaned

    # Format international sans + (33XXXXXXXXX)
    if cleaned.startswith("33") and len(cleaned) == 11:
        rest = cleaned[2:]
        for prefix in _FR_PREFIXES:
            if rest.startswith(prefix):
                return "+" + cleaned

    return None


def _phone_variants(phone: str) -> set[str]:
    """Génère toutes les variantes plausibles pour la recherche."""
    norm = _normalize_french_phone(phone)
    if not norm:
        return set()

    variants = {norm}

    # Variante locale (sans +33, avec 0)
    if norm.startswith("+33"):
        local = "0" + norm[3:]
        variants.add(local)
        # Format avec espaces (0X XX XX XX XX)
        variants.add(" ".join([local[i:i+2] for i in range(0, 10, 2)]))
        # Format compact sans +
        variants.add(norm[1:])  # 33XXXXXXXXX

    # Variante internationale compacte
    if norm.startswith("+33"):
        variants.add(norm[1:])  # 33XXXXXXXXX
        variants.add("+" + norm[1:])  # +33XXXXXXXXX (déjà dans norm)

    return variants


# ──────────────────────────────────────────────────────────────
# Regex extraction téléphone 3CX
# ──────────────────────────────────────────────────────────────

PHONE_PATTERN = re.compile(r"De:\s*([+\d\s().-]{8,})", re.IGNORECASE)


MAX_RETRIES = 3
RETRY_BACKOFF = (10, 30, 60)


class Processor:
    def __init__(self, settings: Settings, state_dir: Path | None = None):
        self.settings = settings
        self.zammad = ZammadClient(settings)
        self.transcriber = Transcriber(settings)
        self.titles = TitleGenerator(settings)
        self.state_dir = state_dir or (DATA_DIR / "state")

    def process(self, payload: WebhookPayload) -> dict:
        ticket_id = payload.ticket.id
        article = payload.article
        article_id = article.id
        done, _marker = self._load_state(ticket_id, article_id)
        if done:
            logger.info("Ticket %s déjà traité — idempotence.", ticket_id)
            return {"idempotent": True}

        audio = self._find_audio_attachment(payload)
        if audio is None or not (audio.url or ""):
            self._mark_done(ticket_id, article_id, {"status": "no_audio"})
            logger.warning("Ticket %s sans attachment audio.", ticket_id)
            return {"status": "no_audio"}

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = self._run_pipeline(ticket_id, article_id, payload, audio.url)
                self._mark_done(ticket_id, article_id, result)
                logger.info("Ticket %s traité avec succès.", ticket_id)
                return result
            except Exception as exc:
                logger.error(
                    "Tentative %s/%s échouée pour le ticket %s : %s",
                    attempt,
                    MAX_RETRIES,
                    ticket_id,
                    exc,
                )
                if attempt == MAX_RETRIES:
                    self._mark_failed(ticket_id, article_id, str(exc))
                    raise
                time.sleep(RETRY_BACKOFF[attempt - 1])

    def _run_pipeline(
        self, ticket_id: int, article_id: int | None, payload: WebhookPayload, audio_url: str
    ) -> dict:
        audio_bytes = self.zammad.get_attachment(audio_url)
        transcript = self.transcriber.transcribe(audio_bytes)
        transcript = clean_transcript(transcript)
        if not transcript:
            raise RuntimeError("Transcription vide après nettoyage.")

        meta = self.titles.generate(transcript)

        customer_id = self._resolve_customer(payload, meta.get("customer_name"))
        self.zammad.update_ticket(
            ticket_id,
            {
                "title": meta["title"],
                **({"customer_id": customer_id} if customer_id else {}),
            },
        )
        article_payload = {
            "type": "note",
            "internal": False,
            "body": f"Transcription du message vocal :\n\n{transcript}",
        }
        if article_id is not None:
            article_payload["reply_to"] = article_id
        self.zammad.create_article(ticket_id, article_payload)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "article_id": article_id,
            "transcript": transcript,
            "title": meta["title"],
            "customer_id": customer_id,
            "customer_name": meta.get("customer_name"),
        }

    PHONE_PATTERN = re.compile(r"De:\s*([+\d\s().-]{8,})", re.IGNORECASE)

    def _extract_phone_from_3cx_email(self, body_html: str) -> str | None:
        """Extrait le numéro 'De: +33...' du corps HTML 3CX et retourne la version normalisée E.164."""
        text = re.sub(r"<[^>]+>", " ", body_html)
        text = re.sub(r"\s+", " ", text)
        match = self.PHONE_PATTERN.search(text)
        if match:
            raw = match.group(1)
            return _normalize_french_phone(raw)
        return None

    def _resolve_customer(self, payload: WebhookPayload, llm_name: str | None) -> int | None:
        customer = payload.ticket.customer or {}
        if customer.get("id"):
            return customer["id"]

        phone = self._extract_phone_from_3cx_email(payload.article.body or "")
        if phone:
            for variant in _phone_variants(phone):
                user = self.zammad.find_user_by_phone(variant)
                if user and user.get("id"):
                    logger.info("Client trouvé via téléphone %s (variante %s) : %s (ID: %s)",
                                phone, variant,
                                f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                                user["id"])
                    return user["id"]
            logger.info("Aucun client trouvé pour le téléphone %s (variantes testées: %s)",
                        phone, _phone_variants(phone))

        if llm_name:
            user = self.zammad.find_user_by_name(llm_name)
            if user and user.get("id"):
                logger.info("Client trouvé dans Zammad : %s (ID: %s)", llm_name, user["id"])
                return user["id"]

            try:
                parts = llm_name.split(" ", 1)
                firstname = parts[0]
                lastname = parts[1] if len(parts) > 1 else ""
                new_user = self.zammad.create_user(firstname, lastname)
                logger.info("Client créé dans Zammad : %s (ID: %s)", llm_name, new_user.get("id"))
                return new_user.get("id")
            except Exception as exc:
                logger.warning("Échec création client Zammad pour '%s' : %s", llm_name, exc)

        return None

    def _find_audio_attachment(self, payload: WebhookPayload):
        for attachment in payload.article.attachments or []:
            name = (attachment.filename or "").lower()
            if name.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                return attachment
        return None

    def _load_state(self, ticket_id: int, article_id: int | None):
        path = self._state_path(ticket_id, article_id)
        if not path.is_file():
            return False, {}
        try:
            return True, json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return False, {}

    def _mark_done(self, ticket_id: int, article_id: int | None, data: dict) -> None:
        self._write_state(
            ticket_id, article_id, {**data, "finished_at": time.time(), "success": True}
        )

    def _mark_failed(self, ticket_id: int, article_id: int | None, error: str) -> None:
        self._write_state(
            ticket_id, article_id, {"error": error, "finished_at": time.time(), "success": False}
        )

    def _write_state(self, ticket_id: int, article_id: int | None, data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path(ticket_id, article_id).write_text(json.dumps(data, ensure_ascii=False))

    def _state_path(self, ticket_id: int, article_id: int | None) -> Path:
        key = f"{ticket_id}_{article_id or 'na'}"
        return self.state_dir / f"{key}.json"
