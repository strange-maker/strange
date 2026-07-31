from datetime import timedelta
from types import SimpleNamespace

import requests
from sqlalchemy import func, select

import api
import tasks
from adapters.base import SourceItem
from adapters.cscec import CSCECNewsAdapter, CSCECOrganizationAdapter, _parse_cscec_date
from adapters.registry import get_adapter_definition
from cscec import (
    capture_page_snapshot,
    classify_leadership_event,
    classify_org_change,
    load_cscec_entities,
    normalize_cscec_entity_name,
    parse_cscec_organization,
    record_cscec_article_events,
)
from database import SessionLocal
from ingestion import ingest_item
from models import Article, CSCECLeadershipEvent, CSCECOrgEvent, PageDiff, Source, utcnow
from source_service import sync_sources


def test_master_is_complete_and_preserves_sensitive_names():
    rows=load_cscec_entities()
    by_id={row["entity_id"]:row for row in rows}
    assert len(rows) >= 80
    assert by_id["cscec-listed"]["stock_code"] == "601668.SH"
    assert "远东环球" in by_id["cscec-far-east"]["aliases"]
    assert by_id["cscec-far-east"]["verification_status"] == "renamed"
    assert by_id["cscec-installation"]["canonical_name"] == "中建安装集团有限公司"
    assert any(row["overseas"] and row["official_url"] is None for row in rows)


def test_exact_alias_normalization_does_not_merge_port_entities():
    assert normalize_cscec_entity_name("  中建一局&nbsp;")["entity_id"] == "cscec-1b"
    assert normalize_cscec_entity_name("远东环球")["entity_id"] == "cscec-far-east"
    assert normalize_cscec_entity_name("中建港航局")["entity_id"] == "cscec-port-hang"
    assert normalize_cscec_entity_name("中建筑港")["entity_id"] == "cscec-port"
    assert normalize_cscec_entity_name("中建港务")["entity_id"] == "cscec-harbour"
    assert normalize_cscec_entity_name("中建港") is None


def test_organization_parser_and_date_parser():
    html="""<section>
      <a href="https://1bur.cscec.com/">中国建筑一局（集团）有限公司</a>
      <a href="/member/no-site">中建测试机构</a>
      <a href="javascript:void(0)">普通链接</a>
    </section>"""
    rows=parse_cscec_organization(html)
    assert rows[0]["canonical_name"] == "中国建筑一局（集团）有限公司"
    assert rows[0]["official_url"] == "https://1bur.cscec.com/"
    assert rows[1]["official_url"].startswith("https://www.cscec.com/")
    assert _parse_cscec_date("2026年7月29日").year == 2026
    assert _parse_cscec_date("07-29").month == 7


def _html_response(url: str, html: str) -> requests.Response:
    response=requests.Response()
    response.status_code=200
    response.url=url
    response.encoding="utf-8"
    response._content=html.encode("utf-8")
    return response


def test_cscec_news_adapter_discovers_news_section_and_wechat_leads(monkeypatch):
    homepage="""<nav><a href="/xwzx/gsyw/">公司要闻</a></nav>"""
    listing="""<ul class="news-list">
      <li><a href="/xwzx/gsyw/202607/1234567.html">中建四局海外项目取得新进展</a><span class="date">2026-07-29</span></li>
      <li><a href="https://mp.weixin.qq.com/s/demo">中建四局主要领导赴项目调研</a><span>2026年7月28日</span></li>
    </ul>"""
    adapter=CSCECNewsAdapter("https://4bur.cscec.com/",{
        "endpoint":"https://4bur.cscec.com/",
        "auto_discover_news":True,
        "include_wechat_index_leads":True,
    })
    def fake_get(url: str,**_kwargs):
        return _html_response(url,listing if "/xwzx/gsyw" in url else homepage)
    monkeypatch.setattr(adapter,"_get",fake_get)
    items=adapter.fetch_list()
    assert len(items) == 2
    assert items[0].published_at and items[0].published_at.year == 2026
    wechat=next(item for item in items if "mp.weixin.qq.com" in item.url)
    assert wechat.raw["wechat_link_only"] is True
    monkeypatch.setattr(adapter,"_get",lambda *_args,**_kwargs:(_ for _ in ()).throw(AssertionError("WeChat body must not be auto-fetched")))
    assert "正文未自动抓取" in adapter.fetch_detail(wechat).excerpt


def test_cscec_source_family_is_registered_and_pending_sources_activate():
    definition=get_adapter_definition("中建四局新闻","https://4bur.cscec.com/",{
        "ka_focus":"cscec","source_type":"official","crawl_method":"html",
    })
    assert definition and definition["initial_status"] == "active"
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中建四局新闻"))
        source.adapter_status="pending_adapter"
        source.enabled=False
        db.commit()
        sync_sources(db)
        db.refresh(source)
        assert source.adapter_status == "active"
        assert source.enabled is True
        assert source.adapter_config["auto_discover_news"] is True


def test_leadership_activity_is_not_misclassified_as_appointment():
    appointment=classify_leadership_event("任命张三为中国建筑某公司董事长")
    meeting=classify_leadership_event("党委书记李明赴海外调研并出席会议")
    assert appointment and appointment["role_change"] is True
    assert appointment["appointment_type"] == "appointment"
    assert meeting and meeting["role_change"] is False
    assert meeting["appointment_type"] == "overseas_visit"
    assert classify_org_change("公司名称变更并完成更名") == "renamed"


def test_page_snapshot_is_idempotent_and_creates_review_diff():
    with SessionLocal() as db:
        first,diff=capture_page_snapshot(db,"https://example.com/org","<h1>中建一局</h1>","organization")
        db.commit()
        assert diff is None
        same,diff=capture_page_snapshot(db,"https://example.com/org","<h1>中建一局</h1>","organization")
        assert same.id == first.id and diff is None
        _snapshot,diff=capture_page_snapshot(db,"https://example.com/org","<h1>中建一局</h1><p>中建二局有限公司</p>","organization")
        db.commit()
        assert diff and diff.verification_status == "pending_review"
        assert db.scalar(select(func.count(PageDiff.id))) == 1


def test_cscec_event_deduplication():
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中国建筑官网"))
        article=Article(
            title="任命张三为中建一局董事长",
            original_title="任命张三为中建一局董事长",
            summary="公开任免",
            sales_insight="核验后跟进",
            original_url="https://www.cscec.com/test-appointment",
            canonical_url="https://www.cscec.com/test-appointment",
            primary_source_id=source.id,
            source_name=source.source_name,
            source_type="official",
            reliability_level="high",
            published_at=utcnow(),
            fetched_at=utcnow(),
            content_excerpt="中国建筑发布任免决定，任命张三为中建一局董事长。",
            content_hash="a"*64,
            language="zh",
            country="中国",
            region="中国",
            ka=["中国建筑"],
            subsidiary=[],
            industries=[],
            intelligence_types=["ka_leader"],
            matched_entities=[],
            ka_candidates=[],
            date_verification_status="verified",
            overseas_evidence=[],
            ka_match_evidence=[],
            confidence_score=.9,
            verification_status="source_verified",
            is_primary_source=True,
            is_overseas=True,
            is_demo=False,
        )
        db.add(article);db.flush()
        record_cscec_article_events(db,article,source)
        record_cscec_article_events(db,article,source)
        db.commit()
        assert db.scalar(select(func.count(CSCECLeadershipEvent.id))) == 1


def test_domestic_cscec_governance_is_kept_out_of_overseas_feed_but_recorded():
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中建四局新闻"))
        result=ingest_item(db,source,SourceItem(
            title="任命张三为中建四局某公司董事长",
            url="https://4bur.cscec.com/xwzx/gsyw/202607/7654321.html",
            published_at=utcnow(),
            excerpt="中建四局发布干部任免决定，任命张三为某公司董事长。",
            language="zh",
        ))
        db.commit()
        assert result == "new"
        article=db.scalar(select(Article).where(Article.title.like("任命张三%")))
        assert article and article.is_overseas is False
        assert db.scalar(select(func.count(CSCECLeadershipEvent.id))) == 1


def test_official_index_wechat_link_is_low_confidence_lead():
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中建五局新闻"))
        result=ingest_item(db,source,SourceItem(
            title="中建五局党委书记李明赴项目调研",
            url="https://mp.weixin.qq.com/s/example-lead",
            published_at=utcnow(),
            excerpt="中建五局党委书记李明赴项目调研。",
            language="zh",
            raw={"wechat_link_only":True,"official_index_url":"https://5bur.cscec.com/xwzx/wjyw/"},
        ))
        db.commit()
        assert result == "new"
        article=db.scalar(select(Article).where(Article.original_url.like("%example-lead%")))
        assert article.source_type == "wechat_manual"
        assert article.reliability_level == "low"
        assert article.is_primary_source is False


def test_cscec_api_and_manual_only_sources(client,admin_headers):
    entities=client.get("/api/ka/cscec/entities",headers=admin_headers)
    assert entities.status_code == 200
    assert entities.json()["count"] >= 80
    sources=client.get("/api/sources",headers=admin_headers).json()
    wechat=[row for row in sources if row["source_name"] == "中国建筑公众号"][0]
    assert wechat["adapter_status"] == "manual_only"
    assert wechat["crawl_method"] == "manual_import"
    assert wechat["entity_id"] == "cscec-listed"


def test_cscec_batch_duplicate_guard(client,admin_headers,monkeypatch):
    monkeypatch.setattr(api.celery,"send_task",lambda *_args,**_kwargs:SimpleNamespace(id="cscec-task"))
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中国建筑企业动态"))
        source.adapter_status="active";source.enabled=True;db.commit()
    first=client.post("/api/admin/crawl/cscec/all",headers=admin_headers,json={"entity_ids":["cscec-listed"]})
    assert first.status_code == 202
    second=client.post("/api/admin/crawl/cscec/all",headers=admin_headers,json={"entity_ids":["cscec-listed"]})
    assert second.status_code == 409


def test_daily_entity_task_records_snapshot(monkeypatch):
    class FakeAdapter:
        last_html="<a href='https://1bur.cscec.com/'>中国建筑一局（集团）有限公司</a>"
        def fetch_list(self):
            return [SimpleNamespace(raw={"entity_discovery":True,"canonical_name":"中国建筑一局（集团）有限公司","official_url":"https://1bur.cscec.com/"})]
    monkeypatch.setattr(tasks,"build_adapter",lambda *_args,**_kwargs:FakeAdapter())
    class Lock:
        def acquire(self,blocking=False): return True
        def owned(self): return True
        def release(self): return None
    monkeypatch.setattr(tasks.redis_client,"lock",lambda *_args,**_kwargs:Lock())
    result=tasks.sync_cscec_entity_master.run()
    assert result["status"] == "completed"
    assert result["master_count"] >= 80
