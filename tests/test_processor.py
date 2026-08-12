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

    with (
        patch.object(processor.zammad, "get_attachment", fake_attach),
        patch.object(
            processor.transcriber,
            "transcribe",
            return_value="Bonjour, je rappelle pour ma facture 2026.",
        ),
        patch.object(
            processor.titles,
            "generate",
            return_value={"title": "Rappel facture", "customer_name": None},
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}) as mock_update,
        patch.object(processor.zammad, "create_article", return_value={}) as mock_article,
    ):
        result = processor.process(payload())

    assert result["success"] is True
    assert result["title"] == "Rappel facture"
    assert "facture" in result["transcript"]
    mock_update.assert_called_once()
    mock_article.assert_called_once()


def test_no_audio_marked(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.article.attachments = [
        __import__("app.models", fromlist=["Attachment"]).Attachment(filename="scan.pdf")
    ]

    result = processor.process(p)
    assert result["status"] == "no_audio"


def test_idempotence_prevents_reprocess(tmp_path):
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="texte"),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
    ):
        processor.process(payload())
        result = processor.process(payload())

    assert result["idempotent"] is True


def test_retries_on_error(tmp_path):
    processor = make_processor(tmp_path)

    calls = {"n": 0}

    def failing_transcribe(_b):
        calls["n"] += 1
        raise ZammadError("boom")

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", failing_transcribe),
        patch("app.processor.time.sleep"),
        pytest.raises(ZammadError),
    ):
        processor.process(payload())

    assert calls["n"] == 3


def test_empty_transcript_raises(tmp_path):
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="   "),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch("app.processor.time.sleep"),
    ):
        with pytest.raises(RuntimeError):
            processor.process(payload())


def test_customer_resolution_uses_payload_customer(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = {"id": 8, "firstname": "Emily", "lastname": "Adams"}

    assert processor._resolve_customer(p, "Acme") == 8


def test_customer_resolution_llm_lookup(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None

    with patch.object(processor.zammad, "find_user_by_name", return_value={"id": 55}):
        assert processor._resolve_customer(p, "Acme") == 55


def test_customer_resolution_llm_create(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None

    with (
        patch.object(processor.zammad, "find_user_by_name", return_value=None),
        patch.object(processor.zammad, "create_user", return_value={"id": 66}),
    ):
        assert processor._resolve_customer(p, "Acme") == 66


def test_customer_resolution_create_failure_returns_none(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None

    with (
        patch.object(processor.zammad, "find_user_by_name", return_value=None),
        patch.object(processor.zammad, "create_user", side_effect=ZammadError("nope")),
    ):
        assert processor._resolve_customer(p, "Acme") is None


def test_customer_resolution_no_name_returns_none(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None

    assert processor._resolve_customer(p, None) is None


def test_missing_audio_with_url_uses_url(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    p.article.attachments = [
        __import__("app.models", fromlist=["Attachment"]).Attachment(filename="scan.pdf"),
        __import__("app.models", fromlist=["Attachment"]).Attachment(
            filename="msg.m4a", url="http://zammad.example.com/dl/msg.m4a"
        ),
    ]

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x") as mock_attach,
        patch.object(processor.transcriber, "transcribe", return_value="Bonjour"),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
    ):
        result = processor.process(p)

    assert result["success"] is True
    mock_attach.assert_called_once_with("http://zammad.example.com/dl/msg.m4a")


def test_state_file_corrupted_treated_as_not_done(tmp_path):
    processor = make_processor(tmp_path)
    p = payload()
    state = tmp_path / "state" / "81_104.json"
    state.parent.mkdir(parents=True)
    state.write_text("not json {")

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="Bonjour"),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
    ):
        result = processor.process(p)

    assert result["success"] is True
