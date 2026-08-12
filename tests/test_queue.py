from unittest.mock import MagicMock, patch

from app.queue import get_queue, get_redis_connection


@patch("app.queue.redis.from_url")
def test_get_redis_connection(mock_from_url):
    get_redis_connection()
    assert mock_from_url.called


@patch("app.queue.get_redis_connection")
@patch("app.queue.Queue")
def test_get_queue(mock_queue_cls, mock_conn):
    mock_conn.return_value = "conn"
    mock_queue_cls.return_value = "queue"
    assert get_queue() == "queue"
    mock_queue_cls.assert_called_once_with("transcription", connection="conn")


@patch("app.queue.get_queue")
def test_enqueue_transcription(mock_get_queue):
    queue = MagicMock()
    queue.enqueue.return_value = MagicMock(id="job-abc")
    mock_get_queue.return_value = queue

    from app.queue import enqueue_transcription

    job_id = enqueue_transcription({"ticket": {}})

    assert job_id == "job-abc"
    queue.enqueue.assert_called_once()


def test_process_transcription_job(monkeypatch):
    import app.queue as queue_mod

    fake_processor = MagicMock()
    fake_processor.process.return_value = {"success": True}

    monkeypatch.setattr("app.config.get_settings", lambda: MagicMock())
    monkeypatch.setattr("app.processor.Processor", lambda settings: fake_processor)
    monkeypatch.setattr(
        "app.models.WebhookPayload",
        MagicMock(model_validate=MagicMock(return_value="payload")),
    )

    result = queue_mod.process_transcription_job({"ticket": {}})

    assert result == {"success": True}
    fake_processor.process.assert_called_once_with("payload")
