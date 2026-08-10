import subprocess
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

from .config import Settings


class TranscriptionError(Exception):
    pass


class Transcriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: WhisperModel | None = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
                cpu_threads=self.settings.whisper_cpu_threads,
            )
        return self._model

    def transcribe(self, audio_bytes: bytes, filename: str = "audio") -> str:
        ext = Path(filename).suffix.lower() or ".wav"
        with tempfile.TemporaryDirectory(prefix="zat-") as tmpdir:
            source = Path(tmpdir) / f"source{ext}"
            source.write_bytes(audio_bytes)
            wav = self._normalize_to_wav(source, Path(tmpdir) / "mono16k.wav")

            if not wav.is_file() or wav.stat().st_size == 0:
                raise TranscriptionError(
                    "Prétraitement ffmpeg n'a produit aucun audio exploitable."
                )

            segments, _info = self.model.transcribe(
                str(wav),
                language=self.settings.whisper_language,
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

    def _normalize_to_wav(self, source: Path, target: Path) -> Path:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=self.settings.zammad_timeout * 2,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = getattr(exc, "stderr", b"").decode(errors="replace")[-500:]
            raise TranscriptionError(f"ffmpeg a échoué sur {source.name}: {detail}") from exc
        return target