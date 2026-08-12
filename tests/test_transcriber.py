from unittest.mock import MagicMock, patch

import pytest

from app.transcriber import Transcriber, TranscriptionError


def make_transcriber():
    settings = MagicMock()
    settings.whisper_model = "base"
    settings.whisper_device = "cpu"
    settings.whisper_compute_type = "int8"
    settings.whisper_cpu_threads = 8
    settings.whisper_language = None
    settings.zammad_timeout = 30
    return Transcriber(settings)


@patch("app.transcriber.subprocess.run")
def test_normalize_to_wav_success(mock_run, tmp_path):
    source = tmp_path / "a.mp3"
    target = tmp_path / "mono16k.wav"
    source.write_bytes(b"audio")
    mock_run.return_value = MagicMock()

    tr = make_transcriber()
    assert tr._normalize_to_wav(source, target) == target

    cmd = mock_run.call_args[0][0]
    assert "-ac" in cmd and "1" in cmd
    assert "-ar" in cmd and "16000" in cmd


@patch("app.transcriber.subprocess.run")
def test_normalize_to_wav_ffmpeg_failure(mock_run, tmp_path):
    source = tmp_path / "a.mp3"
    target = tmp_path / "mono16k.wav"
    source.write_bytes(b"audio")

    err = __import__("subprocess").CalledProcessError(1, "ffmpeg")
    err.stderr = b"error detail"
    mock_run.side_effect = err

    tr = make_transcriber()
    with pytest.raises(TranscriptionError):
        tr._normalize_to_wav(source, target)


def test_transcribe_success(tmp_path, monkeypatch):
    tr = make_transcriber()

    class _Seg:
        text = "Bonjour"

    fake_wav = tmp_path / "mono16k.wav"
    fake_wav.write_bytes(b"RIFF")

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([_Seg(), _Seg()], None)
    tr._model = mock_model

    with patch.object(tr, "_normalize_to_wav", return_value=fake_wav):
        result = tr.transcribe(b"audio", filename="voicemail.mp3")

    assert result == "Bonjour Bonjour"


def test_transcribe_empty_wav(tmp_path):
    tr = make_transcriber()
    fake_wav = tmp_path / "mono16k.wav"

    with patch.object(tr, "_normalize_to_wav", return_value=fake_wav):
        with pytest.raises(TranscriptionError):
            tr.transcribe(b"audio")


def test_model_lazy_loading():
    import app.transcriber as mod

    tr = make_transcriber()
    assert tr._model is None
    with patch.object(mod, "WhisperModel") as mock_cls:
        mock_cls.return_value = "model-instance"
        assert tr.model == "model-instance"
        assert tr._model == "model-instance"
        mock_cls.assert_called_once()
