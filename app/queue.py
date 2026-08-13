import time

import redis
from rq import Queue, get_current_job
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


def enqueue_manual_transcription(ticket_input: int | str, settings: Settings | None = None) -> str:
    queue = get_queue(settings)
    job = queue.enqueue(
        "app.queue.process_manual_job",
        ticket_input,
        job_timeout="10m",
    )
    return job.id


def _record_progress(job, name: str, entry: dict) -> None:
    if job is None:
        return
    steps = [s for s in job.meta.get("steps", []) if s.get("step") != name]
    job.meta["steps"] = steps + [entry]
    job.save_meta()


def _progress_callback(job):
    return lambda name, entry: _record_progress(job, name, entry)


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


def get_job_status(job_id: str, settings: Settings | None = None) -> dict:
    """État d'un job pour l'UI : statut global + étapes intermédiaires."""
    conn = get_redis_connection(settings)
    try:
        job = Job.fetch(job_id, connection=conn)
    except NoSuchJobError:
        return {"job_id": job_id, "status": "unknown"}

    if job.is_finished:
        status = "finished"
    elif job.is_failed:
        status = "failed"
    elif job.is_started:
        status = "running"
    else:
        status = "queued"

    result = job.result if job.is_finished else {}
    return {
        "job_id": job_id,
        "status": status,
        "steps": job.meta.get("steps", []),
        "result": result,
    }


def process_transcription_job(payload_dict: dict) -> dict:
    from .config import get_settings
    from .models import WebhookPayload
    from .processor import Processor

    settings = get_settings()
    processor = Processor(settings)
    payload = WebhookPayload.model_validate(payload_dict)
    return processor.process(payload, progress=_progress_callback(get_current_job()))


def process_manual_job(ticket_input: int | str) -> dict:
    from .config import get_settings
    from .processor import Processor

    settings = get_settings()
    processor = Processor(settings)
    return processor.process_manual(ticket_input, progress=_progress_callback(get_current_job()))
