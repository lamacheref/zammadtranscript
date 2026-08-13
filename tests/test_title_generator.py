from unittest.mock import MagicMock, patch

import pytest

from app.title_generator import TitleError, TitleGenerator


@pytest.fixture(autouse=True)
def _no_ollama_auto_pull():
    # generate() déclenche ensure_ollama_model : inutile de télécharger en test.
    with patch("app.title_generator.ensure_ollama_model", return_value={"status": "ok"}):
        yield


def make_generator():
    settings = MagicMock()
    settings.ollama_url = "http://localhost:11434"
    settings.ollama_model = "llama3.2"
    return TitleGenerator(settings)


def _message(content: str) -> MagicMock:
    m = MagicMock()
    m.message.content = content
    return m


def test_generate_valid_json():
    gen = make_generator()
    client = MagicMock()
    client.chat.return_value = _message('{"title": "Rappel facture", "customer_name": "Acme"}')
    gen._client = client

    result = gen.generate("transcription du message")

    assert result == {"title": "Rappel facture", "customer_name": "Acme"}
    client.chat.assert_called_once()
    assert client.chat.call_args.kwargs["format"] == "json"


def test_generate_no_customer():
    gen = make_generator()
    client = MagicMock()
    client.chat.return_value = _message('{"title": "Titre", "customer_name": null}')
    gen._client = client

    result = gen.generate("transcription")

    assert result["customer_name"] is None


def test_generate_title_truncated_to_80():
    gen = make_generator()
    client = MagicMock()
    client.chat.return_value = _message('{"title": "%s", "customer_name": null}' % ("a" * 120))
    gen._client = client

    result = gen.generate("transcription")

    assert len(result["title"]) == 80


def test_generate_invalid_json_raises():
    gen = make_generator()
    client = MagicMock()
    client.chat.return_value = _message("pas du json")
    gen._client = client

    with pytest.raises(TitleError):
        gen.generate("transcription")


def test_generate_empty_title_raises():
    gen = make_generator()
    client = MagicMock()
    client.chat.return_value = _message('{"title": "", "customer_name": null}')
    gen._client = client

    with pytest.raises(TitleError):
        gen.generate("transcription")


def test_client_lazy_loading():
    import app.title_generator as mod

    gen = make_generator()
    assert gen._client is None
    with patch.object(mod.ollama, "Client") as mock_cls:
        mock_cls.return_value = "client-instance"
        assert gen.client == "client-instance"
        assert gen._client == "client-instance"
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["host"] == "http://localhost:11434"


@patch("app.title_generator.httpx.get")
def test_available_models_present(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:latest"}]}
    )
    assert make_generator().available_models()["status"] == "ok"


@patch("app.title_generator.httpx.get")
def test_available_models_missing(mock_get):
    mock_get.return_value = MagicMock(json=lambda: {"models": [{"name": "qwen2.5:latest"}]})
    result = make_generator().available_models()
    assert result["status"] == "error"
    assert "llama3.2" in result["message"]


@patch("app.title_generator.httpx.get")
def test_available_models_ollama_down(mock_get):
    mock_get.side_effect = Exception("connection refused")
    result = make_generator().available_models()
    assert result["status"] == "error"
    assert "injoignable" in result["message"].lower()
