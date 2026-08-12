from unittest.mock import MagicMock, patch


def test_worker_main_logs_and_works(tmp_path, monkeypatch):
    from app import worker

    settings_mock = MagicMock()
    settings_mock.log_level = "INFO"
    settings_mock.rq_queue_name = "transcription"
    settings_mock.redis_url = "redis://localhost:6379"

    with (
        patch("app.worker.get_settings", return_value=settings_mock),
        patch("app.worker.get_redis_connection", return_value="conn"),
        patch("app.worker.get_queue", return_value="queue"),
        patch("app.worker.configure_logging") as mock_cfg,
        patch("app.worker.Worker") as mock_worker,
    ):
        mock_worker.return_value.work.return_value = None
        worker.main()

    mock_cfg.assert_called_once_with("INFO")
    mock_worker.assert_called_once_with(["queue"], connection="conn")
