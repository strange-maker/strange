from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select

import api
import tasks
from adapters.base import BackfillPage, SourceItem
from database import SessionLocal
from ingestion import ingest_item
from intelligence import classify_intelligence, extract_leader_event, match_ka_candidates, policy_dimensions
from models import (
    Article, AuditLog, BackfillCheckpoint, BackfillRun, CanonicalEvent,
    CanonicalProject, CrawlBatch, CrawlBatchItem, Role, Source, User, utcnow,
)


def article_row(title: str, published_at: datetime | None, country: str, region: str) -> Article:
    slug=title.lower().replace(" ","-")
    return Article(
        title=title, original_title=title, original_url=f"https://example.com/{slug}",
        canonical_url=f"https://example.com/{slug}", primary_source_id="test-source",
        source_name="Test", source_type="official", reliability_level="high",
        published_at=published_at, content_hash=slug[:64], country=country, region=region,
        intelligence_types=["market_project"], is_overseas=True, is_demo=False,
    )


def test_default_article_window_is_rolling_365_days_and_archive_is_admin_only(client,admin_headers):
    with SessionLocal() as db:
        source=Source(
            id="test-source", source_name="Window Source", source_url="https://example.com",
            source_type="official", reliability_level="high", region_focus=[], country_focus=[],
            industry_focus=[], source_tags=[], crawl_method="html", adapter_status="active", enabled=True,
        )
        db.add(source)
        db.add_all([
            article_row("Recent Saudi project",utcnow()-timedelta(days=364),"沙特阿拉伯","中东"),
            article_row("Old Saudi project",utcnow()-timedelta(days=366),"沙特阿拉伯","中东"),
            article_row("Date unverified project",None,"越南","东南亚"),
        ])
        db.commit()
    default=client.get("/api/articles",headers=admin_headers).json()
    assert [x["title"] for x in default["items"]] == ["Recent Saudi project"]
    archive=client.get("/api/articles?include_archive=true",headers=admin_headers).json()
    assert {x["title"] for x in archive["items"]} == {
        "Recent Saudi project","Old Saudi project","Date unverified project",
    }
    assert archive["archive_included"] is True


def test_cross_language_event_dedup_and_project_stats_do_not_double_count():
    published=datetime(2026,7,1,tzinfo=timezone.utc)
    with SessionLocal() as db:
        media=Source(
            source_name="Overseas Media",source_url="https://media.example.com",source_type="media",
            reliability_level="medium",region_focus=[],country_focus=[],industry_focus=["新能源"],
            source_tags=[],crawl_method="html",adapter_status="active",enabled=True,
        )
        official=Source(
            source_name="中国电建官网",source_url="https://powerchina.example.com",source_type="official",
            reliability_level="high",region_focus=[],country_focus=[],industry_focus=["新能源"],
            source_tags=[],crawl_method="html",adapter_status="active",enabled=True,
        )
        db.add_all([media,official]); db.flush()
        english=SourceItem(
            title="POWERCHINA wins Saudi Arabia solar EPC contract",
            url="https://media.example.com/en",published_at=published,
            excerpt="POWERCHINA wins an international solar project contract in Saudi Arabia.",
            language="en",
        )
        chinese=SourceItem(
            title="中国电建中标沙特光伏EPC合同",
            url="https://powerchina.example.com/zh",published_at=published+timedelta(days=3),
            excerpt="中国电建在沙特阿拉伯中标海外光伏项目EPC合同。",
            language="zh",
        )
        assert ingest_item(db,media,english) == "new"
        assert ingest_item(db,official,chinese) == "duplicate"
        db.commit()
        assert db.scalar(select(func.count(CanonicalEvent.id))) == 1
        assert db.scalar(select(func.count(CanonicalProject.id))) == 1
        event=db.scalar(select(CanonicalEvent))
        assert event.source_count == 2
        assert event.official_source_count == 1
        assert event.verification_status == "cross_verified"


def test_country_region_filters_share_one_opportunity_endpoint(client,admin_headers):
    with SessionLocal() as db:
        source=Source(
            id="test-source", source_name="Opportunity Source", source_url="https://example.com",
            source_type="official", reliability_level="high", region_focus=[], country_focus=[],
            industry_focus=[], source_tags=[], crawl_method="html", adapter_status="active", enabled=True,
        )
        db.add(source)
        db.add_all([
            article_row("Saudi grid",utcnow()-timedelta(days=2),"沙特阿拉伯","中东"),
            article_row("Vietnam factory",utcnow()-timedelta(days=1),"越南","东南亚"),
        ])
        db.commit()
    country=client.get("/api/opportunities?country=沙特阿拉伯",headers=admin_headers)
    region=client.get("/api/opportunities?region=东南亚",headers=admin_headers)
    assert country.status_code == 200 and country.json()["count"] == 1
    assert region.status_code == 200 and region.json()["count"] == 1


def test_weak_aliases_require_context_and_china_electric_has_multiple_candidates():
    assert match_ka_candidates("今天气温偏高","保利生活服务天气提示") == []
    candidates=match_ka_candidates(
        "中国电工签署沙特海外EPC项目合同",
        "中国电工将在沙特阿拉伯执行国际电力工程项目。",
    )
    groups={x["ka_group"] for x in candidates}
    assert {"国机","中国能建"}.issubset(groups)
    assert all(x["needs_review"] for x in candidates if x["ka_group"] in {"国机","中国能建"})


def test_policy_dimensions_and_leader_event_extraction():
    text="沙特发布外资准入与本地采购政策，本地采购比例提高至40%，并调整进口关税。"
    kinds=classify_intelligence(text,"policy")
    dimensions=policy_dimensions(text,"沙特阿拉伯",kinds,["新能源"])
    assert {"foreign_access","localization_policy","trade_tariff"}.issubset(kinds)
    assert dimensions["local_procurement_ratio"] == "40%"
    candidate=match_ka_candidates(
        "中国电建董事长张明访问沙特",
        "中国电建董事长张明在海外项目调研并会见业主。",
    )
    data={
        "intelligence_types":classify_intelligence("中国电建董事长张明访问沙特并会见业主"),
        "ka_candidates":candidate,"country":"沙特阿拉伯","published_at":utcnow(),
        "summary":"领导人调研海外项目","original_url":"https://example.com/leader",
        "source_name":"中国电建官网",
    }
    event=extract_leader_event("中国电建董事长张明访问沙特并会见业主",data)
    assert event and event["action_type"] == "meeting"
    assert event["person_name"] == "张明"
    assert event["ka_group"] == "中国电建"


def test_full_crawl_batch_skips_manual_and_blocked_and_prevents_duplicate_start(client,admin_headers,monkeypatch):
    monkeypatch.setattr(api.celery,"send_task",lambda *_args,**_kwargs:SimpleNamespace(id="task-1"))
    with SessionLocal() as db:
        runnable=db.scalar(select(Source).where(Source.adapter_status == "active"))
        manual=db.scalar(select(Source).where(Source.adapter_status == "manual_only"))
        blocked=Source(
            source_name="Blocked Source",source_url="https://blocked.example.com",
            source_type="media",reliability_level="medium",region_focus=[],country_focus=[],
            industry_focus=[],source_tags=[],crawl_method="html",adapter_status="blocked",enabled=True,
        )
        runnable.enabled=True
        db.add(blocked); db.commit()
        ids=[runnable.id,manual.id,blocked.id]
    response=client.post("/api/admin/crawl-batches",headers=admin_headers,json={"source_ids":ids})
    assert response.status_code == 202
    payload=response.json()
    assert payload["total_sources"] == 3 and payload["skipped_count"] == 2
    duplicate=client.post("/api/admin/crawl-batches",headers=admin_headers,json={"source_ids":ids})
    assert duplicate.status_code == 409
    detail=client.get(f"/api/admin/crawl-batches/{payload['id']}",headers=admin_headers).json()
    assert len(detail["items"]) == 3
    assert len([x for x in detail["items"] if x["status"] == "queued"]) == 1


def test_crawl_batch_cancel_is_admin_only_and_audited(client,admin_headers,monkeypatch):
    monkeypatch.setattr(api.celery,"send_task",lambda *_args,**_kwargs:SimpleNamespace(id="task-2"))
    monkeypatch.setattr(api.celery.control,"revoke",lambda *_args,**_kwargs:None)
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.adapter_status == "active"))
        source.enabled=True; db.commit(); source_id=source.id
    created=client.post("/api/admin/crawl-batches",headers=admin_headers,json={"source_ids":[source_id]}).json()
    cancelled=client.post(f"/api/admin/crawl-batches/{created['id']}/cancel",headers=admin_headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "crawl_batch.cancel")) is not None


def test_new_api_contracts_filters_and_admin_permissions(client,admin_headers,monkeypatch):
    created=client.post("/api/users",headers=admin_headers,json={
        "email":"sales@example.com","full_name":"外部销售试用","password":"Sales-test-password!","role":"sales",
    })
    assert created.status_code == 201
    token=client.post("/api/auth/login",json={"email":"sales@example.com","password":"Sales-test-password!"}).json()["access_token"]
    sales_headers={"Authorization":f"Bearer {token}"}
    common="date_from=2025-01-01&date_to=2026-12-31&region=中东&country=沙特阿拉伯&industry=新能源&intelligence_type=market_project&policy_type=tax_policy&ka_group=中国电建&matched_entity=中国电建&source=none&reliability=high&review_status=pending&verification_status=unverified&page=1&page_size=20&sort=published_desc"
    for endpoint in ("/api/articles","/api/opportunities","/api/ka-intelligence","/api/policies"):
        response=client.get(f"{endpoint}?{common}",headers=sales_headers)
        assert response.status_code == 200, (endpoint,response.text)
        assert {"items","count","page","page_size"}.issubset(response.json())
    assert client.get("/api/opportunities/stats",headers=sales_headers).status_code == 200
    groups=client.get("/api/ka-groups",headers=sales_headers)
    assert groups.status_code == 200 and groups.json()
    assert client.post("/api/admin/crawl-batches",headers=sales_headers,json={}).status_code == 403
    assert client.get("/api/admin/crawl-batches",headers=sales_headers).status_code == 403

    monkeypatch.setattr(api.celery,"send_task",lambda *_args,**_kwargs:SimpleNamespace(id="backfill-task"))
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.adapter_status == "active"))
        source.enabled=True; db.commit(); source_id=source.id
    backfill=client.post("/api/admin/backfills",headers=admin_headers,json={
        "source_id":source_id,"date_from":(utcnow()-timedelta(days=365)).isoformat(),
        "date_to":utcnow().isoformat(),"page_limit":3,
    })
    assert backfill.status_code == 202
    detail=client.get(f"/api/admin/backfills/{backfill.json()['id']}",headers=admin_headers)
    assert detail.status_code == 200 and detail.json()["status"] == "queued"


def test_backfill_pagination_and_checkpoint_resume(monkeypatch):
    pages_seen=[]

    class FakeAdapter:
        def fetch_backfill(self,page=1,cursor=None):
            pages_seen.append((page,cursor))
            if page == 1:
                return BackfillPage([
                    SourceItem("Saudi solar project page one","https://archive.example.com/1",utcnow()-timedelta(days=20),"","Saudi Arabia solar international project"),
                    SourceItem("Saudi undated project","https://archive.example.com/undated",None,"","Saudi Arabia international EPC project"),
                ],"2",False)
            return BackfillPage([
                SourceItem("Saudi grid project page two","https://archive.example.com/2",utcnow()-timedelta(days=200),"","Saudi Arabia transmission international project"),
            ],None,True)

    monkeypatch.setattr(tasks,"build_adapter",lambda *_args,**_kwargs:FakeAdapter())
    with SessionLocal() as db:
        source=Source(
            source_name="Archive Source",source_url="https://archive.example.com",source_type="official",
            reliability_level="high",region_focus=["中东"],country_focus=["沙特阿拉伯"],industry_focus=["新能源"],
            source_tags=[],crawl_method="api",adapter_key="archive",adapter_status="active",enabled=True,
        )
        admin=db.scalar(select(User).join(Role).where(Role.name == "admin"))
        db.add(source); db.flush()
        run=BackfillRun(
            source_id=source.id,requested_by=admin.id,date_from=utcnow()-timedelta(days=365),
            date_to=utcnow(),page_limit=5,
        )
        db.add(run); db.commit(); run_id=run.id
    result=tasks.backfill_source.run(run_id)
    assert result["status"] == "completed"
    assert pages_seen == [(1,None),(2,"2")]
    with SessionLocal() as db:
        run=db.get(BackfillRun,run_id)
        assert run.current_page == 2 and run.date_unverified_count == 1
        assert db.scalar(select(func.count(BackfillCheckpoint.id)).where(BackfillCheckpoint.backfill_run_id == run_id)) == 2

    pages_seen.clear()
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "Archive Source"))
        admin=db.scalar(select(User).join(Role).where(Role.name == "admin"))
        resumed=BackfillRun(
            source_id=source.id,requested_by=admin.id,date_from=utcnow()-timedelta(days=365),
            date_to=utcnow(),page_limit=5,current_page=1,cursor="2",
        )
        db.add(resumed); db.commit(); resumed_id=resumed.id
    result=tasks.backfill_source.run(resumed_id)
    assert result["status"] == "completed"
    assert pages_seen == [(2,"2")]
