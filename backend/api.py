from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
import requests
from sqlalchemy import String, and_, distinct, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from adapters.base import SourceItem
from celery_app import celery
from config import get_settings
from database import SessionLocal, engine, get_db
from ingestion import ingest_item
from models import (
    Article, ArticleSource, AuditLog, BackfillCheckpoint, BackfillRun, Base,
    CanonicalEvent, CanonicalProject, CrawlBatch, CrawlBatchItem, CrawlError,
    CrawlJob, CrawlRun, CSCECEntity, CSCECLeadershipEvent, CSCECOrgEvent,
    EventSource, KAEntity, KAGroup, KALeaderEvent, PageDiff,
    PolicyIntelligence, RefreshToken, ReviewRecord, Role, SavedSearch, Source,
    SourceCapabilityCheck, User, UserFavorite, UserReadStatus, utcnow,
)
from schemas import BackfillCreate, CSCECBackfillCreate, CSCECCrawlCreate, CrawlBatchCreate, LoginRequest, ManualExtractRequest, ManualImport, RefreshRequest, ReviewRequest, SavedSearchCreate, SourceUpdate, TokenResponse, UserCreate, UserUpdate
from security import _as_utc, audit, consume_refresh_token, create_access_token, current_user, hash_password, issue_refresh_token, require_role, verify_password
from source_service import ensure_roles, sync_ka_mappings, sync_sources
from cscec import sync_cscec_entities

settings=get_settings(); router=APIRouter(prefix="/api")


def user_payload(user: User) -> dict:
    return {"id":user.id,"email":user.email,"full_name":user.full_name,"role":user.role.name,"is_active":user.is_active}


def token_payload(db: Session,user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user),refresh_token=issue_refresh_token(db,user),expires_in=settings.access_token_minutes*60,user=user_payload(user))


@router.post("/auth/login",response_model=TokenResponse)
def login(payload: LoginRequest,request: Request,db: Session=Depends(get_db)):
    user=db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user and user.locked_until and _as_utc(user.locked_until) > utcnow():
        audit(db,request,user,"auth.login_locked"); raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,"account temporarily locked")
    if not user or not user.is_active or not verify_password(payload.password,user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= 5: user.locked_until=utcnow()+timedelta(minutes=15)
            db.commit()
        audit(db,request,user,"auth.login_failed"); raise HTTPException(status.HTTP_401_UNAUTHORIZED,"email or password incorrect")
    user.failed_login_count=0; user.locked_until=None; user.last_login_at=utcnow(); db.commit(); audit(db,request,user,"auth.login")
    return token_payload(db,user)


@router.post("/auth/refresh",response_model=TokenResponse)
def refresh(payload: RefreshRequest,db: Session=Depends(get_db)):
    return token_payload(db,consume_refresh_token(db,payload.refresh_token))


@router.post("/auth/logout",status_code=204)
def logout(payload: RefreshRequest,user: User=Depends(current_user),db: Session=Depends(get_db)):
    import hashlib
    digest=hashlib.sha256(payload.refresh_token.encode()).hexdigest(); token=db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest,RefreshToken.user_id == user.id))
    if token: token.revoked_at=utcnow(); db.commit()


@router.get("/auth/me")
def me(user: User=Depends(current_user)): return user_payload(user)


@router.get("/users")
def list_users(_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    return [user_payload(x) | {"last_login_at":x.last_login_at} for x in db.scalars(select(User).order_by(User.created_at)).all()]


@router.post("/users",status_code=201)
def create_user(payload: UserCreate,request: Request,admin: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == payload.email.lower())): raise HTTPException(409,"email already exists")
    role=db.scalar(select(Role).where(Role.name == payload.role)); user=User(email=payload.email.lower(),full_name=payload.full_name,password_hash=hash_password(payload.password),role_id=role.id)
    db.add(user); db.commit(); db.refresh(user); audit(db,request,admin,"user.create","user",user.id,{"role":payload.role}); return user_payload(user)


@router.patch("/users/{user_id}")
def update_user(user_id: str,payload: UserUpdate,request: Request,admin: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    user=db.get(User,user_id)
    if not user: raise HTTPException(404,"user not found")
    if payload.is_active is not None: user.is_active=payload.is_active
    if payload.role: user.role_id=db.scalar(select(Role).where(Role.name == payload.role)).id
    db.commit(); db.refresh(user); audit(db,request,admin,"user.update","user",user.id,payload.model_dump(exclude_none=True)); return user_payload(user)


def serialize_article(article: Article, favorite=False, read=False) -> dict[str,Any]:
    return {"id":article.id,"title":article.title,"original_title":article.original_title,"summary":article.summary,"sales_insight":article.sales_insight,"original_url":article.original_url,"canonical_url":article.canonical_url,"source_name":article.source_name,"source_type":article.source_type,"reliability_level":article.reliability_level,"source_reliability":article.reliability_level,"published_at":article.published_at,"fetched_at":article.fetched_at,"first_seen_at":article.first_seen_at,"last_seen_at":article.last_seen_at,"content_excerpt":article.content_excerpt,"language":article.language,"country":article.country,"region":article.region,"ka":article.ka,"subsidiary":article.subsidiary,"industries":article.industries,"intelligence_types":article.intelligence_types,"matched_entities":article.matched_entities,"ka_candidates":article.ka_candidates,"date_verification_status":article.date_verification_status,"canonical_event_id":article.canonical_event_id,"project_type":article.project_type,"project_stage":article.project_stage,"project_value":float(article.project_value) if article.project_value is not None else None,"currency":article.currency,"overseas_evidence":article.overseas_evidence,"ka_match_evidence":article.ka_match_evidence,"confidence_score":article.confidence_score,"verification_status":article.verification_status,"cross_source_count":article.cross_source_count,"is_primary_source":article.is_primary_source,"review_status":article.review_status,"ai_payload":article.ai_payload,"favorite":favorite,"read":read,"verification_notice":None if article.reliability_level == "high" else "媒体线索，建议核验官方公告"}


def _date_value(value: str | None,end_of_day: bool=False) -> datetime | None:
    if not value: return None
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise HTTPException(422,"dates must be ISO-8601") from exc
    if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=timezone.utc)
    if end_of_day and len(value) <= 10: parsed=parsed+timedelta(days=1)-timedelta(microseconds=1)
    return parsed.astimezone(timezone.utc)


def _article_order(sort: str):
    order={
        "published_desc":func.coalesce(Article.published_at,Article.fetched_at).desc(),
        "published_asc":func.coalesce(Article.published_at,Article.fetched_at).asc(),
        "confidence_desc":Article.confidence_score.desc(),
    }.get(sort)
    if order is None: raise HTTPException(422,"unsupported sort")
    return order


@router.get("/articles")
def articles(q: str | None=None,date_from: str | None=None,date_to: str | None=None,region: str | None=None,country: str | None=None,industry: str | None=None,intelligence_type: str | None=None,policy_type: str | None=None,ka_group: str | None=None,matched_entity: str | None=None,source: str | None=None,ka: str | None=None,source_type: str | None=None,reliability: str | None=None,review_status: str | None=None,verification_status: str | None=None,from_fetched_at: str | None=None,include_archive: bool=False,page: int=Query(1,ge=1),page_size: int=Query(50,ge=1,le=200),sort: str="published_desc",limit: int | None=Query(None,ge=1,le=200),offset: int | None=Query(None,ge=0),user: User=Depends(current_user),db: Session=Depends(get_db)):
    stmt=select(Article).where(Article.is_overseas.is_(True),Article.is_demo.is_(False))
    start=_date_value(date_from) if date_from else (None if include_archive and user.role.name == "admin" else utcnow()-timedelta(days=365))
    end=_date_value(date_to,True) if date_to else utcnow()
    if start: stmt=stmt.where(Article.published_at.is_not(None),Article.published_at >= start)
    if end: stmt=stmt.where(or_(Article.published_at.is_(None) if include_archive and user.role.name == "admin" else text("false"),Article.published_at <= end))
    if q:
        if settings.database_url.startswith("postgresql"):
            vector=func.to_tsvector("simple",func.coalesce(Article.title,"")+" "+func.coalesce(Article.summary,"")+" "+func.coalesce(Article.content_excerpt,""))
            stmt=stmt.where(or_(vector.op("@@")(func.plainto_tsquery("simple",q)),func.similarity(Article.title,q) > .2))
        else: stmt=stmt.where(or_(Article.title.ilike(f"%{q}%"),Article.summary.ilike(f"%{q}%"),Article.content_excerpt.ilike(f"%{q}%"),Article.country.ilike(f"%{q}%"),Article.region.ilike(f"%{q}%")))
    if country: stmt=stmt.where(Article.country == country)
    if region: stmt=stmt.where(Article.region == region)
    if industry: stmt=stmt.where(Article.industries.cast(String).ilike(f"%{industry}%"))
    if intelligence_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{intelligence_type}%"))
    if policy_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{policy_type}%"))
    if ka_group or ka: stmt=stmt.where(Article.ka.cast(String).ilike(f"%{ka_group or ka}%"))
    if matched_entity: stmt=stmt.where(Article.matched_entities.cast(String).ilike(f"%{matched_entity}%"))
    if source: stmt=stmt.where(Article.source_name == source)
    if source_type: stmt=stmt.where(Article.source_type == source_type)
    if reliability: stmt=stmt.where(Article.reliability_level == reliability)
    if review_status: stmt=stmt.where(Article.review_status == review_status)
    if verification_status: stmt=stmt.where(Article.verification_status == verification_status)
    if from_fetched_at:
        try:
            from datetime import datetime
            stmt=stmt.where(Article.fetched_at >= datetime.fromisoformat(from_fetched_at.replace("Z", "+00:00")))
        except ValueError:
            raise HTTPException(422, "from_fetched_at must be ISO-8601")
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    effective_size=limit or page_size
    effective_offset=offset if offset is not None else (page-1)*effective_size
    rows=db.scalars(stmt.order_by(_article_order(sort)).offset(effective_offset).limit(effective_size)).all()
    favorites=set(db.scalars(select(UserFavorite.article_id).where(UserFavorite.user_id == user.id)).all()); reads=set(db.scalars(select(UserReadStatus.article_id).where(UserReadStatus.user_id == user.id)).all())
    return {"items":[serialize_article(x,x.id in favorites,x.id in reads) for x in rows],"count":total,"page":effective_offset//effective_size+1,"page_size":effective_size,"limit":effective_size,"offset":effective_offset,"date_from":start,"date_to":end,"archive_included":bool(include_archive and user.role.name == "admin")}


@router.get("/articles/{article_id}")
def article(article_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    row=db.get(Article,article_id)
    if not row: raise HTTPException(404,"article not found")
    favorite=db.get(UserFavorite,(user.id,article_id)) is not None; read=db.get(UserReadStatus,(user.id,article_id)) is not None
    payload=serialize_article(row,favorite,read)
    payload["supporting_sources"]=[{"source_id":x.source_id,"title":x.title,"original_url":x.original_url,"published_at":x.published_at,"reliability_level":x.reliability_level,"is_primary":x.is_primary,"source_role":x.source_role,"consistency_status":x.consistency_status} for x in db.scalars(select(ArticleSource).where(ArticleSource.article_id == article_id).order_by(ArticleSource.is_primary.desc())).all()]
    if row.canonical_event_id:
        event=db.get(CanonicalEvent,row.canonical_event_id)
        payload["canonical_event"]={"id":event.id,"title":event.title,"event_type":event.event_type,"source_count":event.source_count,"official_source_count":event.official_source_count,"verification_status":event.verification_status,"conflict_status":event.conflict_status} if event else None
    return payload


@router.post("/articles/manual-import",status_code=201)
def manual_import(payload: ManualImport,request: Request,user: User=Depends(require_role("analyst")),db: Session=Depends(get_db)):
    source=db.scalar(select(Source).where(Source.source_name == payload.source_name))
    if payload.import_type == "wechat":
        if not source or source.adapter_status != "manual_only" or source.source_type != "wechat_manual":
            raise HTTPException(400,"wechat imports must use a configured wechat_manual source")
    elif not source:
        source=Source(source_name=payload.source_name,source_url=str(payload.original_url),source_type="media",reliability_level="low",region_focus=[],country_focus=[],industry_focus=[payload.industry] if payload.industry else [],crawl_method="manual_import",adapter_status="manual_only",enabled=True,notes="用户手动导入的网页来源；关键事实必须核验官方来源。")
        db.add(source); db.flush()
    published_at=payload.published_at
    if published_at:
        published_at=published_at.replace(tzinfo=timezone.utc) if published_at.tzinfo is None else published_at.astimezone(timezone.utc)
    item=SourceItem(title=payload.title,url=str(payload.original_url),published_at=published_at,excerpt=(payload.content_text+" "+(payload.ocr_result or ""))[:6000],language="zh")
    result=ingest_item(db,source,item,True); db.commit(); audit(db,request,user,"article.manual_import","source",source.id,{"result":result})
    return {"result":result,"source_type":source.source_type,"verification_notice":"媒体线索，建议核验官方公告" if source.reliability_level != "high" else None}


@router.post("/articles/manual-import/preview")
def manual_import_preview(payload: ManualExtractRequest,user: User=Depends(require_role("analyst"))):
    from manual_extract import extract_public_article
    try:
        return extract_public_article(str(payload.original_url),payload.import_type)
    except PermissionError as exc:
        raise HTTPException(403,str(exc)) from exc
    except (ValueError,requests.RequestException) as exc:
        raise HTTPException(422,str(exc)) from exc


@router.put("/articles/{article_id}/favorite")
def favorite(article_id: str,user: User=Depends(require_role("sales")),db: Session=Depends(get_db)):
    if not db.get(Article,article_id): raise HTTPException(404,"article not found")
    if not db.get(UserFavorite,(user.id,article_id)): db.add(UserFavorite(user_id=user.id,article_id=article_id)); db.commit()
    return {"favorite":True}


@router.delete("/articles/{article_id}/favorite")
def unfavorite(article_id: str,user: User=Depends(require_role("sales")),db: Session=Depends(get_db)):
    row=db.get(UserFavorite,(user.id,article_id))
    if row: db.delete(row); db.commit()
    return {"favorite":False}


@router.put("/articles/{article_id}/read")
def mark_read(article_id: str,user: User=Depends(require_role("sales")),db: Session=Depends(get_db)):
    if not db.get(Article,article_id): raise HTTPException(404,"article not found")
    if not db.get(UserReadStatus,(user.id,article_id)): db.add(UserReadStatus(user_id=user.id,article_id=article_id)); db.commit()
    return {"read":True}


@router.post("/articles/{article_id}/review")
def review(article_id: str,payload: ReviewRequest,request: Request,user: User=Depends(require_role("analyst")),db: Session=Depends(get_db)):
    article=db.get(Article,article_id)
    if not article: raise HTTPException(404,"article not found")
    before={"review_status":article.review_status}; article.review_status={"approve":"approved","reject":"rejected","needs_changes":"needs_changes"}[payload.action]
    db.add(ReviewRecord(article_id=article.id,reviewer_id=user.id,action=payload.action,notes=payload.notes,before_data=before,after_data={"review_status":article.review_status})); db.commit(); audit(db,request,user,"article.review","article",article.id,{"action":payload.action}); return {"review_status":article.review_status}


@router.get("/sources")
def sources(_: User=Depends(current_user),db: Session=Depends(get_db)):
    result=[]
    for source in db.scalars(select(Source).order_by(Source.source_name)).all():
        run=db.scalar(select(CrawlRun).where(CrawlRun.source_id == source.id).order_by(CrawlRun.started_at.desc()).limit(1))
        result.append({"id":source.id,"source_name":source.source_name,"source_url":source.source_url,"source_type":source.source_type,"source_tags":source.source_tags,"entity_id":source.entity_id,"reliability_level":source.reliability_level,"crawl_method":source.crawl_method,"adapter_status":source.adapter_status,"schedule_minutes":source.schedule_minutes,"enabled":source.enabled,"region_focus":source.region_focus,"country_focus":source.country_focus,"industry_focus":source.industry_focus,"notes":source.notes,"last_success_at":source.last_success_at,"last_failure_at":source.last_failure_at,"consecutive_failures":source.consecutive_failures,"next_run_at":source.next_run_at,"backfill_enabled":source.backfill_enabled,"backfill_start_date":source.backfill_start_date,"backfill_end_date":source.backfill_end_date,"backfill_page_limit":source.backfill_page_limit,"backfill_status":source.backfill_status,"backfill_cursor":source.backfill_cursor,"last_backfill_at":source.last_backfill_at,"latest_fetched_count":run.fetched_count if run else 0,"latest_new_count":run.new_count if run else 0,"latest_updated_count":run.updated_count if run else 0,"latest_duplicate_count":run.duplicate_count if run else 0,"latest_skipped_count":max(0,run.fetched_count-run.new_count-run.updated_count-run.duplicate_count) if run else 0,"latest_status":run.status if run else "never","latest_failure_reason":run.failure_reason if run else None})
    return result


@router.patch("/sources/{source_id}")
def update_source(source_id: str,payload: SourceUpdate,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"source not found")
    if payload.enabled is not None:
        if payload.enabled and source.adapter_status not in {"active","manual_only","paused"}: raise HTTPException(400,"source has no runnable adapter")
        source.enabled=payload.enabled
        if payload.enabled and source.adapter_status == "paused": source.adapter_status="active"; source.consecutive_failures=0
    if payload.schedule_minutes is not None: source.schedule_minutes=payload.schedule_minutes
    if payload.backfill_enabled is not None: source.backfill_enabled=payload.backfill_enabled
    if payload.backfill_page_limit is not None: source.backfill_page_limit=payload.backfill_page_limit
    db.commit(); audit(db,request,user,"source.update","source",source.id,payload.model_dump(exclude_none=True)); return {"id":source.id,"enabled":source.enabled,"schedule_minutes":source.schedule_minutes}


@router.post("/sources/{source_id}/run",status_code=202)
def run_source(source_id: str,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source or source.adapter_status != "active" or not source.enabled: raise HTTPException(400,"source is not runnable")
    job=CrawlJob(source_id=source.id,requested_by=user.id,trigger_type="manual",status="queued"); db.add(job); db.commit(); db.refresh(job)
    try:
        task=celery.send_task("tasks.crawl_source",args=[source.id,job.id]); job.celery_task_id=task.id; db.commit()
    except Exception as exc:
        job.status="queue_failed"; db.commit(); raise HTTPException(503,f"worker queue unavailable: {exc}")
    audit(db,request,user,"crawl.run","source",source.id,{"job_id":job.id}); return {"job_id":job.id,"status":"queued"}


@router.get("/sources/{source_id}/runs")
def source_runs(source_id: str,_: User=Depends(require_role("analyst")),db: Session=Depends(get_db)):
    return [{"id":r.id,"started_at":r.started_at,"finished_at":r.finished_at,"status":r.status,"fetched_count":r.fetched_count,"new_count":r.new_count,"updated_count":r.updated_count,"duplicate_count":r.duplicate_count,"http_status":r.http_status,"retry_count":r.retry_count,"failure_reason":r.failure_reason,"next_run_at":r.next_run_at} for r in db.scalars(select(CrawlRun).where(CrawlRun.source_id == source_id).order_by(CrawlRun.started_at.desc()).limit(100)).all()]


@router.get("/dashboard/status")
def dashboard_status(_: User=Depends(current_user),db: Session=Depends(get_db)):
    latest=db.scalar(select(CrawlRun).where(CrawlRun.status == "success").order_by(CrawlRun.finished_at.desc()).limit(1)); running=db.scalar(select(func.count()).select_from(CrawlRun).where(CrawlRun.status == "running")) or 0
    failures=db.scalar(select(func.count()).select_from(Source).where(Source.consecutive_failures > 0,Source.enabled.is_(True))) or 0
    delay_minutes=int((utcnow()-_as_utc(latest.finished_at)).total_seconds()/60) if latest and latest.finished_at else None
    return {"last_successful_update":latest.finished_at if latest else None,"is_updating":running > 0,"running_count":running,"last_new_count":latest.new_count if latest else 0,"failed_source_count":failures,"data_delay_minutes":delay_minutes,"delay_status":"unknown" if delay_minutes is None else ("healthy" if delay_minutes <= 180 else "delayed")}


@router.get("/stats")
def stats(_: User=Depends(current_user),db: Session=Depends(get_db)):
    start=utcnow()-timedelta(days=365)
    base=and_(Article.is_overseas.is_(True),Article.is_demo.is_(False),Article.review_status != "rejected",Article.published_at.is_not(None),Article.published_at >= start)
    event_identity=func.coalesce(Article.canonical_event_id,Article.content_hash)
    countries=db.execute(select(Article.country,func.count(distinct(event_identity))).where(base).group_by(Article.country).order_by(func.count(distinct(event_identity)).desc())).all()
    regions=db.execute(select(Article.region,func.count(distinct(event_identity))).where(base).group_by(Article.region).order_by(func.count(distinct(event_identity)).desc())).all()
    def event_count(kind: str) -> int:
        return db.scalar(select(func.count(distinct(event_identity))).where(base,Article.intelligence_types.cast(String).ilike(f"%{kind}%"))) or 0
    def event_count_any(kinds: list[str]) -> int:
        return db.scalar(select(func.count(distinct(event_identity))).where(base,or_(*(Article.intelligence_types.cast(String).ilike(f"%{kind}%") for kind in kinds)))) or 0
    total=db.scalar(select(func.count(distinct(event_identity))).where(base)) or 0
    recent30=db.scalar(select(func.count(distinct(event_identity))).where(base,Article.published_at >= utcnow()-timedelta(days=30))) or 0
    high=db.scalar(select(func.count(distinct(event_identity))).where(base,Article.reliability_level == "high")) or 0
    cross=db.scalar(select(func.count(distinct(event_identity))).where(base,Article.cross_source_count >= 2)) or 0
    pending=db.scalar(select(func.count(distinct(event_identity))).where(base,Article.review_status.in_(["pending","needs_changes"]))) or 0
    coverage=db.scalar(select(func.count()).select_from(Source).where(Source.backfill_status == "completed")) or 0
    return {
        "counting_basis":"最近365天按 canonical_event 统计；旧记录在尚未生成事件时使用 content_hash 兼容计数",
        "date_from":start,"date_to":utcnow(),"year_intelligence_count":total,"recent_30_count":recent30,
        "new_factory_count":event_count("new_factory"),"data_center_count":event_count("data_center"),
        "rail_transit_count":event_count("rail_transit"),"power_energy_count":event_count_any(["power_grid","renewable_energy","energy_storage"]),
        "international_policy_count":event_count("international_policy"),"tax_investment_policy_count":event_count_any(["tax_policy","investment_policy"]),
        "ka_intelligence_count":event_count_any(["ka_company","ka_leader"]),
        "high_reliability_ratio":round(high/total,4) if total else 0,"cross_verified_ratio":round(cross/total,4) if total else 0,
        "pending_review_count":pending,"failed_source_count":db.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True),Source.consecutive_failures > 0)) or 0,
        "year_covered_source_count":coverage,
        "backfill_completed_source_count":db.scalar(select(func.count()).select_from(Source).where(Source.backfill_status == "completed")) or 0,
        "backfill_pending_source_count":db.scalar(select(func.count()).select_from(Source).where(Source.backfill_enabled.is_(True),Source.backfill_status.not_in(["completed","unsupported"]))) or 0,
        "backfill_unsupported_source_count":db.scalar(select(func.count()).select_from(Source).where(or_(Source.backfill_enabled.is_(False),Source.backfill_status == "unsupported"))) or 0,
        "countries":[{"name":n,"value":v} for n,v in countries if n],"regions":[{"name":n,"value":v} for n,v in regions if n],
    }


@router.get("/opportunities")
def opportunities(date_from: str | None=None,date_to: str | None=None,region: str | None=None,country: str | None=None,industry: str | None=None,intelligence_type: str | None=None,policy_type: str | None=None,project_stage: str | None=None,ka_group: str | None=None,matched_entity: str | None=None,source: str | None=None,reliability: str | None=None,review_status: str | None=None,verification_status: str | None=None,sort: str="published_desc",page: int=Query(1,ge=1),page_size: int=Query(50,ge=1,le=200),_: User=Depends(current_user),db: Session=Depends(get_db)):
    start=_date_value(date_from) if date_from else utcnow()-timedelta(days=365); end=_date_value(date_to,True) if date_to else utcnow()
    stmt=select(Article).where(Article.is_overseas.is_(True),Article.is_demo.is_(False),Article.published_at >= start,Article.published_at <= end,Article.intelligence_types.cast(String).ilike("%market_project%"))
    for value,column in [(region,Article.region),(country,Article.country),(project_stage,Article.project_stage),(reliability,Article.reliability_level),(verification_status,Article.verification_status)]:
        if value: stmt=stmt.where(column == value)
    if industry: stmt=stmt.where(Article.industries.cast(String).ilike(f"%{industry}%"))
    if intelligence_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{intelligence_type}%"))
    if policy_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{policy_type}%"))
    if ka_group: stmt=stmt.where(Article.ka.cast(String).ilike(f"%{ka_group}%"))
    if matched_entity: stmt=stmt.where(Article.matched_entities.cast(String).ilike(f"%{matched_entity}%"))
    if source: stmt=stmt.where(Article.source_name == source)
    if review_status: stmt=stmt.where(Article.review_status == review_status)
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.order_by(_article_order(sort)).offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[serialize_article(x) for x in rows],"count":total,"page":page,"page_size":page_size}


@router.get("/opportunities/stats")
def opportunity_stats(region: str | None=None,country: str | None=None,_: User=Depends(current_user),db: Session=Depends(get_db)):
    start=utcnow()-timedelta(days=365)
    stmt=select(CanonicalEvent).where(CanonicalEvent.event_date >= start,CanonicalEvent.intelligence_types.cast(String).ilike("%market_project%"))
    if region: stmt=stmt.where(CanonicalEvent.region == region)
    if country: stmt=stmt.where(CanonicalEvent.country == country)
    rows=db.scalars(stmt).all()
    stages: dict[str,int]={}; types: dict[str,int]={}; kas: dict[str,int]={}
    for row in rows:
        stages[row.event_type or "unknown"]=stages.get(row.event_type or "unknown",0)+1
        for kind in row.intelligence_types or []: types[kind]=types.get(kind,0)+1
        for entity in row.matched_entities or []: kas[entity]=kas.get(entity,0)+1
    return {"count":len(rows),"event_types":stages,"intelligence_types":types,"matched_entities":kas,"counting_basis":"canonical_event"}


@router.get("/ka-groups")
def ka_groups(_: User=Depends(current_user),db: Session=Depends(get_db)):
    groups=db.scalars(select(KAGroup).order_by(KAGroup.name)).all()
    return [{"id":g.id,"name":g.name,"ka_type":g.ka_type,"entities":[{"id":e.id,"name":e.name,"entity_relation":e.entity_relation,"is_verified_relation":e.is_verified_relation} for e in db.scalars(select(KAEntity).where(KAEntity.ka_group_id == g.id).order_by(KAEntity.name)).all()]} for g in groups]


@router.get("/ka-groups/{group_id}")
def ka_group_detail(group_id: str,_: User=Depends(current_user),db: Session=Depends(get_db)):
    group=db.get(KAGroup,group_id)
    if not group: raise HTTPException(404,"KA group not found")
    start=utcnow()-timedelta(days=365)
    articles=db.scalars(select(Article).where(Article.published_at >= start,Article.ka.cast(String).ilike(f"%{group.name}%")).order_by(Article.published_at.desc()).limit(200)).all()
    return {"id":group.id,"name":group.name,"ka_type":group.ka_type,"items":[serialize_article(x) for x in articles],"entities":[{"id":e.id,"name":e.name,"entity_relation":e.entity_relation,"is_verified_relation":e.is_verified_relation} for e in db.scalars(select(KAEntity).where(KAEntity.ka_group_id == group.id)).all()]}


@router.get("/ka-intelligence")
def ka_intelligence(ka_group: str | None=None,matched_entity: str | None=None,intelligence_type: str | None=None,policy_type: str | None=None,country: str | None=None,region: str | None=None,industry: str | None=None,source: str | None=None,reliability: str | None=None,review_status: str | None=None,verification_status: str | None=None,date_from: str | None=None,date_to: str | None=None,sort: str="published_desc",page: int=Query(1,ge=1),page_size: int=Query(50,ge=1,le=200),_: User=Depends(current_user),db: Session=Depends(get_db)):
    start=_date_value(date_from) if date_from else utcnow()-timedelta(days=365); end=_date_value(date_to,True) if date_to else utcnow()
    stmt=select(Article).where(Article.published_at >= start,Article.published_at <= end,or_(Article.intelligence_types.cast(String).ilike("%ka_company%"),Article.intelligence_types.cast(String).ilike("%ka_leader%")))
    if ka_group: stmt=stmt.where(Article.ka.cast(String).ilike(f"%{ka_group}%"))
    if matched_entity: stmt=stmt.where(Article.matched_entities.cast(String).ilike(f"%{matched_entity}%"))
    if intelligence_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{intelligence_type}%"))
    if policy_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{policy_type}%"))
    if industry: stmt=stmt.where(Article.industries.cast(String).ilike(f"%{industry}%"))
    if source: stmt=stmt.where(Article.source_name == source)
    if review_status: stmt=stmt.where(Article.review_status == review_status)
    if verification_status: stmt=stmt.where(Article.verification_status == verification_status)
    for value,column in [(country,Article.country),(region,Article.region),(reliability,Article.reliability_level)]:
        if value: stmt=stmt.where(column == value)
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.order_by(_article_order(sort)).offset((page-1)*page_size).limit(page_size)).all()
    leader_stmt=select(KALeaderEvent).join(Article,KALeaderEvent.article_id == Article.id).where(
        KALeaderEvent.event_date >= start,KALeaderEvent.event_date <= end,
    )
    for value,column in [
        (ka_group,KALeaderEvent.ka_group),(matched_entity,KALeaderEvent.matched_entity),
        (country,KALeaderEvent.country),(region,Article.region),(source,KALeaderEvent.source_name),
        (reliability,Article.reliability_level),(review_status,Article.review_status),
        (verification_status,Article.verification_status),
    ]:
        if value: leader_stmt=leader_stmt.where(column == value)
    leaders=db.scalars(leader_stmt.order_by(KALeaderEvent.event_date.desc()).limit(100)).all()
    return {"items":[serialize_article(x) for x in rows],"leaders":[{"id":x.id,"article_id":x.article_id,"person_name":x.person_name,"person_title":x.person_title,"organization":x.organization,"ka_group":x.ka_group,"matched_entity":x.matched_entity,"action_type":x.action_type,"meeting_party":x.meeting_party,"country":x.country,"city":x.city,"event_date":x.event_date,"factual_summary":x.factual_summary,"source_url":x.source_url,"source_name":x.source_name,"published_at":x.published_at,"confidence":x.confidence,"evidence_excerpt":x.evidence_excerpt} for x in leaders],"count":total,"page":page,"page_size":page_size}


@router.get("/policies")
def policies(date_from: str | None=None,date_to: str | None=None,country: str | None=None,region: str | None=None,industry: str | None=None,intelligence_type: str | None=None,policy_type: str | None=None,ka_group: str | None=None,matched_entity: str | None=None,source: str | None=None,reliability: str | None=None,review_status: str | None=None,verification_status: str | None=None,sort: str="published_desc",page: int=Query(1,ge=1),page_size: int=Query(50,ge=1,le=200),_: User=Depends(current_user),db: Session=Depends(get_db)):
    start=_date_value(date_from) if date_from else utcnow()-timedelta(days=365); end=_date_value(date_to,True) if date_to else utcnow()
    stmt=select(PolicyIntelligence,Article).join(Article,PolicyIntelligence.article_id == Article.id).where(Article.published_at >= start,Article.published_at <= end)
    if country: stmt=stmt.where(or_(PolicyIntelligence.publishing_country == country,PolicyIntelligence.affected_countries.cast(String).ilike(f"%{country}%")))
    if region: stmt=stmt.where(Article.region == region)
    if industry: stmt=stmt.where(PolicyIntelligence.applicable_industries.cast(String).ilike(f"%{industry}%"))
    if intelligence_type: stmt=stmt.where(Article.intelligence_types.cast(String).ilike(f"%{intelligence_type}%"))
    if policy_type: stmt=stmt.where(PolicyIntelligence.policy_types.cast(String).ilike(f"%{policy_type}%"))
    if ka_group: stmt=stmt.where(Article.ka.cast(String).ilike(f"%{ka_group}%"))
    if matched_entity: stmt=stmt.where(Article.matched_entities.cast(String).ilike(f"%{matched_entity}%"))
    if source: stmt=stmt.where(Article.source_name == source)
    if reliability: stmt=stmt.where(Article.reliability_level == reliability)
    if review_status: stmt=stmt.where(Article.review_status == review_status)
    if verification_status: stmt=stmt.where(Article.verification_status == verification_status)
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.execute(stmt.order_by(_article_order(sort)).offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[serialize_article(article)|{"policy":{"publishing_country":p.publishing_country,"affected_countries":p.affected_countries,"issuing_body":p.issuing_body,"policy_types":p.policy_types,"applicable_industries":p.applicable_industries,"effective_date":p.effective_date,"expiry_date":p.expiry_date,"tax_type":p.tax_type,"tax_rate_change":p.tax_rate_change,"investment_threshold":p.investment_threshold,"foreign_ownership_ratio":p.foreign_ownership_ratio,"localization_requirements":p.localization_requirements,"local_procurement_ratio":p.local_procurement_ratio,"incentives":p.incentives,"import_tariff":p.import_tariff,"export_controls":p.export_controls,"technical_standards":p.technical_standards,"certification_requirements":p.certification_requirements,"china_company_impact":p.china_company_impact,"schneider_sales_impact":p.schneider_sales_impact,"verification_items":p.verification_items}} for p,article in rows],"count":total,"page":page,"page_size":page_size}


@router.get("/saved-searches")
def saved_searches(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [{"id":x.id,"name":x.name,"filters":x.filters,"created_at":x.created_at} for x in db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id)).all()]


@router.post("/saved-searches",status_code=201)
def save_search(payload: SavedSearchCreate,user: User=Depends(require_role("sales")),db: Session=Depends(get_db)):
    row=SavedSearch(user_id=user.id,name=payload.name,filters=payload.filters); db.add(row); db.commit(); db.refresh(row); return {"id":row.id,"name":row.name,"filters":row.filters}


@router.get("/audit-logs")
def audit_logs(limit: int=Query(100,ge=1,le=500),_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    return [{"id":x.id,"user_id":x.user_id,"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"details":x.details,"ip_address":x.ip_address,"created_at":x.created_at} for x in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()]


def _batch_payload(db: Session,batch: CrawlBatch,include_items: bool=False) -> dict:
    items=db.scalars(select(CrawlBatchItem).where(CrawlBatchItem.batch_id == batch.id).order_by(CrawlBatchItem.status,CrawlBatchItem.id)).all()
    sources={x.id:x for x in db.scalars(select(Source).where(Source.id.in_([i.source_id for i in items] or [""]))).all()}
    current=[sources[x.source_id].source_name for x in items if x.status == "running" and x.source_id in sources]
    payload={
        "id":batch.id,"created_by":batch.created_by,"created_at":batch.created_at,
        "started_at":batch.started_at,"finished_at":batch.finished_at,"status":batch.status,
        "total_sources":batch.total_sources,
        "completed":batch.completed_count,"completed_count":batch.completed_count,
        "success":batch.success_count,"success_count":batch.success_count,
        "empty":batch.empty_count,"empty_count":batch.empty_count,
        "failed":batch.failed_count,"failed_count":batch.failed_count,
        "skipped":batch.skipped_count,"skipped_count":batch.skipped_count,
        "new_count":batch.new_count,"updated_count":batch.updated_count,
        "duplicate_count":batch.duplicate_count,"current_sources":current,
        "remaining":max(0,batch.total_sources-batch.completed_count),
        "cancel_requested":batch.cancel_requested,
    }
    if include_items:
        payload["items"]=[{"id":x.id,"source_id":x.source_id,"source_name":sources[x.source_id].source_name if x.source_id in sources else "unknown","status":x.status,"skip_reason":x.skip_reason,"failure_reason":x.failure_reason,"started_at":x.started_at,"finished_at":x.finished_at} for x in items]
    return payload


@router.post("/admin/crawl-batches",status_code=202)
def create_crawl_batch(payload: CrawlBatchCreate,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    existing=db.scalar(select(CrawlBatch).where(CrawlBatch.singleton_key == "global"))
    if existing: raise HTTPException(409,{"message":"a full crawl batch is already active","batch_id":existing.id})
    batch=CrawlBatch(created_by=user.id,status="queued",singleton_key="global")
    db.add(batch)
    try:
        db.commit(); db.refresh(batch)
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(CrawlBatch).where(CrawlBatch.singleton_key == "global"))
        raise HTTPException(409,{"message":"a full crawl batch is already active","batch_id":existing.id if existing else None})
    stmt=select(Source).order_by(Source.source_name)
    if payload.source_ids: stmt=stmt.where(Source.id.in_(payload.source_ids))
    all_sources=db.scalars(stmt).all()
    queued: list[tuple[Source,CrawlJob,CrawlBatchItem]]=[]
    for source in all_sources:
        runnable=source.enabled and source.adapter_status == "active" and source.crawl_method != "manual_import" and source.source_type != "wechat_manual"
        item=CrawlBatchItem(batch_id=batch.id,source_id=source.id,status="queued" if runnable else "skipped",skip_reason=None if runnable else f"{source.adapter_status}/{source.crawl_method}")
        db.add(item); db.flush()
        if runnable:
            job=CrawlJob(source_id=source.id,requested_by=user.id,trigger_type="batch",status="queued")
            db.add(job); db.flush(); item.crawl_job_id=job.id; queued.append((source,job,item))
    batch.total_sources=len(all_sources); batch.skipped_count=len(all_sources)-len(queued); batch.completed_count=batch.skipped_count
    if not queued:
        batch.status="completed"; batch.finished_at=utcnow(); batch.singleton_key=None
    db.commit()
    for source,job,item in queued:
        try:
            task=celery.send_task("tasks.crawl_source",args=[source.id,job.id,item.id])
            job.celery_task_id=task.id; item.celery_task_id=task.id
        except Exception as exc:
            job.status="queue_failed"; item.status="failed"; item.failure_reason=f"worker queue unavailable: {exc}"; item.finished_at=utcnow()
    batch.failed_count=sum(1 for _source,_job,item in queued if item.status == "failed")
    batch.completed_count=batch.skipped_count+batch.failed_count
    if batch.total_sources and batch.completed_count >= batch.total_sources:
        batch.status="completed_with_errors"; batch.finished_at=utcnow(); batch.singleton_key=None
    db.commit()
    audit(db,request,user,"crawl_batch.create","crawl_batch",batch.id,{"queued":len(queued),"skipped":batch.skipped_count})
    return _batch_payload(db,batch)


@router.get("/admin/crawl-batches")
def list_crawl_batches(limit: int=Query(20,ge=1,le=100),_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    return [_batch_payload(db,x) for x in db.scalars(select(CrawlBatch).order_by(CrawlBatch.created_at.desc()).limit(limit)).all()]


@router.get("/admin/crawl-batches/{batch_id}")
def get_crawl_batch(batch_id: str,_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    batch=db.get(CrawlBatch,batch_id)
    if not batch: raise HTTPException(404,"crawl batch not found")
    return _batch_payload(db,batch,True)


@router.post("/admin/crawl-batches/{batch_id}/cancel")
def cancel_crawl_batch(batch_id: str,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    batch=db.get(CrawlBatch,batch_id)
    if not batch: raise HTTPException(404,"crawl batch not found")
    if batch.status not in {"queued","running"}: return _batch_payload(db,batch)
    batch.cancel_requested=True
    items=db.scalars(select(CrawlBatchItem).where(CrawlBatchItem.batch_id == batch.id,CrawlBatchItem.status == "queued")).all()
    for item in items:
        item.status="cancelled"; item.finished_at=utcnow()
        if item.celery_task_id:
            try: celery.control.revoke(item.celery_task_id,terminate=False)
            except Exception: pass
        if item.crawl_job_id:
            job=db.get(CrawlJob,item.crawl_job_id)
            if job: job.status="cancelled"
    batch.completed_count += len(items); batch.skipped_count += len(items)
    if batch.completed_count >= batch.total_sources:
        batch.status="cancelled"; batch.finished_at=utcnow(); batch.singleton_key=None
    db.commit(); audit(db,request,user,"crawl_batch.cancel","crawl_batch",batch.id,{"cancelled_items":len(items)})
    return _batch_payload(db,batch,True)


def _backfill_payload(db: Session,run: BackfillRun) -> dict:
    source=db.get(Source,run.source_id)
    return {"id":run.id,"source_id":run.source_id,"source_name":source.source_name if source else "unknown","status":run.status,"date_from":run.date_from,"date_to":run.date_to,"page_limit":run.page_limit,"current_page":run.current_page,"cursor":run.cursor,"fetched_count":run.fetched_count,"new_count":run.new_count,"duplicate_count":run.duplicate_count,"date_unverified_count":run.date_unverified_count,"failure_reason":run.failure_reason,"started_at":run.started_at,"finished_at":run.finished_at,"created_at":run.created_at,"checkpoints":[{"page_number":x.page_number,"cursor":x.cursor,"oldest_published_at":x.oldest_published_at,"fetched_count":x.fetched_count,"created_at":x.created_at} for x in db.scalars(select(BackfillCheckpoint).where(BackfillCheckpoint.backfill_run_id == run.id).order_by(BackfillCheckpoint.page_number)).all()]}


@router.post("/admin/backfills",status_code=202)
def create_backfill(payload: BackfillCreate,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    source=db.get(Source,payload.source_id)
    if not source or source.adapter_status != "active" or not source.adapter_key: raise HTTPException(400,"source does not support an active adapter")
    start=payload.date_from.replace(tzinfo=timezone.utc) if payload.date_from.tzinfo is None else payload.date_from.astimezone(timezone.utc)
    end=payload.date_to.replace(tzinfo=timezone.utc) if payload.date_to.tzinfo is None else payload.date_to.astimezone(timezone.utc)
    if start >= end: raise HTTPException(422,"date_from must be before date_to")
    active=db.scalar(select(BackfillRun).where(BackfillRun.source_id == source.id,BackfillRun.status.in_(["queued","running","paused"])))
    if active: raise HTTPException(409,{"message":"source already has an active backfill","backfill_id":active.id})
    run=BackfillRun(source_id=source.id,requested_by=user.id,status="queued",date_from=start,date_to=end,page_limit=payload.page_limit)
    db.add(run); source.backfill_enabled=True; source.backfill_start_date=start; source.backfill_end_date=end; source.backfill_page_limit=payload.page_limit; source.backfill_status="queued"
    db.commit(); db.refresh(run)
    try:
        task=celery.send_task("tasks.backfill_source",args=[run.id]); run.celery_task_id=task.id; db.commit()
    except Exception as exc:
        run.status="failed"; run.failure_reason=f"worker queue unavailable: {exc}"; source.backfill_status="failed"; db.commit(); raise HTTPException(503,run.failure_reason)
    audit(db,request,user,"backfill.create","backfill",run.id,{"source_id":source.id,"date_from":start.isoformat(),"date_to":end.isoformat()})
    return _backfill_payload(db,run)


@router.get("/admin/backfills")
def list_backfills(limit: int=Query(50,ge=1,le=200),_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    return [_backfill_payload(db,x) for x in db.scalars(select(BackfillRun).order_by(BackfillRun.created_at.desc()).limit(limit)).all()]


@router.get("/admin/backfills/{run_id}")
def get_backfill(run_id: str,_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    run=db.get(BackfillRun,run_id)
    if not run: raise HTTPException(404,"backfill not found")
    return _backfill_payload(db,run)


@router.post("/admin/backfills/{run_id}/{action}")
def control_backfill(run_id: str,action: str,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    if action not in {"pause","resume","retry","cancel"}: raise HTTPException(404,"unknown backfill action")
    run=db.get(BackfillRun,run_id)
    if not run: raise HTTPException(404,"backfill not found")
    source=db.get(Source,run.source_id)
    if action == "pause" and run.status == "running":
        run.status="paused"; source.backfill_status="paused"
    elif action == "cancel" and run.status in {"queued","running","paused"}:
        run.status="cancelled"; run.finished_at=utcnow(); source.backfill_status="cancelled"
        if run.celery_task_id:
            try: celery.control.revoke(run.celery_task_id,terminate=False)
            except Exception: pass
    elif action in {"resume","retry"} and run.status in {"paused","failed"}:
        run.status="queued"; run.failure_reason=None; source.backfill_status="queued"
        task=celery.send_task("tasks.backfill_source",args=[run.id]); run.celery_task_id=task.id
    else:
        raise HTTPException(409,f"cannot {action} a {run.status} backfill")
    db.commit(); audit(db,request,user,f"backfill.{action}","backfill",run.id)
    return _backfill_payload(db,run)


@router.get("/admin/source-capability-checks")
def capability_checks(limit: int=Query(200,ge=1,le=500),_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    rows=db.scalars(select(SourceCapabilityCheck).order_by(SourceCapabilityCheck.checked_at.desc()).limit(limit)).all()
    return [{"id":x.id,"source_id":x.source_id,"checked_at":x.checked_at,"status":x.status,"test_method":x.test_method,"http_status":x.http_status,"crawlable":x.crawlable,"one_year_backfill":x.one_year_backfill,"extracted_fields":x.extracted_fields,"test_count":x.test_count,"failure_reason":x.failure_reason,"compliance_limits":x.compliance_limits,"recommendation":x.recommendation,"details":x.details} for x in rows]


def _cscec_source_rows(db: Session) -> list[Source]:
    return [
        row
        for row in db.scalars(select(Source).order_by(Source.source_name)).all()
        if "cscec" in (row.source_tags or [])
    ]


@router.get("/ka/cscec/entities")
def cscec_entities(
    entity_level: str | None=None,
    entity_type: str | None=None,
    overseas: bool | None=None,
    country: str | None=None,
    region: str | None=None,
    verification_status: str | None=None,
    active: bool | None=None,
    _: User=Depends(current_user),
    db: Session=Depends(get_db),
):
    stmt=select(CSCECEntity)
    if entity_level: stmt=stmt.where(CSCECEntity.entity_level == entity_level)
    if entity_type: stmt=stmt.where(CSCECEntity.entity_type == entity_type)
    if overseas is not None: stmt=stmt.where(CSCECEntity.overseas.is_(overseas))
    if country: stmt=stmt.where(CSCECEntity.country == country)
    if region: stmt=stmt.where(CSCECEntity.region == region)
    if verification_status: stmt=stmt.where(CSCECEntity.verification_status == verification_status)
    if active is not None: stmt=stmt.where(CSCECEntity.active.is_(active))
    rows=db.scalars(stmt.order_by(CSCECEntity.entity_level,CSCECEntity.canonical_name)).all()
    return {
        "count":len(rows),
        "items":[{
            "entity_id":row.entity_id,"canonical_name":row.canonical_name,"short_name":row.short_name,
            "aliases":row.aliases,"parent_entity_id":row.parent_entity_id,"entity_level":row.entity_level,
            "entity_type":row.entity_type,"stock_code":row.stock_code,"official_url":row.official_url,
            "country":row.country,"region":row.region,"overseas":row.overseas,
            "verification_status":row.verification_status,"verification_source":row.verification_source,
            "active":row.active,"notes":row.notes,"updated_at":row.updated_at,
        } for row in rows],
    }


@router.get("/ka/cscec/events")
def cscec_events(
    q: str | None=None,
    date_from: str | None=None,
    date_to: str | None=None,
    entity_id: str | None=None,
    source_type: str | None=None,
    reliability: str | None=None,
    page: int=Query(1,ge=1),
    page_size: int=Query(50,ge=1,le=200),
    user: User=Depends(current_user),
    db: Session=Depends(get_db),
):
    sources=_cscec_source_rows(db)
    source_names=[row.source_name for row in sources]
    stmt=select(Article).where(Article.source_name.in_(source_names or [""]),Article.is_demo.is_(False))
    start=_date_value(date_from) if date_from else utcnow()-timedelta(days=365)
    end=_date_value(date_to,True) if date_to else utcnow()
    stmt=stmt.where(Article.published_at.is_not(None),Article.published_at >= start,Article.published_at <= end)
    if q: stmt=stmt.where(or_(Article.title.ilike(f"%{q}%"),Article.summary.ilike(f"%{q}%"),Article.content_excerpt.ilike(f"%{q}%")))
    if source_type: stmt=stmt.where(Article.source_type == source_type)
    if reliability: stmt=stmt.where(Article.reliability_level == reliability)
    if entity_id:
        allowed=[row.source_name for row in sources if row.entity_id == entity_id]
        stmt=stmt.where(Article.source_name.in_(allowed or [""]))
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.order_by(func.coalesce(Article.published_at,Article.fetched_at).desc()).offset((page-1)*page_size).limit(page_size)).all()
    favorites=set(db.scalars(select(UserFavorite.article_id).where(UserFavorite.user_id == user.id)).all())
    reads=set(db.scalars(select(UserReadStatus.article_id).where(UserReadStatus.user_id == user.id)).all())
    return {"items":[serialize_article(row,row.id in favorites,row.id in reads) for row in rows],"count":total,"page":page,"page_size":page_size,"date_from":start,"date_to":end}


@router.get("/ka/cscec/leadership-events")
def cscec_leadership_events(
    entity_id: str | None=None,
    appointment_type: str | None=None,
    verification_status: str | None=None,
    limit: int=Query(100,ge=1,le=500),
    _: User=Depends(current_user),
    db: Session=Depends(get_db),
):
    stmt=select(CSCECLeadershipEvent)
    if entity_id: stmt=stmt.where(CSCECLeadershipEvent.entity_id == entity_id)
    if appointment_type: stmt=stmt.where(CSCECLeadershipEvent.appointment_type == appointment_type)
    if verification_status: stmt=stmt.where(CSCECLeadershipEvent.verification_status == verification_status)
    rows=db.scalars(stmt.order_by(func.coalesce(CSCECLeadershipEvent.published_at,CSCECLeadershipEvent.created_at).desc()).limit(limit)).all()
    return [{"id":row.id,"person_name":row.person_name,"entity_id":row.entity_id,"parent_entity_id":row.parent_entity_id,"title_before":row.title_before,"title_after":row.title_after,"appointment_type":row.appointment_type,"effective_date":row.effective_date,"published_at":row.published_at,"source_url":row.source_url,"source_name":row.source_name,"evidence_excerpt":row.evidence_excerpt,"confidence":row.confidence,"verification_status":row.verification_status} for row in rows]


@router.get("/ka/cscec/org-events")
def cscec_org_events(
    change_type: str | None=None,
    verification_status: str | None=None,
    limit: int=Query(100,ge=1,le=500),
    _: User=Depends(current_user),
    db: Session=Depends(get_db),
):
    stmt=select(CSCECOrgEvent)
    if change_type: stmt=stmt.where(CSCECOrgEvent.change_type == change_type)
    if verification_status: stmt=stmt.where(CSCECOrgEvent.verification_status == verification_status)
    rows=db.scalars(stmt.order_by(func.coalesce(CSCECOrgEvent.published_at,CSCECOrgEvent.created_at).desc()).limit(limit)).all()
    return [{"id":row.id,"change_type":row.change_type,"entity_before":row.entity_before,"entity_after":row.entity_after,"parent_before":row.parent_before,"parent_after":row.parent_after,"relation_before":row.relation_before,"relation_after":row.relation_after,"effective_date":row.effective_date,"published_at":row.published_at,"source_urls":row.source_urls,"source_count":row.source_count,"diff_snapshot_id":row.diff_snapshot_id,"evidence_excerpt":row.evidence_excerpt,"confidence":row.confidence,"verification_status":row.verification_status} for row in rows]


@router.get("/ka/cscec/page-diffs")
def cscec_page_diffs(
    entity_id: str | None=None,
    page_type: str | None=None,
    verification_status: str | None=None,
    limit: int=Query(100,ge=1,le=500),
    _: User=Depends(current_user),
    db: Session=Depends(get_db),
):
    stmt=select(PageDiff)
    if entity_id: stmt=stmt.where(PageDiff.entity_id == entity_id)
    if page_type: stmt=stmt.where(PageDiff.page_type == page_type)
    if verification_status: stmt=stmt.where(PageDiff.verification_status == verification_status)
    rows=db.scalars(stmt.order_by(PageDiff.created_at.desc()).limit(limit)).all()
    return [{"id":row.id,"entity_id":row.entity_id,"page_type":row.page_type,"page_url":row.page_url,"before_snapshot_id":row.before_snapshot_id,"after_snapshot_id":row.after_snapshot_id,"diff_text":row.diff_text,"detected_changes":row.detected_changes,"confidence":row.confidence,"verification_status":row.verification_status,"reviewed_at":row.reviewed_at,"created_at":row.created_at} for row in rows]


@router.post("/ka/cscec/page-diffs/{diff_id}/review")
def review_cscec_page_diff(diff_id: str,payload: ReviewRequest,request: Request,user: User=Depends(require_role("analyst")),db: Session=Depends(get_db)):
    row=db.get(PageDiff,diff_id)
    if not row: raise HTTPException(404,"page diff not found")
    row.verification_status={"approve":"verified","reject":"rejected","needs_changes":"pending_review"}[payload.action]
    row.reviewer_id=user.id; row.reviewed_at=utcnow(); db.commit()
    audit(db,request,user,"cscec.page_diff.review","page_diff",row.id,{"action":payload.action,"notes":payload.notes})
    return {"id":row.id,"verification_status":row.verification_status,"reviewed_at":row.reviewed_at}


@router.post("/admin/crawl/cscec/all",status_code=202)
def crawl_all_cscec(payload: CSCECCrawlCreate,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    sources=_cscec_source_rows(db)
    if payload.source_type: sources=[row for row in sources if row.source_type == payload.source_type]
    if payload.entity_ids: sources=[row for row in sources if row.entity_id in payload.entity_ids]
    if not sources: raise HTTPException(404,"no CSCEC sources matched")
    return create_crawl_batch(CrawlBatchCreate(source_ids=[row.id for row in sources]),request,user,db)


@router.post("/admin/crawl/cscec/backfill",status_code=202)
def backfill_all_cscec(payload: CSCECBackfillCreate,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    start=payload.date_from or (utcnow()-timedelta(days=365))
    end=payload.date_to or utcnow()
    sources=[
        row for row in _cscec_source_rows(db)
        if row.adapter_status == "active" and row.adapter_key and row.backfill_enabled
    ]
    if payload.entity_ids: sources=[row for row in sources if row.entity_id in payload.entity_ids]
    queued=[]; skipped=[]
    for source in sources:
        active=db.scalar(select(BackfillRun).where(BackfillRun.source_id == source.id,BackfillRun.status.in_(["queued","running","paused"])))
        if active:
            skipped.append({"source_id":source.id,"reason":"already_active","backfill_id":active.id})
            continue
        run=BackfillRun(source_id=source.id,requested_by=user.id,status="queued",date_from=start,date_to=end,page_limit=payload.page_limit)
        db.add(run); source.backfill_status="queued"; db.flush()
        try:
            task=celery.send_task("tasks.backfill_source",args=[run.id]); run.celery_task_id=task.id
            queued.append({"source_id":source.id,"source_name":source.source_name,"backfill_id":run.id,"task_id":task.id})
        except Exception as exc:
            run.status="failed"; run.failure_reason=f"worker queue unavailable: {exc}"; source.backfill_status="failed"
            skipped.append({"source_id":source.id,"reason":run.failure_reason})
    db.commit()
    audit(db,request,user,"cscec.backfill.create","cscec",None,{"queued":len(queued),"skipped":len(skipped)})
    return {"queued":queued,"skipped":skipped,"date_from":start,"date_to":end}


@router.post("/admin/cscec/entities/sync",status_code=202)
def sync_cscec_entity_endpoint(request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    try:
        task=celery.send_task("tasks.sync_cscec_entities")
    except Exception as exc:
        raise HTTPException(503,f"worker queue unavailable: {exc}") from exc
    audit(db,request,user,"cscec.entities.sync","cscec",None,{"task_id":task.id})
    return {"status":"queued","task_id":task.id}


@router.post("/analyst/manual-import/wechat",status_code=201)
def cscec_wechat_manual_import(payload: ManualImport,request: Request,user: User=Depends(require_role("analyst")),db: Session=Depends(get_db)):
    return manual_import(payload.model_copy(update={"import_type":"wechat"}),request,user,db)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not settings.production: Base.metadata.create_all(engine)
        with SessionLocal() as db: ensure_roles(db); sync_cscec_entities(db); sync_sources(db); sync_ka_mappings(db)
        yield
    app=FastAPI(title="Schneider Global Sales Intelligence API",version="1.0.0",lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=list(settings.allowed_origins),allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
    app.include_router(router)

    def readiness(response: Response,db: Session) -> dict:
        database_ok=True
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            database_ok=False
            db.rollback()
        redis_ok=True
        try:
            Redis.from_url(settings.redis_url,socket_connect_timeout=2,socket_timeout=2).ping()
        except Exception:
            redis_ok=False
        if not database_ok: response.status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status":"ready" if database_ok and redis_ok else ("degraded" if database_ok else "not_ready"),
            "database":"ok" if database_ok else "unavailable",
            "redis":"ok" if redis_ok else "unavailable",
            "environment":settings.environment,
            "timestamp":utcnow(),
        }

    @app.get("/health/live")
    def health_live():
        return {"status":"alive","timestamp":utcnow()}

    @app.get("/health/ready")
    def health_ready(response: Response,db: Session=Depends(get_db)):
        return readiness(response,db)

    @app.get("/health")
    def health(response: Response,db: Session=Depends(get_db)):
        return readiness(response,db)
    return app


app=create_app()
