from unittest.mock import MagicMock, patch

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
    assert result["success"] is False
    step = result["steps"][-1]
    assert step["step"] == "article"
    assert step["status"] == "error"


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


def test_idempotence_reuses_stored_transcript(tmp_path):
    """Le deuxième appel renvoie le résultat stocké, pas des données null."""
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="texte cool"),
        patch.object(
            processor.titles, "generate", return_value={"title": "Titre", "customer_name": "Alice"}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
    ):
        processor.process(payload())
        result = processor.process(payload())

    assert result["idempotent"] is True
    assert result["transcript"] == "texte cool"
    assert result["title"] == "Titre"
    assert result["customer_name"] == "Alice"


def test_no_audio_state_does_not_block_retranscription(tmp_path):
    """Un état 'no_audio' (sans transcription) ne doit pas bloquer une nouvelle tentative."""
    processor = make_processor(tmp_path)
    payload_obj = payload()
    article_id = payload_obj.article.id
    processor._mark_done(payload_obj.ticket.id, article_id, {"status": "no_audio"})

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="transcrit enfin"),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
    ):
        result = processor.process(payload_obj)

    assert result.get("idempotent") is not True
    assert result["success"] is True
    assert result["transcript"] == "transcrit enfin"


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
    ):
        result = processor.process(payload())

    assert calls["n"] == 3
    assert result["success"] is False
    transcription_step = [s for s in result["steps"] if s["step"] == "transcription"][0]
    assert transcription_step["status"] == "error"
    assert "boom" in transcription_step["error"]


def test_no_retries_manual_mode(tmp_path):
    """En mode manuel (retries=False), on échoue immédiatement avec l'erreur sur la bonne étape."""
    processor = make_processor(tmp_path)
    calls = {"n": 0}

    def failing_download(_url):
        calls["n"] += 1
        raise ZammadError("network down")

    with (
        patch.object(processor.zammad, "get_attachment", failing_download),
        patch("app.processor.time.sleep"),
    ):
        result = processor.process(payload(), retries=False)

    assert calls["n"] == 1
    assert result["success"] is False
    download_step = [s for s in result["steps"] if s["step"] == "download"][0]
    assert download_step["status"] == "error"
    assert "network down" in download_step["error"]


def test_prepare_manual_success(tmp_path):
    """Le brouillon manuel rapporte chaque étape sans écrire dans Zammad."""
    processor = make_processor(tmp_path)
    reported = []

    def progress(name, entry):
        reported[:] = [s for s in reported if s != name] + [name]

    with (
        patch.object(processor.zammad, "get_ticket", side_effect=ZammadError("404")),
        patch.object(
            processor.zammad,
            "find_ticket_by_number",
            return_value={
                "id": 6475,
                "number": "202608069400166",
                "title": "Nouveau message vocal",
                "customer_id": None,
                "customer": None,
            },
        ),
        patch.object(
            processor.zammad,
            "get_ticket_articles",
            return_value=[
                {
                    "id": 104,
                    "body": "De: +33 6 12 34 56 78<br>Appel manqué",
                    "attachments": [{"id": 174, "filename": "voicemail.mp3"}],
                }
            ],
        ),
        patch.object(processor.zammad, "get_attachment", return_value=b"x") as mock_get_attachment,
        patch.object(processor.transcriber, "transcribe", return_value="bonjour test"),
        patch.object(processor.zammad, "find_user_by_phone", return_value=None),
        patch.object(
            processor.titles,
            "generate",
            return_value={"title": "Titre", "customer_name": "Alice"},
        ),
        patch.object(processor.zammad, "find_user_by_name", return_value=None),
        patch.object(processor.zammad, "update_ticket", MagicMock(return_value={})) as mock_update,
        patch.object(processor.zammad, "create_article", MagicMock(return_value={})) as mock_create,
        patch.object(
            processor.zammad, "create_user", MagicMock(return_value={})
        ) as mock_create_user,
    ):
        result = processor.prepare_manual(202608069400166, progress=progress)

        # Aucune écriture Zammad pendant la préparation
        mock_update.assert_not_called()
        mock_create.assert_not_called()
        mock_create_user.assert_not_called()

    assert result["success"] is True
    assert result["draft"] is True
    assert result["ticket_id"] == 6475
    assert result["article_id"] == 104
    assert result["title"] == "Titre"
    assert result["transcript"] == "bonjour test"
    assert result["customer_suggestion"] == "Alice"
    assert result["customer_id_suggestion"] is None
    assert reported == ["ticket", "article", "download", "transcription"]
    assert [s["step"] for s in result["steps"]] == [
        "ticket",
        "article",
        "download",
        "transcription",
    ]
    # L'URL de l'attachment est construite (l'API Zammad n'en renvoie pas)
    attachment_url = "http://zammad.example.com/api/v1/ticket_attachment/6475/104/174"
    assert mock_get_attachment.call_args.args[0] == attachment_url


def test_prepare_manual_ticket_not_found(tmp_path):
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_ticket", side_effect=ZammadError("404")),
        patch.object(processor.zammad, "find_ticket_by_number", return_value=None),
    ):
        result = processor.prepare_manual(99999)

    assert result["success"] is False
    assert result["draft"] is False
    ticket_step = result["steps"][0]
    assert ticket_step["step"] == "ticket"
    assert ticket_step["status"] == "error"


def test_prepare_manual_no_audio_article(tmp_path):
    processor = make_processor(tmp_path)

    with (
        patch.object(
            processor.zammad,
            "get_ticket",
            return_value={
                "id": 6475,
                "number": "202608069400166",
                "title": "T",
                "customer_id": 8,
                "customer": {},
            },
        ),
        patch.object(
            processor.zammad,
            "get_ticket_articles",
            return_value=[{"id": 104, "attachments": [{"id": 1, "filename": "doc.pdf"}]}],
        ),
    ):
        result = processor.prepare_manual(6475)

    assert result["success"] is False
    assert result["draft"] is False
    article_step = [s for s in result["steps"] if s["step"] == "article"][0]
    assert article_step["status"] == "error"
    assert "audio" in article_step["error"]


def test_commit_manual(tmp_path):
    """L'opérateur valide un brouillon : titre, client, article sont écrits."""
    processor = make_processor(tmp_path)

    with (
        patch.object(
            processor.zammad,
            "find_user_by_name",
            return_value={"id": 42, "firstname": "Alice", "lastname": "Dupont"},
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}) as mock_update,
        patch.object(processor.zammad, "create_article", return_value={"id": 505}) as mock_create,
        patch.object(processor, "_mark_done", return_value=None) as mock_done,
    ):
        result = processor.commit_manual(
            ticket_id=6475,
            article_id=104,
            transcript="bonjour test",
            title="Titre corrigé",
            customer_name="Alice Dupont",
        )

    assert result["success"] is True
    assert result["ticket_id"] == 6475
    assert result["article_id"] == 505
    assert result["customer_id"] == 42
    assert result["customer_name"] == "Alice Dupont"
    assert mock_update.call_args.args == (6475, {"title": "Titre corrigé", "customer_id": 42})
    article_payload = mock_create.call_args.args[1]
    assert article_payload["body"] == "bonjour test"
    assert article_payload["type"] == "note"
    assert article_payload["sender"] == "Agent"
    assert article_payload["content_type"] == "text/plain"
    assert article_payload["internal"] is False
    assert article_payload["subject"] == "Titre corrigé"
    assert article_payload["reply_to"] == 104
    mock_done.assert_called_once()


def test_commit_manual_keeps_reply_article_id_when_zammad_no_id(tmp_path):
    """En l'absence d'id dans la réponse Zammad, on retombe sur l'article source."""
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={}),
        patch.object(processor, "_mark_done", return_value=None),
    ):
        result = processor.commit_manual(
            ticket_id=6475,
            article_id=104,
            transcript="bonjour test",
            title="",
        )

    assert result["success"] is True
    assert result["article_id"] == 104


def test_pipeline_article_uses_agent_sender(tmp_path):
    """L'article créé par le webhook est explicite : type note, sender Agent."""
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="Salut"),
        patch.object(
            processor.titles, "generate", return_value={"title": "Titre", "customer_name": None}
        ),
        patch.object(processor.zammad, "update_ticket", return_value={}),
        patch.object(processor.zammad, "create_article", return_value={"id": 9}) as mock_article,
    ):
        result = processor.process(payload())

    assert result["success"] is True
    article_payload = mock_article.call_args.args[1]
    assert article_payload["sender"] == "Agent"
    assert article_payload["type"] == "note"
    assert article_payload["content_type"] == "text/plain"
    assert article_payload["internal"] is False


def test_empty_transcript_fails_step(tmp_path):
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "get_attachment", return_value=b"x"),
        patch.object(processor.transcriber, "transcribe", return_value="   "),
        patch.object(
            processor.titles, "generate", return_value={"title": "T", "customer_name": None}
        ),
        patch("app.processor.time.sleep"),
    ):
        result = processor.process(payload())

    assert result["success"] is False
    transcription_step = [s for s in result["steps"] if s["step"] == "transcription"][0]
    assert transcription_step["status"] == "error"
    assert "Transcription vide" in transcription_step["error"]


def test_plan_uses_payload_customer_without_llm(tmp_path):
    """Client déjà posé sur le ticket : réutilisé. Ollama appelé pour le titre seulement."""
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = {"id": 8, "firstname": "Emily", "lastname": "Adams"}

    with patch.object(
        processor.titles,
        "generate",
        return_value={"title": "Titre Ollama", "customer_name": "Autre nom"},
    ) as mock_generate:
        plan = processor._plan_analysis(p, "transcription")

    assert plan["customer_id"] == 8
    assert plan["customer_name"] == "Emily Adams"
    assert plan["title"] == "Titre Ollama"
    mock_generate.assert_called_once()


def test_plan_uses_phone_without_llm_client(tmp_path):
    """Client trouvé par téléphone : utilisé. L'avis client d'Ollama est ignoré,
    mais Ollama reste appelé pour générer le titre."""
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None
    p.article.body = "De: +33 6 12 34 56 78<br>Appel manqué"

    with (
        patch.object(
            processor.zammad,
            "find_user_by_phone",
            return_value={"id": 42, "firstname": "Alice", "lastname": "Dupont"},
        ),
        patch.object(
            processor.titles,
            "generate",
            return_value={"title": "Titre Ollama", "customer_name": "Client inventé par LLM"},
        ) as mock_generate,
        patch.object(processor.zammad, "find_user_by_name") as mock_by_name,
    ):
        plan = processor._plan_analysis(p, "transcription")

    assert plan["customer_id"] == 42
    assert plan["customer_name"] == "Alice Dupont"
    assert plan["title"] == "Titre Ollama"
    mock_generate.assert_called_once()
    mock_by_name.assert_not_called()


def test_plan_phone_not_found_still_uses_llm(tmp_path):
    """Téléphone non trouvé : Ollama propose titre + client, recherché dans Zammad."""
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None
    p.article.body = "De: +33 6 12 34 56 78<br>Appel manqué"

    with (
        patch.object(processor.zammad, "find_user_by_phone", return_value=None),
        patch.object(
            processor.titles,
            "generate",
            return_value={"title": "Titre", "customer_name": "Acme"},
        ),
        patch.object(
            processor.zammad,
            "find_user_by_name",
            return_value={"id": 55, "firstname": "Acme", "lastname": "Corp"},
        ),
    ):
        plan = processor._plan_analysis(p, "transcription")

    assert plan["title"] == "Titre"
    assert plan["customer_id"] == 55
    assert plan["customer_name"] == "Acme Corp"


def test_plan_llm_name_not_found_never_creates(tmp_path):
    """Client proposé par Ollama mais absent de Zammad : nom indiqué, AUCUNE création."""
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None
    p.article.body = ""

    with (
        patch.object(
            processor.titles,
            "generate",
            return_value={"title": "Titre", "customer_name": "Acme"},
        ),
        patch.object(processor.zammad, "find_user_by_name", return_value=None),
        patch.object(processor.zammad, "create_user") as mock_create,
    ):
        plan = processor._plan_analysis(p, "transcription")

    assert plan["customer_id"] is None
    assert plan["customer_name"] == "Acme"
    mock_create.assert_not_called()


def test_plan_no_llm_when_no_customer_info(tmp_path):
    """Sans téléphone ni nom, Ollama fournit le titre, pas de client."""
    processor = make_processor(tmp_path)
    p = payload()
    p.ticket.customer = None
    p.article.body = ""

    with patch.object(
        processor.titles,
        "generate",
        return_value={"title": "Titre", "customer_name": None},
    ):
        plan = processor._plan_analysis(p, "transcription")

    assert plan["title"] == "Titre"
    assert plan["customer_id"] is None
    assert plan["customer_name"] is None


def test_commit_manual_never_creates_customer(tmp_path):
    """commit_manual : nom introuvable dans Zammad → aucun client créé."""
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "find_user_by_name", return_value=None),
        patch.object(processor.zammad, "create_user") as mock_create,
        patch.object(processor.zammad, "update_ticket", return_value={}) as mock_update,
        patch.object(processor.zammad, "create_article", return_value={"id": 1}),
        patch.object(processor, "_mark_done", return_value=None),
    ):
        result = processor.commit_manual(
            ticket_id=6475,
            article_id=None,
            transcript="bonjour",
            title="Titre",
            customer_name="Client inconnu",
        )

    assert result["success"] is True
    assert result["customer_id"] is None
    assert mock_create.assert_not_called() is None
    assert mock_update.call_args.args[1] == {"title": "Titre"}


def test_commit_manual_resolves_existing_customer_by_name(tmp_path):
    """commit_manual : nom trouvé dans Zammad → client_id utilisé."""
    processor = make_processor(tmp_path)

    with (
        patch.object(processor.zammad, "find_user_by_name", return_value={"id": 42}),
        patch.object(processor.zammad, "update_ticket", return_value={}) as mock_update,
        patch.object(processor.zammad, "create_article", return_value={"id": 1}),
        patch.object(processor, "_mark_done", return_value=None),
    ):
        result = processor.commit_manual(
            ticket_id=6475,
            article_id=None,
            transcript="bonjour",
            title="Titre",
            customer_name="Alice Dupont",
        )

    assert result["customer_id"] == 42
    assert mock_update.call_args.args[1] == {"title": "Titre", "customer_id": 42}


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
