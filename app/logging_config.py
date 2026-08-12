import logging
import sys

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "faster_whisper",
    "ctranslate2",
    "huggingface_hub",
    "fsspec",
    "openai",
)


def configure_logging(level: str = "INFO", *, force: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers and not force:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
