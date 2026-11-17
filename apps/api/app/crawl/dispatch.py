import threading
import uuid

from app.core.config import get_settings


def dispatch_crawl(tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Hand a committed crawl job to the executor. Must be called AFTER the job row is committed."""
    mode = get_settings().crawl_execution
    if mode == "celery":
        from app.worker import crawl_task

        crawl_task.delay(str(tenant_id), str(job_id))
        return
    from app.crawl.crawler import run_crawl

    if mode == "sync":
        run_crawl(tenant_id, job_id)
    else:
        threading.Thread(target=run_crawl, args=(tenant_id, job_id), daemon=True, name=f"crawl-{job_id}").start()
