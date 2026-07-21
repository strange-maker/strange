from __future__ import annotations

from sqlalchemy.orm import Session

from adapters import build_adapter
from config import get_settings
from ingestion import ingest_item
from models import CrawlError, CrawlJob, CrawlRun, Source, utcnow
from source_service import next_run

settings=get_settings()


def execute_crawl(db: Session, source: Source, job: CrawlJob | None = None, retry_count: int = 0) -> CrawlRun:
    run=CrawlRun(source_id=source.id,crawl_job_id=job.id if job else None,status="running",retry_count=retry_count)
    db.add(run); db.flush()
    if job: job.status="running"
    db.commit()
    try:
        if source.adapter_status != "active" or not source.adapter_key:
            raise RuntimeError(f"source adapter is {source.adapter_status}")
        adapter=build_adapter(source.source_name,source.source_url,source.adapter_config)
        items=adapter.fetch_list(); run.fetched_count=len(items)
        for item in items:
            detailed=adapter.fetch_detail(item) if source.adapter_config.get("fetch_detail") else item
            result=ingest_item(db,source,detailed)
            if result == "new": run.new_count += 1
            elif result == "updated": run.updated_count += 1
            elif result == "duplicate": run.duplicate_count += 1
        run.status="success"; run.http_status=adapter.last_http_status; source.consecutive_failures=0; source.last_success_at=utcnow()
        if job: job.status="success"
    except Exception as exc:
        run.status="failed"; run.failure_reason=str(exc)[:2000]; source.consecutive_failures += 1; source.last_failure_at=utcnow()
        db.add(CrawlError(crawl_run_id=run.id,error_type=exc.__class__.__name__,message=str(exc)[:4000],details={"source":source.source_name}))
        if source.consecutive_failures >= settings.max_consecutive_failures:
            source.adapter_status="paused"
        if job: job.status="failed"
    finally:
        run.finished_at=utcnow(); source.next_run_at=next_run(source); run.next_run_at=source.next_run_at; db.commit(); db.refresh(run)
    return run
