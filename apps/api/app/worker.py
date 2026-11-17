"""Celery worker: `celery -A app.worker worker --concurrency 2 -Q crawl`.

Tasks carry only (tenant_id, job_id); the task re-establishes tenant context and re-validates the job
(it must exist in that tenant, be queued/running, and its domain must still be verified).
"""
import uuid
from typing import Any

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("aisv", broker=settings.redis_url or "redis://localhost:6379/0")
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_default_queue="crawl",
    task_acks_late=True,  # a crashed worker's job is redelivered and resumes from its persisted queue
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
)


@celery_app.task(bind=True, name="aisv.crawl", max_retries=60)  # type: ignore[untyped-decorator]
def crawl_task(self: Any, tenant_id: str, job_id: str) -> str:
    from app.crawl.crawler import run_crawl

    outcome = run_crawl(uuid.UUID(tenant_id), uuid.UUID(job_id))
    if outcome == "deferred":  # another crawl holds this host's politeness lock
        raise self.retry(countdown=60)
    return outcome
