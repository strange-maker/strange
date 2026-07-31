from __future__ import annotations

import time
from datetime import timezone
from urllib.parse import urlparse

from celery.utils.log import get_task_logger
from redis import Redis
from redis.exceptions import LockError
from sqlalchemy import func, select

from adapters import build_adapter
from config import get_settings
from celery_app import celery
from crawl_service import execute_crawl
from database import SessionLocal
from ingestion import ingest_item
from models import BackfillCheckpoint, BackfillRun, CrawlBatch, CrawlBatchItem, CrawlJob, CrawlRun, Source, utcnow
from cscec import capture_page_snapshot, reconcile_discovered_entities, sync_cscec_entities

settings=get_settings()
redis_client=Redis.from_url(settings.redis_url,decode_responses=True)
logger=get_task_logger(__name__)


@celery.task(bind=True,max_retries=4,name="tasks.crawl_source")
def crawl_source(self,source_id: str,job_id: str | None=None,batch_item_id: str | None=None):
    logger.info("crawl task received source_id=%s job_id=%s retry=%s",source_id,job_id,self.request.retries)
    with SessionLocal() as db:
        source=db.get(Source,source_id); job=db.get(CrawlJob,job_id) if job_id else None
        batch_item=db.get(CrawlBatchItem,batch_item_id) if batch_item_id else None
        if batch_item:
            batch_item.status="running"; batch_item.started_at=utcnow()
            batch=db.get(CrawlBatch,batch_item.batch_id)
            if batch and batch.status == "queued": batch.status="running"; batch.started_at=utcnow()
            db.commit()
        if not source:
            if job: job.status="failed"
            if batch_item: batch_item.status="failed"; batch_item.failure_reason="source missing"; batch_item.finished_at=utcnow()
            db.commit()
            if batch_item: _refresh_batch(db,batch_item.batch_id)
            logger.warning("crawl source missing source_id=%s",source_id)
            return {"status":"missing"}
        if not source.enabled or source.crawl_method == "manual_import" or source.source_type == "wechat_manual" or source.adapter_status != "active":
            if job: job.status="failed"
            if batch_item: batch_item.status="skipped"; batch_item.skip_reason="source is not runnable"; batch_item.finished_at=utcnow()
            db.commit()
            if batch_item: _refresh_batch(db,batch_item.batch_id)
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
            should_retry=result.status == "failed" and source.adapter_status != "paused" and self.request.retries < self.max_retries
            if batch_item:
                batch_item.status="retrying" if should_retry else ("empty" if result.status == "success" and result.fetched_count == 0 else result.status)
                batch_item.failure_reason=result.failure_reason
                batch_item.finished_at=None if should_retry else utcnow()
                db.commit(); _refresh_batch(db,batch_item.batch_id)
            logger.info("crawl run finished source=%s run_id=%s status=%s fetched=%s new=%s",source.source_name,result.id,result.status,result.fetched_count,result.new_count)
            if should_retry:
                raise self.retry(exc=RuntimeError(result.failure_reason or "crawl failed"),countdown=min(1800,60*(2**self.request.retries)))
            return {"run_id":result.id,"status":result.status,"new_count":result.new_count}
        finally:
            try:
                if lock.owned(): lock.release()
            except LockError:
                logger.warning("domain lock expired before release domain=%s",domain)


def _refresh_batch(db,batch_id: str) -> None:
    batch=db.get(CrawlBatch,batch_id)
    if not batch: return
    items=db.scalars(select(CrawlBatchItem).where(CrawlBatchItem.batch_id == batch_id)).all()
    runs=db.execute(
        select(func.coalesce(func.sum(CrawlRun.new_count),0),func.coalesce(func.sum(CrawlRun.updated_count),0),func.coalesce(func.sum(CrawlRun.duplicate_count),0))
        .join(CrawlJob,CrawlRun.crawl_job_id == CrawlJob.id)
        .join(CrawlBatchItem,CrawlBatchItem.crawl_job_id == CrawlJob.id)
        .where(CrawlBatchItem.batch_id == batch_id)
    ).one()
    terminal={"success","empty","failed","skipped","cancelled"}
    batch.completed_count=sum(x.status in terminal for x in items)
    batch.success_count=sum(x.status == "success" for x in items)
    batch.empty_count=sum(x.status == "empty" for x in items)
    batch.failed_count=sum(x.status == "failed" for x in items)
    batch.skipped_count=sum(x.status in {"skipped","cancelled"} for x in items)
    batch.new_count=int(runs[0] or 0); batch.updated_count=int(runs[1] or 0); batch.duplicate_count=int(runs[2] or 0)
    if items and batch.completed_count == len(items):
        batch.status="cancelled" if batch.cancel_requested else ("completed_with_errors" if batch.failed_count else "completed")
        batch.finished_at=utcnow(); batch.singleton_key=None
    db.commit()


@celery.task(bind=True,max_retries=3,name="tasks.backfill_source")
def backfill_source(self,run_id: str):
    with SessionLocal() as db:
        run=db.get(BackfillRun,run_id)
        if not run: return {"status":"missing"}
        source=db.get(Source,run.source_id)
        if not source or source.adapter_status != "active" or not source.adapter_key:
            run.status="failed"; run.failure_reason="source does not have an active adapter"
            if source: source.backfill_status="failed"
            db.commit(); return {"status":"failed"}
        run.status="running"; run.started_at=run.started_at or utcnow(); source.backfill_status="running"; db.commit()
        try:
            adapter=build_adapter(source.source_name,source.source_url,source.adapter_config)
            cursor=run.cursor or source.backfill_cursor
            page=run.current_page + 1
            date_from=run.date_from.replace(tzinfo=timezone.utc) if run.date_from.tzinfo is None else run.date_from.astimezone(timezone.utc)
            date_to=run.date_to.replace(tzinfo=timezone.utc) if run.date_to.tzinfo is None else run.date_to.astimezone(timezone.utc)
            reached_start=False
            while page <= run.page_limit:
                db.refresh(run)
                if run.status in {"paused","cancelled"}:
                    source.backfill_status=run.status; db.commit()
                    return {"status":run.status,"page":run.current_page}
                result=adapter.fetch_backfill(page=page,cursor=cursor)
                oldest=None; page_fetched=0
                for item in result.items:
                    page_fetched += 1; run.fetched_count += 1
                    if item.published_at is None:
                        run.date_unverified_count += 1
                        outcome=ingest_item(db,source,item)
                    else:
                        published=item.published_at.replace(tzinfo=timezone.utc) if item.published_at.tzinfo is None else item.published_at.astimezone(timezone.utc)
                        oldest=min(filter(None,[oldest,published]),default=published)
                        if published < date_from:
                            reached_start=True; continue
                        if published > date_to: continue
                        outcome=ingest_item(db,source,item)
                    if outcome == "new": run.new_count += 1
                    elif outcome == "duplicate": run.duplicate_count += 1
                run.current_page=page; run.cursor=result.next_cursor; source.backfill_cursor=result.next_cursor
                db.add(BackfillCheckpoint(backfill_run_id=run.id,page_number=page,cursor=result.next_cursor,oldest_published_at=oldest,fetched_count=page_fetched))
                db.commit()
                if result.exhausted or reached_start: break
                page += 1; cursor=result.next_cursor
            run.status="completed"; run.finished_at=utcnow()
            source.backfill_status="completed"; source.last_backfill_at=run.finished_at; source.backfill_cursor=None
            db.commit()
            return {"status":"completed","pages":run.current_page,"new_count":run.new_count,"date_unverified_count":run.date_unverified_count}
        except Exception as exc:
            if self.request.retries < self.max_retries:
                run.status="retrying"; run.failure_reason=str(exc)[:2000]; source.backfill_status="retrying"; db.commit()
                raise self.retry(exc=exc,countdown=min(1800,60*(2**self.request.retries)))
            run.status="failed"; run.failure_reason=str(exc)[:2000]; source.backfill_status="failed"; db.commit()
            return {"status":"failed","reason":run.failure_reason}


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


@celery.task(name="tasks.sync_cscec_entities")
def sync_cscec_entity_master():
    """Sync the reviewed master and compare the official organization page."""
    singleton=redis_client.lock("scheduler:sync-cscec-entities",timeout=1800,blocking_timeout=0)
    if not singleton.acquire(blocking=False):
        return {"status":"skipped","reason":"singleton_lock"}
    try:
        with SessionLocal() as db:
            master_count=sync_cscec_entities(db)
            source=db.scalar(select(Source).where(Source.source_name == "中国建筑组织架构"))
            if not source:
                return {"status":"master_only","master_count":master_count,"reason":"organization source missing"}
            adapter=build_adapter(source.source_name,source.source_url,source.adapter_config)
            items=adapter.fetch_list()
            capture_page_snapshot(
                db,
                source.source_url,
                adapter.last_html,
                "organization",
                entity_id=source.entity_id,
                source_id=source.id,
            )
            discovered=[
                {
                    "canonical_name":item.raw.get("canonical_name"),
                    "official_url":item.raw.get("official_url"),
                }
                for item in items
                if item.raw.get("entity_discovery")
            ]
            stats=reconcile_discovered_entities(db,discovered)
            logger.info("CSCEC entity sync complete master=%s discovered=%s stats=%s",master_count,len(discovered),stats)
            return {"status":"completed","master_count":master_count,"discovered_count":len(discovered),**stats}
    finally:
        try:
            if singleton.owned(): singleton.release()
        except LockError:
            logger.warning("CSCEC entity sync singleton lock expired before release")
