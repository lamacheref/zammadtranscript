import hashlib
import hmac
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .logging_config import configure_logging
from .models import TranscribeRequest, WebhookPayload
from .queue import (
    enqueue_manual_transcription,
    enqueue_transcription,
    get_job_status,
    get_redis_connection,
)

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


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    # Retourne 200 (vide pour HEAD) — compatible healthcheck wget -q --spider
    return JSONResponse(content={"status": "ok"})


@app.get("/ui/models")
def ui_models() -> JSONResponse:
    """État des modèles (Ollama/Whisper) et services requis, affiché en barre d'icônes."""
    from .title_generator import TitleGenerator
    from .transcriber import Transcriber

    checks: dict = {}

    checks["ollama"] = {
        "label": f"Ollama ({settings.ollama_model})",
        **TitleGenerator(settings).available_models(),
    }

    checks["whisper"] = {
        "label": f"Whisper ({settings.whisper_model})",
        **Transcriber(settings).model_available(),
    }

    try:
        get_redis_connection(settings).ping()
        checks["redis"] = {"label": "Redis", "status": "ok", "message": "Redis joignable"}
    except Exception as exc:
        checks["redis"] = {
            "label": "Redis",
            "status": "error",
            "message": f"Redis injoignable : {exc}",
        }

    try:
        r = httpx.get(f"{settings.zammad_url.rstrip('/')}/", timeout=10)
        checks["zammad"] = {
            "label": "Zammad",
            "status": "ok" if r.status_code < 500 else "error",
            "message": f"Zammad répond (HTTP {r.status_code})",
        }
    except Exception as exc:
        checks["zammad"] = {
            "label": "Zammad",
            "status": "error",
            "message": f"Zammad injoignable : {exc}",
        }

    return JSONResponse(content={"checks": checks})


@app.get("/ui", response_class=HTMLResponse)
async def ui_index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/ui/transcribe", status_code=202)
async def ui_transcribe(payload: TranscribeRequest) -> JSONResponse:
    """Enfile une transcription manuelle et renvoie le job_id (l'UI interroge /ui/status)."""
    ticket_input = payload.ticket_id
    job_id = enqueue_manual_transcription(ticket_input)
    logger.info("Transcription manuelle %s enfile (job %s)", ticket_input, job_id)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "ticket_input": ticket_input, "job_id": job_id},
    )


@app.get("/ui/status/{job_id}")
async def ui_status(job_id: str) -> JSONResponse:
    """État d'un job de transcription manuelle : étapes + statut + résultat."""
    status = get_job_status(job_id)
    result = status.get("result") or {}
    if result.get("ticket_id") and not result.get("ticket_url"):
        zammad_base = settings.zammad_url.rstrip("/")
        result = {
            **result,
            "ticket_url": f"{zammad_base}/#ticket/zoom/{result['ticket_id']}",
        }
    status["result"] = result
    return JSONResponse(content=status)


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
