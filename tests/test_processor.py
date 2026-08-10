import time
from unittest.mock import patch

import pytest

from app.config import Settings
from app.models import WebhookPayload
from app.processor import Processor
from app.zammad import ZammadError


def make_settings(tmp_path, **overrides):
    base = {
        "zammad_url": "http://zammad.example.com",
        "zammad_token": "token",
        "whisper_model": "base",
    }
    base.update(overrides)
    return Settings(**base)


def make_processor(tmp_path, **overrides):
    settings = make_settings(tmp_path, **overrides)
    return Processor(settings, state_dir=tmp_path / "state")


def payload(ticket_id=81, article_id=104):
    return WebhookPayload.model_validate(
        {
            "ticket": {
                "id": ticket_id,
                "number": "10081",
                "title": "Webhook-Test",
                "customer_id": 8,
                "customer": {"id": 8, "firstname": "Emily", "lastname": "Adams"},
            },
            "article": {
                "id": article_id,
                "ticket_id": ticket_id,
                "type": "email",
                "attachments": [
                    {
                        "id": 174,
                        "filename": "voicemail.mp3",
                        "url": "http://zammad.example.com/api/v1/ticket_attachment/81/104/174",
                    }
                ],
            },
        }
    )


def test_pipeline_success(tmp_path):
    processor = make_processor(tmp_path)

    def fake_attach(url):
        return b"RIFF....audio"

    with patch.object(processor.zammad, "get_attachment", fake_attach), \
         patch.object(processor.transcriber, "transcribe", return_value="Bonjour, je rappelle pour ma facture 2026."), \
         patch.object(processor.titles, "generate", return_value={"title": "Rappel facture", "customer_name": None}), \
         patch.object(processor.zammad, "update_ticket", return_value={}) as mock_update, \
         patch.object(processor.zammad, "create_article", return_value={}) as mock_article:
        result = processor.process(payload())

    assert result["success"] is True
    assert result["title"] == "Rappel facture"
    assert "facture" in result["transcript"]
    mock_update.assert_called_once()
    mock_article.assert_called_once()


def test_no_audio_marked(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.article.attachments = [__import__("app.models", fromlist=["Attachment"]).Attachment(filename="scan.pdf")]

    result = processor.process(p)
    assert result["status"] == "no_audio"


def test_idempotence_prevents_reprocess(tmp_path):
    processor = make_processor(tmp_path)

    with patch.object(processor.zammad, "get_attachment", return_value=b"x"), \
         patch.object(processor.transcriber, "transcribe", return_value="texte"), \
         patch.object(processor.titles, "generate", return_value={"title": "T", "customer_name": None}), \
         patch.object(processor.zammad, "update_ticket", return_value={}), \
         patch.object(processor.zammad, "create_article", return_value={}):
        processor.process(payload())
        result = processor.process(payload())

    assert result["idempotent"] is True


def test_retries_on_error(tmp_path):
    processor = make_processor(tmp_path)

    calls = {"n": 0}

    def failing_transcribe(_b):
        calls["n"] += 1
        raise ZammadError("boom")

    with patch.object(processor.zammad, "get_attachment", return_value=b"x"), \
         patch.object(processor.transcriber, "transcribe", failing_transcribe), \
         patch("app.processor.time.sleep"):
        with pytest.raises(ZammadError):
            processor.process(payload())

    assert calls["n"] == 3