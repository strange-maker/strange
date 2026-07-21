from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import String, and_, distinct, func, or_, select, text
from sqlalchemy.orm import Session

from adapters.base import SourceItem
from config import get_settings
from database import SessionLocal, engine, get_db
from ingestion import ingest_item
from models import Article, ArticleSource, AuditLog, Base, CrawlError, CrawlJob, CrawlRun, RefreshToken, ReviewRecord, Role, SavedSearch, Source, User, UserFavorite, UserReadStatus, utcnow
from schemas import LoginRequest, ManualImport, RefreshRequest, ReviewRequest, SavedSearchCreate, SourceUpdate, TokenResponse, UserCreate, UserUpdate
from security import _as_utc, audit, consume_refresh_token, create_access_token, current_user, hash_password, issue_refresh_token, require_role, verify_password
from source_service import ensure_roles, sync_sources

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
    return {"id":article.id,"title":article.title,"original_title":article.original_title,"summary":article.summary,"sales_insight":article.sales_insight,"original_url":article.original_url,"canonical_url":article.canonical_url,"source_name":article.source_name,"source_type":article.source_type,"reliability_level":article.reliability_level,"source_reliability":article.reliability_level,"published_at":article.published_at,"fetched_at":article.fetched_at,"first_seen_at":article.first_seen_at,"last_seen_at":article.last_seen_at,"content_excerpt":article.content_excerpt,"language":article.language,"country":article.country,"region":article.region,"ka":article.ka,"subsidiary":article.subsidiary,"industries":article.industries,"project_type":article.project_type,"project_stage":article.project_stage,"project_value":float(article.project_value) if article.project_value is not None else None,"currency":article.currency,"overseas_evidence":article.overseas_evidence,"ka_match_evidence":article.ka_match_evidence,"confidence_score":article.confidence_score,"verification_status":article.verification_status,"cross_source_count":article.cross_source_count,"is_primary_source":article.is_primary_source,"review_status":article.review_status,"ai_payload":article.ai_payload,"favorite":favorite,"read":read,"verification_notice":None if article.reliability_level == "high" or article.cross_source_count > 1 else "媒体线索，建议核验官方公告"}


@router.get("/articles")
def articles(q: str | None=None,country: str | None=None,region: str | None=None,ka: str | None=None,source_type: str | None=None,reliability: str | None=None,review_status: str | None=None,verification_status: str | None=None,from_fetched_at: str | None=None,limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(get_db)):
    stmt=select(Article).where(Article.is_overseas.is_(True),Article.is_demo.is_(False))
    if q:
        if settings.database_url.startswith("postgresql"):
            vector=func.to_tsvector("simple",func.coalesce(Article.title,"")+" "+func.coalesce(Article.summary,"")+" "+func.coalesce(Article.content_excerpt,""))
            stmt=stmt.where(or_(vector.op("@@")(func.plainto_tsquery("simple",q)),func.similarity(Article.title,q) > .2))
        else: stmt=stmt.where(or_(Article.title.ilike(f"%{q}%"),Article.summary.ilike(f"%{q}%"),Article.content_excerpt.ilike(f"%{q}%"),Article.country.ilike(f"%{q}%"),Article.region.ilike(f"%{q}%")))
    if country: stmt=stmt.where(Article.country == country)
    if region: stmt=stmt.where(Article.region == region)
    if ka: stmt=stmt.where(Article.ka.cast(String).ilike(f"%{ka}%"))
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
    rows=db.scalars(stmt.order_by(func.coalesce(Article.published_at,Article.fetched_at).desc()).offset(offset).limit(limit)).all()
    favorites=set(db.scalars(select(UserFavorite.article_id).where(UserFavorite.user_id == user.id)).all()); reads=set(db.scalars(select(UserReadStatus.article_id).where(UserReadStatus.user_id == user.id)).all())
    return {"items":[serialize_article(x,x.id in favorites,x.id in reads) for x in rows],"count":total,"limit":limit,"offset":offset}


@router.get("/articles/{article_id}")
def article(article_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    row=db.get(Article,article_id)
    if not row: raise HTTPException(404,"article not found")
    favorite=db.get(UserFavorite,(user.id,article_id)) is not None; read=db.get(UserReadStatus,(user.id,article_id)) is not None
    payload=serialize_article(row,favorite,read)
    payload["supporting_sources"]=[{"source_id":x.source_id,"title":x.title,"original_url":x.original_url,"published_at":x.published_at,"reliability_level":x.reliability_level,"is_primary":x.is_primary} for x in db.scalars(select(ArticleSource).where(ArticleSource.article_id == article_id).order_by(ArticleSource.is_primary.desc())).all()]
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
        result.append({"id":source.id,"source_name":source.source_name,"source_url":source.source_url,"source_type":source.source_type,"source_tags":source.source_tags,"reliability_level":source.reliability_level,"crawl_method":source.crawl_method,"adapter_status":source.adapter_status,"schedule_minutes":source.schedule_minutes,"enabled":source.enabled,"region_focus":source.region_focus,"country_focus":source.country_focus,"industry_focus":source.industry_focus,"notes":source.notes,"last_success_at":source.last_success_at,"last_failure_at":source.last_failure_at,"consecutive_failures":source.consecutive_failures,"next_run_at":source.next_run_at,"latest_new_count":run.new_count if run else 0,"latest_status":run.status if run else "never","latest_failure_reason":run.failure_reason if run else None})
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
    db.commit(); audit(db,request,user,"source.update","source",source.id,payload.model_dump(exclude_none=True)); return {"id":source.id,"enabled":source.enabled,"schedule_minutes":source.schedule_minutes}


@router.post("/sources/{source_id}/run",status_code=202)
def run_source(source_id: str,request: Request,user: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source or source.adapter_status != "active" or not source.enabled: raise HTTPException(400,"source is not runnable")
    job=CrawlJob(source_id=source.id,requested_by=user.id,trigger_type="manual",status="queued"); db.add(job); db.commit(); db.refresh(job)
    try:
        from tasks import crawl_source
        task=crawl_source.delay(source.id,job.id); job.celery_task_id=task.id; db.commit()
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
    base=and_(Article.is_overseas.is_(True),Article.is_demo.is_(False),Article.review_status != "rejected")
    countries=db.execute(select(Article.country,func.count(distinct(Article.content_hash))).where(base).group_by(Article.country).order_by(func.count(distinct(Article.content_hash)).desc()).limit(15)).all()
    regions=db.execute(select(Article.region,func.count(distinct(Article.content_hash))).where(base).group_by(Article.region).order_by(func.count(distinct(Article.content_hash)).desc())).all()
    return {"counting_basis":"按去重后的 content_hash 统计，已排除 demo 与 rejected 记录","countries":[{"name":n,"value":v} for n,v in countries if n],"regions":[{"name":n,"value":v} for n,v in regions if n]}


@router.get("/saved-searches")
def saved_searches(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [{"id":x.id,"name":x.name,"filters":x.filters,"created_at":x.created_at} for x in db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id)).all()]


@router.post("/saved-searches",status_code=201)
def save_search(payload: SavedSearchCreate,user: User=Depends(require_role("sales")),db: Session=Depends(get_db)):
    row=SavedSearch(user_id=user.id,name=payload.name,filters=payload.filters); db.add(row); db.commit(); db.refresh(row); return {"id":row.id,"name":row.name,"filters":row.filters}


@router.get("/audit-logs")
def audit_logs(limit: int=Query(100,ge=1,le=500),_: User=Depends(require_role("admin")),db: Session=Depends(get_db)):
    return [{"id":x.id,"user_id":x.user_id,"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"details":x.details,"ip_address":x.ip_address,"created_at":x.created_at} for x in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()]


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not settings.production: Base.metadata.create_all(engine)
        with SessionLocal() as db: ensure_roles(db); sync_sources(db)
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
