import json
from unittest.mock import MagicMock, patch

from app import model_download
from app.config import Settings


def make_settings(**overrides):
    base = {
        "zammad_url": "http://zammad.example.com",
        "zammad_token": "t",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3.2",
    }
    base.update(overrides)
    return Settings(**base)


# ── model_present ──────────────────────────────────────────────────────────────


@patch("app.model_download.httpx.get")
def test_model_present_true(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:latest"}]}
    )
    assert model_download.model_present(make_settings()) is True


@patch("app.model_download.httpx.get")
def test_model_present_false(mock_get):
    mock_get.return_value = MagicMock(json=lambda: {"models": [{"name": "qwen2.5:latest"}]})
    assert model_download.model_present(make_settings()) is False


@patch("app.model_download.httpx.get")
def test_model_present_ollama_down(mock_get):
    mock_get.side_effect = Exception("connection refused")
    assert model_download.model_present(make_settings()) is False


# ── start_model_download ───────────────────────────────────────────────────────


@patch("app.model_download.model_present", return_value=True)
def test_start_when_present(mock_present):
    result = model_download.start_model_download(make_settings())
    assert result["status"] == "present"


@patch("app.model_download.get_redis_connection")
@patch("app.model_download.model_present", return_value=False)
def test_start_acquires_lock_and_spawns_thread(mock_present, mock_conn):
    conn = MagicMock()
    conn.set.return_value = True
    mock_conn.return_value = conn
    with patch("app.model_download.threading.Thread") as mock_thread:
        result = model_download.start_model_download(make_settings())

    assert result["status"] == "started"
    conn.set.assert_called_once()
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()


@patch("app.model_download.get_redis_connection")
@patch("app.model_download.model_present", return_value=False)
def test_start_dedupes_when_already_running(mock_present, mock_conn):
    conn = MagicMock()
    conn.set.return_value = False
    mock_conn.return_value = conn
    with patch("app.model_download.threading.Thread") as mock_thread:
        result = model_download.start_model_download(make_settings())

    assert result["status"] == "in_progress"
    mock_thread.assert_not_called()


# ── get_download_status ────────────────────────────────────────────────────────


@patch("app.model_download.get_redis_connection")
def test_status_idle(mock_conn):
    conn = MagicMock()
    conn.get.return_value = None
    mock_conn.return_value = conn
    assert model_download.get_download_status(make_settings())["status"] == "idle"


@patch("app.model_download.get_redis_connection")
def test_status_downloading_with_percent(mock_conn):
    conn = MagicMock()
    conn.get.return_value = json.dumps(
        {
            "status": "downloading",
            "message": "downloading sha256:abc",
            "completed": 1024,
            "total": 2048,
        }
    )
    mock_conn.return_value = conn
    status = model_download.get_download_status(make_settings())
    assert status["status"] == "downloading"
    assert status["percent"] == 50
    assert status["completed"] == 1024


@patch("app.model_download.get_redis_connection")
def test_status_done(mock_conn):
    conn = MagicMock()
    conn.get.return_value = json.dumps({"status": "done", "message": "ok", "model": "llama3.2"})
    mock_conn.return_value = conn
    assert model_download.get_download_status(make_settings())["status"] == "done"


@patch("app.model_download.get_redis_connection")
def test_status_error(mock_conn):
    conn = MagicMock()
    conn.get.return_value = json.dumps({"status": "error", "message": "512 missing blob"})
    mock_conn.return_value = conn
    status = model_download.get_download_status(make_settings())
    assert status["status"] == "error"
    assert "512" in status["message"]


# ── ensure_ollama_model ────────────────────────────────────────────────────────


@patch("app.model_download.start_model_download")
@patch("app.model_download.model_present", return_value=True)
def test_ensure_ok_when_present(mock_present, mock_start):
    result = model_download.ensure_ollama_model(make_settings(), wait_timeout=1)
    assert result["status"] == "ok"
    mock_start.assert_not_called()


@patch("app.model_download.get_download_status")
@patch("app.model_download.start_model_download")
@patch("app.model_download.model_present", side_effect=[False])
def test_ensure_pulls_when_missing(mock_present, mock_start, mock_status):
    mock_start.return_value = {"status": "started"}
    mock_status.return_value = {"status": "done"}
    result = model_download.ensure_ollama_model(make_settings(), wait_timeout=3)
    assert result["status"] == "ok"
    mock_start.assert_called_once()


@patch("app.model_download.get_download_status")
@patch("app.model_download.start_model_download")
@patch("app.model_download.model_present", side_effect=[False])
def test_ensure_reports_error(mock_present, mock_start, mock_status):
    mock_start.return_value = {"status": "started"}
    mock_status.return_value = {"status": "error", "message": "disk full"}
    result = model_download.ensure_ollama_model(make_settings(), wait_timeout=3)
    assert result["status"] == "error"


# ── _pull_worker ───────────────────────────────────────────────────────────────


@patch("app.model_download.get_redis_connection")
def test_pull_worker_uses_configured_ollama_host(mock_conn):
    """Le pull doit utiliser settings.ollama_url, pas localhost (bug Connection refused)."""
    client = MagicMock()
    client.pull.return_value = iter([MagicMock(status="success")])
    mock_conn.return_value = MagicMock()

    with patch.object(model_download.ollama, "Client", return_value=client) as mock_cls:
        model_download._pull_worker(make_settings(ollama_url="http://ollama:11434"))

    mock_cls.assert_called_once_with(host="http://ollama:11434")
    client.pull.assert_called_once_with("llama3.2", stream=True)
