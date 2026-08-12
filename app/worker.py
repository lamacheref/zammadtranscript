import logging
import sys

from rq import Worker

from .config import get_settings
from .logging_config import configure_logging
from .queue import get_queue, get_redis_connection

logger = logging.getLogger("zammad-autotranscription-worker")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    conn = get_redis_connection(settings)
    queue = get_queue(settings)

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
