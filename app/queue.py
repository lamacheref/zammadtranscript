import time

import redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from .config import Settings, get_settings


def get_redis_connection(settings: Settings | None = None) -> redis.Redis:
    settings = settings or get_settings()
    return redis.from_url(settings.redis_url, decode_responses=False)


def get_queue(settings: Settings | None = None) -> Queue:
    conn = get_redis_connection(settings)
    settings = settings or get_settings()
    return Queue(settings.rq_queue_name, connection=conn)


def enqueue_transcription(payload_dict: dict, settings: Settings | None = None) -> str:
    queue = get_queue(settings)
    job = queue.enqueue("app.queue.process_transcription_job", payload_dict, job_timeout="10m")
    return job.id


def wait_for_job(
    job_id: str, settings: Settings | None = None, timeout: int = 300, interval: float = 1.0
) -> dict:
    """Attend la fin d'un job RQ et retourne son résultat ou lève une exception."""
    conn = get_redis_connection(settings)
    start = time.time()
    while time.time() - start < timeout:
        try:
            job = Job.fetch(job_id, connection=conn)
            if job.is_finished:
                return job.result or {}
            if job.is_failed:
                raise RuntimeError(f"Job {job_id} échoué: {job.exc_info}")
        except NoSuchJobError:
            pass
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} n'a pas terminé dans les {timeout}s")


def process_transcription_job(payload_dict: dict) -> dict:
    from .config import get_settings
    from .models import WebhookPayload
    from .processor import Processor

    settings = get_settings()
    processor = Processor(settings)
    payload = WebhookPayload.model_validate(payload_dict)
    return processor.process(payload)
