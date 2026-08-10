import json
import logging
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
                logger.error("Tentative %s/%s échouée pour le ticket %s : %s",
                             attempt, MAX_RETRIES, ticket_id, exc)
                if attempt == MAX_RETRIES:
                    self._mark_failed(ticket_id, article_id, str(exc))
                    raise
                time.sleep(RETRY_BACKOFF[attempt - 1])

    def _run_pipeline(self, ticket_id: int, article_id: int | None,
                      payload: WebhookPayload, audio_url: str) -> dict:
        audio_bytes = self.zammad.get_attachment(audio_url)
        transcript = self.transcriber.transcribe(audio_bytes)
        transcript = clean_transcript(transcript)
        if not transcript:
            raise RuntimeError("Transcription vide après nettoyage.")

        meta = self.titles.generate(transcript)

        customer_id = self._resolve_customer(payload, meta.get("customer_name"))
        self.zammad.update_ticket(ticket_id, {
            "title": meta["title"],
            **({"customer_id": customer_id} if customer_id else {}),
        })
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

    def _resolve_customer(self, payload: WebhookPayload, llm_name: str | None) -> int | None:
        customer = payload.ticket.customer or {}
        if customer.get("id"):
            return customer["id"]
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
        self._write_state(ticket_id, article_id, {**data, "finished_at": time.time(), "success": True})

    def _mark_failed(self, ticket_id: int, article_id: int | None, error: str) -> None:
        self._write_state(ticket_id, article_id,
                          {"error": error, "finished_at": time.time(), "success": False})

    def _write_state(self, ticket_id: int, article_id: int | None, data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path(ticket_id, article_id).write_text(json.dumps(data, ensure_ascii=False))

    def _state_path(self, ticket_id: int, article_id: int | None) -> Path:
        key = f"{ticket_id}_{article_id or 'na'}"
        return self.state_dir / f"{key}.json"