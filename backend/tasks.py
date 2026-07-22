from __future__ import annotations

import time
from urllib.parse import urlparse

from celery.utils.log import get_task_logger
from redis import Redis
from redis.exceptions import LockError
from sqlalchemy import select

from config import get_settings
from celery_app import celery
from crawl_service import execute_crawl
from database import SessionLocal
from models import CrawlJob, Source, utcnow

settings=get_settings()
redis_client=Redis.from_url(settings.redis_url,decode_responses=True)
logger=get_task_logger(__name__)


@celery.task(bind=True,max_retries=4,name="tasks.crawl_source")
def crawl_source(self,source_id: str,job_id: str | None=None):
    logger.info("crawl task received source_id=%s job_id=%s retry=%s",source_id,job_id,self.request.retries)
    with SessionLocal() as db:
        source=db.get(Source,source_id); job=db.get(CrawlJob,job_id) if job_id else None
        if not source:
            if job: job.status="failed"; db.commit()
            logger.warning("crawl source missing source_id=%s",source_id)
            return {"status":"missing"}
        if not source.enabled or source.crawl_method == "manual_import" or source.source_type == "wechat_manual" or source.adapter_status != "active":
            if job: job.status="failed"; db.commit()
            logger.warning("crawl source not runnable source=%s status=%s method=%s",source.source_name,source.adapter_status,source.crawl_method)
            return {"status":"not_runnable"}
        domain=urlparse(source.source_url).netloc
        lock=redis_client.lock(f"crawl:domain:{domain}",timeout=max(60,settings.crawl_timeout_seconds*3),blocking_timeout=5)
        if not lock.acquire(blocking=True):
            logger.info("domain lock busy domain=%s",domain)
            raise self.retry(countdown=min(900,60*(2**self.request.retries)))
        try:
            last_key=f"crawl:last:{domain}"; last=float(redis_client.get(last_key) or 0); wait=settings.crawl_domain_rate_seconds-(time.time()-last)
            if wait > 0: time.sleep(wait)
            result=execute_crawl(db,source,job,retry_count=self.request.retries); redis_client.set(last_key,time.time(),ex=3600)
            logger.info("crawl run finished source=%s run_id=%s status=%s fetched=%s new=%s",source.source_name,result.id,result.status,result.fetched_count,result.new_count)
            if result.status == "failed" and source.adapter_status != "paused":
                raise self.retry(exc=RuntimeError(result.failure_reason or "crawl failed"),countdown=min(1800,60*(2**self.request.retries)))
            return {"run_id":result.id,"status":result.status,"new_count":result.new_count}
        finally:
            try:
                if lock.owned(): lock.release()
            except LockError:
                logger.warning("domain lock expired before release domain=%s",domain)


@celery.task(name="tasks.dispatch_due_sources")
def dispatch_due_sources():
    """Dispatch due automatic sources once, even if two Beat processes briefly overlap."""
    singleton=redis_client.lock("scheduler:dispatch-due-sources",timeout=55,blocking_timeout=0)
    if not singleton.acquire(blocking=False):
        logger.warning("scheduler dispatch skipped because singleton lock is held")
        return {"queued":0,"skipped":"singleton_lock"}
    queued=0
    try:
        with SessionLocal() as db:
            sources=db.scalars(
                select(Source).where(
                    Source.enabled.is_(True),
                    Source.adapter_status == "active",
                    Source.crawl_method != "manual_import",
                    Source.source_type != "wechat_manual",
                    Source.next_run_at.is_not(None),
                    Source.next_run_at <= utcnow(),
                ).order_by(Source.next_run_at).limit(50)
            ).all()
            for source in sources:
                job=CrawlJob(source_id=source.id,trigger_type="schedule",status="queued"); db.add(job); db.flush()
                task=crawl_source.delay(source.id,job.id); job.celery_task_id=task.id; source.next_run_at=None; queued += 1
            db.commit()
        logger.info("scheduler dispatch complete queued=%s",queued)
        return {"queued":queued}
    finally:
        try:
            if singleton.owned(): singleton.release()
        except LockError:
            logger.warning("scheduler singleton lock expired before release")
