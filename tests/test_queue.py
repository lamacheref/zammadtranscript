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
    fake_processor.process.assert_called_once()
    assert fake_processor.process.call_args.args[0] == "payload"


@patch("app.queue.get_queue")
def test_enqueue_manual_transcription(mock_get_queue):
    queue = MagicMock()
    queue.enqueue.return_value = MagicMock(id="job-ui")
    mock_get_queue.return_value = queue

    from app.queue import enqueue_manual_transcription

    job_id = enqueue_manual_transcription(202608069400166)

    assert job_id == "job-ui"
    queue.enqueue.assert_called_once()
    args, kwargs = queue.enqueue.call_args
    assert args[0] == "app.queue.process_manual_job"
    assert args[1] == 202608069400166


def test_process_manual_job(monkeypatch):
    import app.queue as queue_mod

    fake_processor = MagicMock()
    fake_processor.process_manual.return_value = {"success": True, "steps": []}

    monkeypatch.setattr("app.config.get_settings", lambda: MagicMock())
    monkeypatch.setattr("app.processor.Processor", lambda settings: fake_processor)

    result = queue_mod.process_manual_job(6475)

    assert result == {"success": True, "steps": []}
    fake_processor.process_manual.assert_called_once()
    assert fake_processor.process_manual.call_args.args[0] == 6475


class _FakeJob:
    def __init__(self, state):
        self.state = state
        self.meta = {"steps": [{"step": "ticket", "status": "ok"}]}
        self.result = {"success": True, "ticket_id": 7}

    @property
    def is_finished(self):
        return self.state == "finished"

    @property
    def is_failed(self):
        return self.state == "failed"

    @property
    def is_started(self):
        return self.state == "running"


def test_get_job_status(monkeypatch):
    import app.queue as queue_mod

    monkeypatch.setattr(
        "app.queue.Job", MagicMock(fetch=MagicMock(return_value=_FakeJob("running")))
    )

    status = queue_mod.get_job_status("job-x")

    assert status == {
        "job_id": "job-x",
        "status": "running",
        "steps": [{"step": "ticket", "status": "ok"}],
        "result": {},
    }


def test_get_job_status_finished(monkeypatch):
    import app.queue as queue_mod

    monkeypatch.setattr(
        "app.queue.Job", MagicMock(fetch=MagicMock(return_value=_FakeJob("finished")))
    )

    status = queue_mod.get_job_status("job-x")

    assert status["status"] == "finished"
    assert status["result"] == {"success": True, "ticket_id": 7}
