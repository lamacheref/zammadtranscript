import logging

from app.logging_config import configure_logging


def test_configure_logging_restricts_noisy_loggers():
    configure_logging("DEBUG", force=True)

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("faster_whisper").level == logging.WARNING


def test_configure_logging_is_idempotent():
    configure_logging("WARNING", force=True)
    before = logging.getLogger().handlers[:]

    configure_logging("INFO")

    assert logging.getLogger().handlers == before
