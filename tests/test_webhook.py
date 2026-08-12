import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
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

    with (
        patch("app.main.settings.webhook_secret", "secret"),
        patch("app.main.enqueue_transcription", return_value="job-123") as mock_enqueue,
    ):
        r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 202
    assert mock_enqueue.called
    assert r.json()["job_id"] == "job-123"


def test_no_audio_skipped():
    body = json.dumps(
        {
            "ticket": {"id": 99},
            "article": {"id": 100, "attachments": [{"filename": "doc.pdf"}]},
        }
    ).encode()
    headers = signed_headers("secret", body)
    with patch("app.main.settings.webhook_secret", "secret"):
        with patch("app.main.enqueue_transcription", return_value="job-456") as m:
            r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 202
    assert m.called
    assert r.json()["job_id"] == "job-456"


def test_signature_without_prefix():
    from app.main import valid_signature

    body = b"hello"
    digest = hmac.new(b"secret", body, hashlib.sha1).hexdigest()
    assert valid_signature(body, digest)


def test_valid_signature_sha256():
    from app.main import valid_signature

    body = b"hello"
    digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert valid_signature(body, f"sha256={digest}")


def test_invalid_signature_returns_false():
    from app.main import valid_signature

    with patch("app.main.settings.webhook_secret", "secret"):
        assert not valid_signature(b"hello", "sha1=deadbeef")


def test_no_signature_required_when_no_secret():
    from app.main import valid_signature

    assert valid_signature(b"hello", "")


def test_authorize_invalid_token():
    from fastapi import HTTPException

    from app.main import authorize

    with patch("app.main.settings.webhook_secret", "secret"):
        with pytest.raises(HTTPException) as exc_info:
            authorize(_RequestStub(), "Bearer wrong")
    assert exc_info.value.status_code == 401


def test_authorize_valid_token():
    from app.main import authorize

    with patch("app.main.settings.webhook_secret", "secret"):
        authorize(_RequestStub(), "Bearer secret")
    # no exception raised


def test_webhook_auth_failure():
    with patch("app.main.settings.webhook_secret", "secret"):
        r = client.post(
            "/webhook/zammad",
            content=json.dumps(PAYLOAD).encode(),
            headers={"Authorization": "Bearer wrong"},
        )
    assert r.status_code == 401


def test_webhook_invalid_payload():
    body = b"not json"
    headers = signed_headers("secret", body)
    with patch("app.main.settings.webhook_secret", "secret"):
        r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 422


def test_webhook_missing_ticket_id():
    body = json.dumps({"ticket": {}, "article": {}}).encode()
    headers = signed_headers("secret", body)
    with patch("app.main.settings.webhook_secret", "secret"):
        with patch("app.main.enqueue_transcription", return_value="job-789") as m:
            r = client.post("/webhook/zammad", content=body, headers=headers)
    assert r.status_code == 422
    assert not m.called


class _RequestStub:
    def __init__(self):
        self.client = ("127.0.0.1", 12345)


def test_ui_index():
    r = client.get("/ui")
    assert r.status_code == 200
    assert "Zammad" in r.text or "transcription" in r.text.lower()


def test_ui_transcribe_no_audio():
    with patch("app.processor.Processor") as mock_processor_cls:
        processor = mock_processor_cls.return_value
        processor.zammad.get_ticket.return_value = {
            "id": 81,
            "number": "10081",
            "title": "T",
            "customer_id": 8,
            "customer": {},
        }
        processor.zammad.get_ticket_articles.return_value = [
            {"attachments": [{"filename": "doc.pdf"}]}
        ]
        r = client.post("/ui/transcribe", json={"ticket_id": 81})

    assert r.status_code == 422
    assert "audio" in r.json()["detail"].lower()


def test_ui_transcribe_ticket_not_found():
    from fastapi import HTTPException

    with patch("app.processor.Processor") as mock_processor_cls:
        processor = mock_processor_cls.return_value
        processor.zammad.get_ticket.side_effect = HTTPException(status_code=404)
        r = client.post("/ui/transcribe", json={"ticket_id": 999})

    assert r.status_code == 404


def test_ui_transcribe_success():
    with (
        patch("app.processor.Processor") as mock_processor_cls,
        patch("app.main.enqueue_transcription", return_value="job-ui") as mock_enqueue,
    ):
        processor = mock_processor_cls.return_value
        processor.zammad.get_ticket.return_value = {
            "id": 81,
            "number": "10081",
            "title": "T",
            "customer_id": 8,
            "customer": {},
        }
        processor.zammad.get_ticket_articles.return_value = [
            {
                "attachments": [
                    {
                        "id": 174,
                        "filename": "voicemail.mp3",
                        "url": "http://zammad.example.com/dl/audio",
                    }
                ]
            }
        ]
        r = client.post("/ui/transcribe", json={"ticket_id": 81})

    assert r.status_code == 202
    assert r.json()["job_id"] == "job-ui"
    mock_enqueue.assert_called_once()
