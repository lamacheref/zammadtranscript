import logging
import sys

from rq import Worker

from .config import get_settings
from .logging_config import configure_logging
from .model_download import ensure_ollama_model_in_background
from .queue import get_queue, get_redis_connection

logger = logging.getLogger("zammad-autotranscription-worker")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    conn = get_redis_connection(settings)
    queue = get_queue(settings)

    # Télécharge le modèle Ollama au démarrage (dédupliqué si l'API le fait déjà) :
    # garantit que le webhook peut traiter sans erreur dès le premier ticket.
    ensure_ollama_model_in_background(settings)

    logger.info(
        "Démarrage worker RQ sur queue '%s' (Redis: %s)", settings.rq_queue_name, settings.redis_url
    )

    worker = Worker([queue], connection=conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Arrêt worker")
        sys.exit(0)
