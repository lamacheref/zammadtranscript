import hashlib
import hmac
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "ticket": {
        "id": 81,
        "number": "10081",
        "title": "Webhook-Test",
        "customer_id": 8,
        "customer": {"id": 8, "firstname": "Emily", "lastname": "Adams"},
    },
    "article": {
        "id": 104,
        "ticket_id": 81,
        "type": "email",
        "attachments": [
            {
                "id": 174,
                "filename": "voicemail.mp3",
                "url": "https://zammad.example.com/api/v1/ticket_attachment/81/104/174",
            }
        ],
    },
}


def signed_headers(secret: str, body: bytes) -> dict:
    digest = hmac.new(secret.encode(), body, hashlib.sha1).digest()
    return {"X-Hub-Signature": f"sha1={digest.hex()}"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_missing_signature_when_secret_set():
    with patch("app.main.settings.webhook_secret", "secret"):
        r = client.post("/webhook/zammad", json=PAYLOAD)
    assert r.status_code == 401


def test_bad_signature():
    with patch("app.main.settings.webhook_secret", "secret"):
        r = client.post(
            "/webhook/zammad", json=PAYLOAD, headers={"X-Hub-Signature": "sha1=deadbeef"}
        )
    assert r.status_code == 401


def test_valid_signature_and_pipeline():
    body = json.dumps(PAYLOAD).encode()
    headers = signed_headers("secret", body)

    with patch("app.main.settings.webhook_secret", "secret"), \
         patch("app.main.processor.process", return_value={"status": "ok"}) as mock_process:
        r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 202
    assert mock_process.called


def test_no_audio_skipped():
    body = json.dumps(
        {
            "ticket": {"id": 99},
            "article": {"id": 100, "attachments": [{"filename": "doc.pdf"}]},
        }
    ).encode()
    headers = signed_headers("secret", body)
    with patch("app.main.settings.webhook_secret", "secret"):
        with patch("app.main.processor.process", return_value={"status": "no_audio"}) as m:
            r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 202
    assert m.called