import hashlib
import hmac
import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .models import WebhookPayload
from .queue import enqueue_transcription

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("zammad-autotranscription")

settings: Settings = get_settings()

app = FastAPI(title="Zammad Auto Transcription", version="0.1.0")


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