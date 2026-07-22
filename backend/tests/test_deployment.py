from types import SimpleNamespace

import pytest
from sqlalchemy import select

import api as api_module
from api import app
from celery_app import celery
from cli import bootstrap_admin
from config import get_settings,normalize_database_url
from database import SessionLocal,get_db
from models import AuditLog,CrawlJob,Role,Source,User
from tasks import crawl_source


def test_health_endpoints_database_ready_redis_optional(client):
    live=client.get("/health/live")
    assert live.status_code == 200 and live.json()["status"] == "alive"
    ready=client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
    assert ready.json()["redis"] == "unavailable"
    assert ready.json()["status"] == "degraded"


def test_readiness_fails_only_when_database_is_unavailable(client):
    class BrokenSession:
        def execute(self,*_args,**_kwargs): raise RuntimeError("database unavailable")
        def rollback(self): pass

    def broken_db(): yield BrokenSession()
    app.dependency_overrides[get_db]=broken_db
    try:
        response=client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["database"] == "unavailable"
    finally:
        app.dependency_overrides.pop(get_db,None)


def test_railway_database_url_and_production_settings(monkeypatch):
    assert normalize_database_url("postgresql://u:p@host:5432/db") == "postgresql+psycopg://u:p@host:5432/db"
    assert normalize_database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    monkeypatch.setenv("ENVIRONMENT","production")
    monkeypatch.setenv("DATABASE_URL","postgresql://u:p@host:5432/db")
    monkeypatch.setenv("REDIS_URL","redis://redis.internal:6379/0")
    monkeypatch.setenv("JWT_SECRET","x"*64)
    monkeypatch.setenv("ALLOWED_ORIGINS","https://one.example.com, https://two.example.com/")
    monkeypatch.setenv("CRAWL_USER_AGENT","Schneider-Sales-Intelligence/1.0 contact=compliance@example.com")
    monkeypatch.setenv("PORT","4321")
    get_settings.cache_clear()
    try:
        configured=get_settings()
        assert configured.database_url.startswith("postgresql+psycopg://")
        assert configured.allowed_origins == ("https://one.example.com","https://two.example.com")
        assert configured.port == 4321
        assert configured.seed_demo_data is False
    finally:
        get_settings.cache_clear()


def test_production_rejects_wildcard_cors_and_demo_seed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT","production")
    monkeypatch.setenv("DATABASE_URL","postgresql://u:p@host:5432/db")
    monkeypatch.setenv("REDIS_URL","redis://redis.internal:6379/0")
    monkeypatch.setenv("JWT_SECRET","x"*64)
    monkeypatch.setenv("CRAWL_USER_AGENT","Schneider-Sales-Intelligence/1.0 contact=compliance@example.com")
    monkeypatch.setenv("ALLOWED_ORIGINS","*")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError,match="ALLOWED_ORIGINS"):
        get_settings()
    monkeypatch.setenv("ALLOWED_ORIGINS","https://frontend.example.com")
    monkeypatch.setenv("SEED_DEMO_DATA","true")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError,match="SEED_DEMO_DATA"):
        get_settings()
    get_settings.cache_clear()


def test_celery_uses_redis_and_utc_and_manual_sources_are_not_runnable():
    assert celery.conf.enable_utc is True
    assert celery.conf.timezone == "UTC"
    assert celery.conf.broker_url.startswith("redis://")
    assert crawl_source.app is celery
    assert crawl_source.app.connection_for_write().as_uri().startswith("redis://")
    with SessionLocal() as db:
        manual=db.scalar(select(Source).where(Source.crawl_method == "manual_import"))
        assert manual and crawl_source.run(manual.id)["status"] == "not_runnable"


def test_manual_crawl_is_sent_through_configured_celery_app(client,admin_headers,monkeypatch):
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.enabled.is_(True),Source.adapter_status == "active"))
        assert source
        source_id=source.id

    sent={}

    def fake_send_task(name,args):
        sent["name"]=name
        sent["args"]=args
        return SimpleNamespace(id="celery-test-task")

    monkeypatch.setattr(api_module.celery,"send_task",fake_send_task)
    response=client.post(f"/api/sources/{source_id}/run",headers=admin_headers)
    assert response.status_code == 202
    assert sent == {"name":"tasks.crawl_source","args":[source_id,response.json()["job_id"]]}
    with SessionLocal() as db:
        job=db.get(CrawlJob,response.json()["job_id"])
        assert job and job.status == "queued" and job.celery_task_id == "celery-test-task"


def test_first_admin_bootstrap_is_one_time_and_audited(capsys):
    with SessionLocal() as db:
        current=db.scalar(select(User).join(Role).where(Role.name == "admin"))
        db.delete(current); db.commit()
    args=SimpleNamespace(email="first-admin@example.com",name="首位管理员",generate_password=True,password_env=None)
    bootstrap_admin(args)
    output=capsys.readouterr().out
    assert "ONE-TIME GENERATED PASSWORD" in output
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "first-admin@example.com"))
        assert db.scalar(select(AuditLog).where(AuditLog.action == "bootstrap.admin_created"))
    with pytest.raises(SystemExit,match="administrator already exists"):
        bootstrap_admin(args)
