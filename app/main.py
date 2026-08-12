import hashlib
import hmac
import logging
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, get_settings
from .logging_config import configure_logging
from .models import WebhookPayload, TranscribeRequest
from .queue import enqueue_transcription

logger = logging.getLogger("zammad-autotranscription")

settings: Settings = get_settings()
configure_logging(settings.log_level)

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Zammad Auto Transcription", version="0.1.0")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def valid_signature(body: bytes, signature: str) -> bool:
    if not settings.webhook_secret:
        return True
    for prefix in ("sha1=", "sha256="):
        if signature.startswith(prefix):
            hex_digest = signature[len(prefix):]
            break
    else:
        hex_digest = signature
    try:
        computed = hmac.new(
            settings.webhook_secret.encode(),
            body,
            digestmod=hashlib.sha1,
        ).hexdigest()
    except ValueError:
        return False
    return hmac.compare_digest(computed.lower(), hex_digest.lower())


def authorize(request: Request, authorization: str | None) -> None:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            if settings.webhook_secret and not hmac.compare_digest(token, settings.webhook_secret):
                raise HTTPException(status_code=401, detail="Token invalide")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ui", response_class=HTMLResponse)
async def ui_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/ui/transcribe")
async def ui_transcribe(request: Request, payload: TranscribeRequest) -> JSONResponse:
    from .processor import Processor

    processor = Processor(settings)

    try:
        ticket = processor.zammad.get_ticket(payload.ticket_id)
    except Exception as exc:
        logger.exception("Erreur récupération ticket %s : %s", payload.ticket_id, exc)
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} introuvable")

    articles = processor.zammad.get_ticket_articles(payload.ticket_id) if hasattr(processor.zammad, 'get_ticket_articles') else []
    if not articles:
        try:
            articles = processor.zammad.get_ticket_articles(payload.ticket_id)
        except Exception:
            pass

    audio_attachment = None
    if articles:
        for article in articles:
            for att in article.get("attachments", []):
                filename = (att.get("filename") or "").lower()
                if filename.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                    audio_attachment = att
                    break
            if audio_attachment:
                break

    if not audio_attachment:
        raise HTTPException(status_code=422, detail="Aucun attachment audio trouvé dans le ticket")

    job_id = enqueue_transcription({
        "ticket": {
            "id": ticket.get("id"),
            "number": ticket.get("number"),
            "title": ticket.get("title"),
            "customer_id": ticket.get("customer_id"),
            "customer": ticket.get("customer"),
        },
        "article": {
            "id": audio_attachment.get("id"),
            "ticket_id": payload.ticket_id,
            "type": "note",
            "attachments": [audio_attachment],
        }
    })

    logger.info("Transcription manuelle ticket %s enfile (job %s)", payload.ticket_id, job_id)

    return JSONResponse(status_code=202, content={"status": "accepted", "ticket_id": payload.ticket_id, "job_id": job_id})


@app.post("/webhook/zammad")
async def webhook(
    request: Request,
    x_hub_signature: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    body = await request.body()
    authorize(request, authorization)

    if x_hub_signature is None or x_hub_signature == "":
        if settings.webhook_secret:
            raise HTTPException(status_code=401, detail="Signature manquante")
    elif not valid_signature(body, x_hub_signature):
        raise HTTPException(status_code=401, detail="Signature invalide")

    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception as exc:
        logger.warning("Payload invalide : %s", exc)
        raise HTTPException(status_code=422, detail=f"Payload invalide: {exc}") from exc

    if payload.ticket.id is None:
        raise HTTPException(status_code=422, detail="ticket.id absent")

    job_id = enqueue_transcription(payload.model_dump(mode="json"))
    logger.info("Ticket %s enfile (job %s)", payload.ticket.id, job_id)
    return JSONResponse(status_code=202, content={"status": "accepted", "ticket_id": payload.ticket.id, "job_id": job_id})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)