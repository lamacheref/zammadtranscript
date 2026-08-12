import redis
from rq import Queue

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


def process_transcription_job(payload_dict: dict) -> dict:
    from .config import get_settings
    from .models import WebhookPayload
    from .processor import Processor

    settings = get_settings()
    processor = Processor(settings)
    payload = WebhookPayload.model_validate(payload_dict)
    return processor.process(payload)
