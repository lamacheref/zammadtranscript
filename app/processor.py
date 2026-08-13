import json
import logging
import re
import time
from pathlib import Path

from . import DATA_DIR
from .config import Settings
from .models import Attachment, WebhookPayload
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
    "1",
    "2",
    "3",
    "4",
    "5",  # métropole
    "6",
    "7",  # mobile
    "9",  # VOIP / numéros spéciaux
    "590",
    "594",
    "596",
    "262",
    "269",
    "681",
    "689",  # DOM/TOM
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
        variants.add(" ".join([local[i : i + 2] for i in range(0, 10, 2)]))
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

# Étapes du pipeline, visibles dans l'UI manuelle.
STEP_LABELS = {
    "ticket": "Recherche du ticket",
    "article": "Recherche de l'article contenant l'audio",
    "download": "Téléchargement de l'audio",
    "transcription": "Transcription",
}


def _step(steps: dict, progress, name: str, status: str, message=None, error=None) -> dict:
    entry = {
        "step": name,
        "label": STEP_LABELS.get(name, name),
        "status": status,
        "message": message,
        "error": error,
    }
    steps[name] = entry
    if progress:
        progress(name, dict(entry))
    return entry


class Processor:
    def __init__(self, settings: Settings, state_dir: Path | None = None):
        self.settings = settings
        self.zammad = ZammadClient(settings)
        self.transcriber = Transcriber(settings)
        self.titles = TitleGenerator(settings)
        self.state_dir = state_dir or (DATA_DIR / "state")

    def process(
        self,
        payload: WebhookPayload,
        progress=None,
        retries: bool = True,
        steps: dict | None = None,
    ) -> dict:
        steps = steps or {}
        ticket_id = payload.ticket.id
        article = payload.article
        article_id = article.id

        if "ticket" not in steps:
            _step(steps, progress, "ticket", "ok", message=f"Ticket #{ticket_id}")

        # Idempotence : si une vraie transcription existe déjà, la réutiliser.
        done, state = self._load_state(ticket_id, article_id)
        if done:
            if state.get("transcript"):
                logger.info("Ticket %s déjà transcrit — réutilisation du résultat.", ticket_id)
                _step(
                    steps,
                    progress,
                    "transcription",
                    "ok",
                    message="Transcription existante réutilisée",
                )
                return {**state, "idempotent": True, "steps": list(steps.values())}
            logger.info(
                "Ticket %s précédemment marqué '%s' sans transcription — retranscription.",
                ticket_id,
                state.get("status") or "traité",
            )

        audio = self._find_audio_attachment(payload)
        if audio is None or not (audio.url or ""):
            logger.warning("Ticket %s sans attachment audio.", ticket_id)
            _step(
                steps,
                progress,
                "article",
                "error",
                error="Aucun attachment audio trouvé dans le ticket",
            )
            self._mark_done(ticket_id, article_id, {"status": "no_audio"})
            return {"success": False, "steps": list(steps.values())}
        if "article" not in steps:
            _step(steps, progress, "article", "ok", message=audio.filename)
        else:
            # Déjà rapporté par le pipeline manuel : on met à jour sans re-notifier.
            steps["article"].update(status="ok", message=audio.filename, error=None)

        _step(steps, progress, "download", "running", message="Téléchargement de l'audio…")
        for attempt in range(1, MAX_RETRIES + 1):
            step_name = "download"
            try:
                audio_bytes = self.zammad.get_attachment(audio.url)
                _step(
                    steps,
                    progress,
                    "download",
                    "ok",
                    message=f"{len(audio_bytes)} octets téléchargés",
                )
                step_name = "transcription"
                result = self._run_pipeline(ticket_id, article_id, payload, audio_bytes)
                self._mark_done(ticket_id, article_id, result)
                logger.info("Ticket %s traité avec succès.", ticket_id)
                _step(steps, progress, "transcription", "ok", message="Transcription terminée")
                return {**result, "steps": list(steps.values())}
            except Exception as exc:
                logger.error(
                    "Tentative %s/%s échouée pour le ticket %s : %s",
                    attempt,
                    MAX_RETRIES,
                    ticket_id,
                    exc,
                )
                _step(steps, progress, step_name, "error", error=str(exc))
                if not retries or attempt == MAX_RETRIES:
                    self._mark_failed(ticket_id, article_id, str(exc))
                    return {"success": False, "steps": list(steps.values()), "error": str(exc)}
                _step(
                    steps,
                    progress,
                    step_name,
                    "running",
                    message=f"Nouvelle tentative ({attempt + 1}/{MAX_RETRIES})…",
                )
                time.sleep(RETRY_BACKOFF[attempt - 1])

    def prepare_manual(
        self,
        ticket_input: int | str,
        progress=None,
    ) -> dict:
        """Pipeline manuel de PRÉPARATION : aucune écriture dans Zammad.

        Retourne un brouillon (transcription, titre, client suggéré) que l'opérateur
        peut corriger puis valider via `commit_manual` (bouton « Ajouter au ticket »).
        """
        steps: dict = {}
        ticket = None
        try:
            ticket = self.zammad.get_ticket(int(ticket_input))
        except Exception:
            ticket = None
        if ticket is None:
            try:
                found = self.zammad.find_ticket_by_number(str(ticket_input))
                if found and found.get("id"):
                    ticket = found
            except Exception as exc:
                _step(
                    steps,
                    progress,
                    "ticket",
                    "error",
                    error=f"Recherche du ticket {ticket_input} impossible : {exc}",
                )
                return {"success": False, "draft": False, "steps": list(steps.values())}
        if ticket is None:
            _step(steps, progress, "ticket", "error", error=f"Ticket {ticket_input} introuvable")
            return {"success": False, "draft": False, "steps": list(steps.values())}

        ticket_id = int(ticket["id"])
        _step(steps, progress, "ticket", "ok", message=f"Ticket #{ticket_id}")

        audio, audio_article = self._find_audio_article(ticket_id, progress, steps)
        if audio is None:
            return {"success": False, "draft": False, "steps": list(steps.values())}

        _step(steps, progress, "download", "running", message="Téléchargement de l'audio…")
        try:
            audio_bytes = self.zammad.get_attachment(audio.url)
        except Exception as exc:
            _step(steps, progress, "download", "error", error=str(exc))
            return {"success": False, "draft": False, "steps": list(steps.values())}
        _step(steps, progress, "download", "ok", message=f"{len(audio_bytes)} octets téléchargés")

        try:
            transcript = self._transcribe_only(audio_bytes)
        except Exception as exc:
            _step(steps, progress, "transcription", "error", error=str(exc))
            return {"success": False, "draft": False, "steps": list(steps.values())}
        _step(steps, progress, "transcription", "ok", message="Transcription terminée")

        payload = WebhookPayload.model_validate(
            {
                "ticket": {
                    "id": ticket.get("id"),
                    "title": ticket.get("title"),
                    "customer_id": ticket.get("customer_id"),
                    "customer": ticket.get("customer")
                    or ({"id": ticket.get("customer_id")} if ticket.get("customer_id") else None),
                },
                "article": {"body": (audio_article or {}).get("body") or ""},
            }
        )
        plan = self._plan_analysis(payload, transcript)

        return {
            "success": True,
            "draft": True,
            "ticket_id": ticket_id,
            "article_id": (audio_article or {}).get("id"),
            "transcript": transcript,
            "title": plan["title"],
            "customer_id_suggestion": plan["customer_id"],
            "customer_suggestion": plan["customer_name"],
            "steps": list(steps.values()),
        }

    def commit_manual(
        self,
        ticket_id: int,
        article_id: int | None,
        transcript: str,
        title: str,
        customer_name: str | None = None,
        customer_id: int | None = None,
    ) -> dict:
        """Applique le brouillon validé par l'opérateur au ticket Zammad."""
        transcript = (transcript or "").strip()
        title = (title or "").strip()
        if not transcript:
            raise RuntimeError("Transcription vide.")
        title = title or "Message vocal transcrit"

        customer_resolved = None
        if customer_id:
            customer_resolved = int(customer_id)
        elif customer_name and customer_name.strip():
            customer_resolved = self._resolve_customer_name(customer_name.strip())

        update = {"title": title}
        if customer_resolved:
            update["customer_id"] = customer_resolved
        self.zammad.update_ticket(ticket_id, update)

        created = self._create_transcript_article(
            ticket_id,
            transcript,
            subject=title,
            reply_to=article_id,
        )
        created_id = created.get("id") if isinstance(created, dict) else None

        result = {
            "success": True,
            "ticket_id": ticket_id,
            "article_id": created_id or article_id,
            "transcript": transcript,
            "title": title,
            "customer_id": customer_resolved,
            "customer_name": customer_name or None,
        }
        self._mark_done(ticket_id, article_id, result)
        logger.info("Brouillon appliqué au ticket %s par l'opérateur.", ticket_id)
        return result

    def _create_transcript_article(
        self,
        ticket_id: int,
        body: str,
        *,
        subject: str | None = None,
        reply_to: int | None = None,
        internal: bool = False,
    ) -> dict:
        """Crée l'article de transcription dans Zammad (type note, sender Agent).

        Les champs sont explicites : `sender=Agent` (l'article est écrit par un
        opérateur, pas par le système) et `internal=False` pour qu'il soit visible
        du client. La réponse Zammad est vérifiée (attribut `id` attendu).
        """
        payload: dict = {
            "type": "note",
            "sender": "Agent",
            "content_type": "text/plain",
            "internal": internal,
            "body": body,
        }
        payload["body"] = (
            f"Transcription par ZammadTranscript - Attention à la qualité\n\n{body.strip()}"
        )
        if subject:
            payload["subject"] = subject
        if reply_to is not None:
            payload["reply_to"] = reply_to
        created = self.zammad.create_article(ticket_id, payload)
        created_id = created.get("id") if isinstance(created, dict) else None
        logger.info(
            "Article de transcription créé (ticket %s, type=note, sender=Agent, "
            "internal=%s, subject=%r, id=%s)",
            ticket_id,
            internal,
            subject,
            created_id,
        )
        if not created_id:
            logger.warning(
                "Zammad n'a pas renvoyé d'id pour l'article créé (ticket %s).",
                ticket_id,
            )
        return created

    def _resolve_customer_name(self, name: str) -> int | None:
        """Trouve un client Zammad par nom. JAMAIS de création : l'opérateur
        choisit un client existant (ou le crée lui-même dans Zammad)."""
        user = self.zammad.find_user_by_name(name)
        if user and user.get("id"):
            return user["id"]
        logger.info(
            "Client '%s' introuvable dans Zammad — aucun client créé (action de l'opérateur requise).",
            name,
        )
        return None

    def _find_audio_article(self, ticket_id: int, progress=None, steps: dict | None = None):
        """Cherche l'article contenant l'audio via l'API Zammad et construit l'URL."""
        try:
            articles = self.zammad.get_ticket_articles(ticket_id)
        except Exception as exc:
            _step(
                steps,
                progress,
                "article",
                "error",
                error=f"Impossible de lire les articles du ticket {ticket_id} : {exc}",
            )
            return None, None

        for article in articles or []:
            for att in article.get("attachments", []):
                name = (att.get("filename") or "").lower()
                if not name.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                    continue
                # L'API Zammad ne renvoie pas d'URL : la construire.
                if not (att.get("url") or ""):
                    att_id = att.get("id")
                    art_id = article.get("id")
                    if att_id and art_id:
                        base = self.settings.zammad_url.rstrip("/")
                        att = {
                            **att,
                            "url": f"{base}/api/v1/ticket_attachment/{ticket_id}/{art_id}/{att_id}",
                        }
                audio = Attachment.model_validate(att)
                _step(steps, progress, "article", "ok", message=att.get("filename"))
                return audio, article

        _step(
            steps,
            progress,
            "article",
            "error",
            error="Aucun attachment audio trouvé dans le ticket",
        )
        return None, None

    def _transcribe_only(self, audio_bytes: bytes) -> str:
        """Whisper uniquement (aucun appel Ollama). Retourne la transcription nettoyée."""
        transcript = self.transcriber.transcribe(audio_bytes)
        transcript = clean_transcript(transcript)
        if not transcript:
            raise RuntimeError("Transcription vide après nettoyage.")
        return transcript

    def _analyze_with_llm(self, transcript: str) -> dict:
        """Titre + client proposé via Ollama. N'est appelé QUE si aucun client
        n'est résolu par le ticket ou par la recherche téléphone (règle métier)."""
        return self.titles.generate(transcript)

    def _user_display_name(self, user: dict) -> str | None:
        name = f"{user.get('firstname') or ''} {user.get('lastname') or ''}".strip()
        return name or None

    def _plan_analysis(
        self, payload: WebhookPayload, transcript: str, article_body: str | None = None
    ) -> dict:
        """Décide titre + client du ticket.

        Règles métier :
        - le NUMÉRO 3CX du payload est recherché en priorité dans Zammad :
          s'il existe un client, utiliser CE client et ne pas demander le nom à
          Ollama ;
        - le TITRE est de toute façon généré par Ollama à partir de la
          transcription ;
        - sans téléphone → Ollama propose un nom de client, recherché dans
          Zammad : s'il est trouvé, il est proposé ; sinon il est juste indiqué
          à l'opérateur, absolument aucun client n'est créé.
        """
        meta = self._analyze_with_llm(transcript)
        body = article_body if article_body is not None else (payload.article.body or "")

        customer_id = None
        customer_name = None

        user = self._find_customer_by_phone(body)
        if user and user.get("id"):
            customer_id = user["id"]
            customer_name = self._user_display_name(user)
        else:
            existing = payload.ticket.customer or {}
            if existing.get("id"):
                customer_id = existing["id"]
                customer_name = self._user_display_name(existing)
            else:
                suggested = meta.get("customer_name")
                if suggested:
                    found = self.zammad.find_user_by_name(suggested)
                    if found and found.get("id"):
                        customer_id = found["id"]
                        customer_name = self._user_display_name(found)
                        logger.info(
                            "Client trouvé dans Zammad par nom : %s (ID: %s)",
                            suggested,
                            found["id"],
                        )
                    else:
                        customer_name = suggested
                        logger.info(
                            "Client proposé par Ollama '%s' introuvable dans Zammad — "
                            "nom indiqué à l'opérateur, AUCUN client créé.",
                            suggested,
                        )

        return {
            "title": meta["title"] or "Message vocal transcrit",
            "customer_id": customer_id,
            "customer_name": customer_name,
        }

    def _find_customer_by_phone(self, body: str) -> dict | None:
        """Cherche un client Zammad via le numéro 3CX ('De: +33…') dans le corps de l'article."""
        phone = self._extract_phone_from_3cx_email(body or "")
        if not phone:
            return None
        for variant in _phone_variants(phone):
            user = self.zammad.find_user_by_phone(variant)
            if user and user.get("id"):
                logger.info(
                    "Client trouvé via téléphone %s (variante %s) : %s (ID: %s)",
                    phone,
                    variant,
                    f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                    user["id"],
                )
                return user
        logger.info("Aucun client trouvé pour le téléphone %s (variantes testées)", phone)
        return None

    def _run_pipeline(
        self, ticket_id: int, article_id: int | None, payload: WebhookPayload, audio_bytes: bytes
    ) -> dict:
        transcript = self._transcribe_only(audio_bytes)
        plan = self._plan_analysis(payload, transcript)

        update_payload = {"title": plan["title"]}
        if plan["customer_id"]:
            update_payload["customer_id"] = plan["customer_id"]
        self.zammad.update_ticket(ticket_id, update_payload)
        self._create_transcript_article(
            ticket_id,
            f"Transcription du message vocal :\n\n{transcript}",
            subject=plan["title"],
            reply_to=article_id,
        )

        return {
            "success": True,
            "ticket_id": ticket_id,
            "article_id": article_id,
            "transcript": transcript,
            "title": plan["title"],
            "customer_id": plan["customer_id"],
            "customer_name": plan["customer_name"],
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
