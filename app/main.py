import hashlib
import hmac
import logging
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .logging_config import configure_logging
from .models import TranscribeRequest, WebhookPayload
from .queue import enqueue_transcription, wait_for_job

logger = logging.getLogger("zammad-autotranscription")

settings: Settings = get_settings()
configure_logging(settings.log_level)

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Zammad Auto Transcription", version="0.1.0")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# Middleware : force du JSON pour /ui/* en cas d'erreur non gérée (évite le HTML)
class UiJsonErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            if request.url.path.startswith("/ui/"):
                logger.exception("Erreur UI non gérée: %s", exc)
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "detail": "Erreur interne du serveur"},
                )
            raise


app.add_middleware(UiJsonErrorMiddleware)


def valid_signature(body: bytes, signature: str) -> bool:
    if not settings.webhook_secret:
        return True
    for prefix in ("sha1=", "sha256="):
        if signature.startswith(prefix):
            hex_digest = signature[len(prefix) :]
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
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/ui/transcribe")
async def ui_transcribe(
    request: Request,
    payload: TranscribeRequest,
    wait: bool = True,
) -> JSONResponse:
    from .processor import Processor

    processor = Processor(settings)

    # Le payload peut contenir l'ID interne OU le numéro de ticket (ex: 202608069400166)
    ticket_id = payload.ticket_id
    ticket = None

    # 1) Essayer l'ID interne directement
    try:
        ticket = processor.zammad.get_ticket(ticket_id)
    except Exception:
        ticket = None

    # 2) Si échec, chercher par numéro (le champ 'number' de Zammad)
    if ticket is None:
        try:
            found = processor.zammad.find_ticket_by_number(str(ticket_id))
            if found and found.get("id"):
                ticket = found
                ticket_id = found["id"]
                logger.info("Ticket résolu par numéro : %s → ID %s", payload.ticket_id, ticket_id)
        except Exception as exc:
            logger.exception("Erreur recherche ticket par numéro %s : %s", payload.ticket_id, exc)

    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} introuvable")

    # Récupérer les articles (protégé : un 4xx ne doit pas faire planter l'endpoint)
    articles = []
    try:
        articles = processor.zammad.get_ticket_articles(ticket_id)
    except Exception as exc:
        logger.warning("Impossible de lire les articles du ticket %s : %s", ticket_id, exc)

    audio_attachment = None
    for article in articles or []:
        for att in article.get("attachments", []):
            filename = (att.get("filename") or "").lower()
            if filename.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                audio_attachment = att
                break
        if audio_attachment:
            break

    if not audio_attachment:
        raise HTTPException(status_code=422, detail="Aucun attachment audio trouvé dans le ticket")

    job_id = enqueue_transcription(
        {
            "ticket": {
                "id": ticket.get("id"),
                "number": ticket.get("number"),
                "title": ticket.get("title"),
                "customer_id": ticket.get("customer_id"),
                "customer": ticket.get("customer"),
            },
            "article": {
                "id": audio_attachment.get("id"),
                "ticket_id": ticket_id,
                "type": "note",
                "attachments": [audio_attachment],
            },
        }
    )

    logger.info("Transcription manuelle ticket %s enfile (job %s)", ticket_id, job_id)

    if not wait:
        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "ticket_id": ticket_id, "job_id": job_id},
        )

    # Attendre la fin du job (mode synchrone pour l'UI)
    try:
        result = wait_for_job(job_id, settings, timeout=300)
    except TimeoutError:
        raise HTTPException(
            status_code=504, detail="Timeout: le job n'a pas terminé à temps"
        ) from None
    except Exception as exc:
        logger.exception("Erreur lors du traitement du job %s : %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {exc}") from None

    # Construire l'URL du ticket Zammad (avec l'ID interne résolu)
    zammad_base = settings.zammad_url.rstrip("/")
    ticket_url = f"{zammad_base}/#ticket/zoom/{ticket_id}"

    return JSONResponse(
        content={
            "success": True,
            "ticket_id": ticket_id,
            "ticket_url": ticket_url,
            "title": result.get("title"),
            "transcript": result.get("transcript"),
            "customer_id": result.get("customer_id"),
            "customer_name": result.get("customer_name"),
        }
    )


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
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "ticket_id": payload.ticket.id, "job_id": job_id},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
