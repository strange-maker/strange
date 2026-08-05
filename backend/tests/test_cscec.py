from datetime import timedelta
from types import SimpleNamespace

import requests
from sqlalchemy import func, select

import api
import crawl_service
import tasks
from adapters.base import SourceItem
import adapters.cscec as cscec_adapters
from adapters.cscec import (
    CSCECNewsAdapter,
    CSCECOrganizationAdapter,
    CSCECPDFAnnouncementAdapter,
    _parse_cscec_date,
)
from adapters.registry import get_adapter_definition
from cscec import (
    capture_page_snapshot,
    classify_leadership_event,
    classify_org_change,
    is_plausible_person_name,
    load_cscec_entities,
    normalize_cscec_entity_name,
    parse_cscec_organization,
    record_cscec_article_events,
)
from database import SessionLocal
from ingestion import ingest_item
from models import Article, CSCECLeadershipEvent, CSCECOrgEvent, PageDiff, Source, utcnow
from crawl_service import execute_crawl
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


def _pdf_response(url: str, content: bytes = b"%PDF-1.7 test") -> requests.Response:
    response=requests.Response()
    response.status_code=200
    response.url=url
    response.headers["content-type"]="application/pdf"
    response.headers["content-length"]=str(len(content))
    response._content=content
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


def test_cscec_pdf_announcement_adapter_selects_recent_and_governance_items(monkeypatch):
    html="""<section>
      <ul class="yxj-list">
        <li><span>2026-06-17</span><a href="./2026/P0201.pdf">中国建筑临时股东会会议资料</a></li>
        <li><span>2026-05-20</span><a href="./2026/P0202.pdf">中国建筑关于独立董事辞任的公告</a></li>
        <li><span>2026-03-12</span><a href="./2026/P0203.pdf">中国建筑关于公司高级管理人员离任的公告</a></li>
      </ul>
      <ul class="yxj-list">
        <li><span>2025-12-01</span><a href="./2025/P0204.pdf">中国建筑年度普通公告</a></li>
      </ul>
    </section>"""
    adapter=CSCECPDFAnnouncementAdapter(
        "https://www.cscec.com/tzzgxnew/tzgg_new/",
        {"recent_limit":1,"priority_limit":10,"priority_lookback_days":1000},
    )
    monkeypatch.setattr(adapter,"_get",lambda *_args,**_kwargs:_html_response(adapter.source_url,html))
    items=adapter.fetch_list()
    assert [item.title for item in items] == [
        "中国建筑临时股东会会议资料",
        "中国建筑关于独立董事辞任的公告",
        "中国建筑关于公司高级管理人员离任的公告",
    ]
    assert all(item.url.endswith(".pdf") for item in items)
    assert all(item.raw["document_format"] == "pdf" for item in items)
    assert items[1].published_at.isoformat().startswith("2026-05-20")


def test_cscec_pdf_announcement_adapter_extracts_text_and_marks_scans(monkeypatch):
    url="https://www.cscec.com/tzzgxnew/tzgg_new/2026/P0202.pdf"
    adapter=CSCECPDFAnnouncementAdapter("https://www.cscec.com/tzzgxnew/tzgg_new/")
    item=SourceItem(
        title="中国建筑关于独立董事辞任的公告",
        url=url,
        published_at=_parse_cscec_date("2026-05-20"),
        raw={"document_format":"pdf"},
    )
    monkeypatch.setattr(adapter,"_get",lambda *_args,**_kwargs:_pdf_response(url))
    monkeypatch.setattr(
        cscec_adapters,
        "extract_pdf_text",
        lambda *_args,**_kwargs:"公司独立董事马王军先生提交辞职报告，申请辞去独立董事职务。",
    )
    detailed=adapter.fetch_detail(item)
    assert detailed.raw["pdf_text_status"] == "extracted"
    assert detailed.raw["pdf_text_length"] > 20
    assert "马王军" in detailed.excerpt

    scanned=SourceItem(title="中国建筑扫描版公告",url=url,raw={"document_format":"pdf"})
    monkeypatch.setattr(cscec_adapters,"extract_pdf_text",lambda *_args,**_kwargs:"")
    scanned=adapter.fetch_detail(scanned)
    assert scanned.raw["pdf_text_status"] == "requires_ocr"
    assert "需 OCR" in scanned.excerpt


def test_cscec_pdf_announcement_backfill_is_batched(monkeypatch):
    adapter=CSCECPDFAnnouncementAdapter(
        "https://www.cscec.com/tzzgxnew/tzgg_new/",
        {"backfill_batch_size":2},
    )
    adapter._catalog_cache=[
        SourceItem(title=f"中国建筑公告{i}",url=f"https://www.cscec.com/{i}.pdf")
        for i in range(5)
    ]
    monkeypatch.setattr(adapter,"fetch_detail",lambda item:item)
    first=adapter.fetch_backfill()
    second=adapter.fetch_backfill(page=2,cursor=first.next_cursor)
    assert len(first.items) == 2 and first.next_cursor == "2" and first.exhausted is False
    assert len(second.items) == 2 and second.next_cursor == "4" and second.exhausted is False


def test_cscec_source_family_is_registered_and_pending_sources_activate():
    definition=get_adapter_definition("中建四局新闻","https://4bur.cscec.com/",{
        "ka_focus":"cscec","source_type":"official","crawl_method":"html",
    })
    assert definition and definition["initial_status"] == "active"
    pdf_definition=get_adapter_definition(
        "中国建筑投资者服务",
        "https://www.cscec.com/tzzgxnew/tzgg_new/",
        {"ka_focus":"cscec","source_type":"stock_disclosure","crawl_method":"html"},
    )
    assert pdf_definition["class"] is CSCECPDFAnnouncementAdapter
    assert pdf_definition["fetch_detail"] is True
    assert pdf_definition["supports_backfill"] is True
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


def test_verified_cscec_source_urls_are_synchronized():
    expected = {
        "中建二局新闻": "https://2bur.cscec.com/",
        "中建三局新闻": "https://3bur.cscec.com/",
        "中建设计研究院新闻": "https://ccdc.cscec.com/",
        "中建西南院新闻": "https://xnjz.cscec.com/",
        "中建西北院新闻": "https://nwin.cscec.com/",
        "中国建筑投资者服务": "https://www.cscec.com/tzzgxnew/tzgg_new/",
    }
    with SessionLocal() as db:
        rows = db.scalars(select(Source).where(Source.source_name.in_(expected))).all()
        assert {row.source_name: row.source_url for row in rows} == expected
        assert all(row.adapter_status == "active" for row in rows)


def test_one_stale_detail_page_does_not_fail_the_source(monkeypatch):
    class FakeAdapter:
        last_http_status = 200

        def fetch_list(self):
            return [SourceItem(
                title="中建钢构摩洛哥盖马高铁项目首批构件发运",
                url="https://www.cscec.com/test-stale-detail",
                published_at=utcnow(),
                excerpt="摩洛哥高铁项目进入构件发运阶段。",
                language="zh",
            )]

        def fetch_detail(self, _item):
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError("404 Client Error: stale detail page", response=response)

    monkeypatch.setattr(crawl_service, "build_adapter", lambda *_args, **_kwargs: FakeAdapter())
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_name == "中国建筑企业动态"))
        source.adapter_status = "active"
        source.enabled = True
        source.adapter_config = {**source.adapter_config, "fetch_detail": True}
        db.commit()
        run = execute_crawl(db, source)
        assert run.status == "success"
        assert run.fetched_count == 1
        assert run.new_count == 1
        assert db.scalar(select(Article).where(Article.original_url.like("%test-stale-detail%")))


def test_leadership_activity_is_not_misclassified_as_appointment():
    appointment=classify_leadership_event("任命张三为中国建筑某公司董事长")
    meeting=classify_leadership_event("党委书记李明赴海外调研并出席会议")
    assert appointment and appointment["role_change"] is True
    assert appointment["appointment_type"] == "appointment"
    assert meeting and meeting["role_change"] is False
    assert meeting["appointment_type"] == "overseas_visit"
    resignation=classify_leadership_event(
        "公司董事会于2026年5月19日收到公司独立董事马王军先生提交的辞职报告，"
        "马王军先生申请辞去公司独立董事及董事会专门委员会相关职务。"
    )
    assert resignation and resignation["appointment_type"] == "resignation"
    assert resignation["person_name"] == "马王军"
    assert resignation["title_before"] == "独立董事"
    assert classify_org_change("公司名称变更并完成更名") == "renamed"


def test_leadership_parser_rejects_pdf_prose_as_person_names():
    false_positive_documents = (
        "股东如有任何问题，可以在会议期间向董事会提出。董事出席本次股东会会议。",
        "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述。近日签署项目协议。",
        "董事和高级管理人员不得以任何方式损害公司利益，本规定经董事会会议审议通过。",
    )
    for text in false_positive_documents:
        assert classify_leadership_event(text) is None
    for token in ("股东如有", "容不存在", "不得以"):
        assert is_plausible_person_name(token) is False


def test_leadership_parser_keeps_named_official_activity():
    event = classify_leadership_event("中国建筑董事长郑学选先生赴海外调研并出席会议")
    assert event
    assert event["person_name"] == "郑学选"
    assert event["appointment_type"] == "overseas_visit"


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


def test_stock_disclosure_pdf_records_named_cscec_resignation():
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中国建筑投资者服务"))
        result=ingest_item(db,source,SourceItem(
            title="中国建筑关于独立董事辞任的公告",
            url="https://www.cscec.com/tzzgxnew/tzgg_new/2026/test-resignation.pdf",
            published_at=utcnow(),
            excerpt=(
                "公司董事会收到公司独立董事马王军先生提交的辞职报告，"
                "马王军先生申请辞去公司独立董事及董事会专门委员会相关职务。"
            ),
            language="zh",
            raw={"document_format":"pdf","pdf_text_status":"extracted"},
        ))
        db.commit()
        assert result == "new"
        article=db.scalar(select(Article).where(Article.original_url.like("%test-resignation.pdf")))
        event=db.scalar(
            select(CSCECLeadershipEvent).where(
                CSCECLeadershipEvent.article_id == article.id,
                CSCECLeadershipEvent.person_name == "马王军",
            )
        )
        assert article.source_type == "stock_disclosure"
        assert article.is_primary_source is True
        assert article.is_overseas is False
        assert event and event.appointment_type == "resignation"


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


def _add_cscec_article(db, source: Source, title: str, days_ago: int, *, country: str | None, region: str | None, content: str, intelligence_types: list[str] | None=None, is_overseas: bool=False) -> Article:
    url=f"https://www.cscec.com/test/{abs(hash(title))}.html"
    article=Article(
        title=title,
        original_title=title,
        summary=content[:220],
        sales_insight="测试销售洞察",
        original_url=url,
        canonical_url=url,
        primary_source_id=source.id,
        source_name=source.source_name,
        source_type=source.source_type,
        reliability_level=source.reliability_level,
        published_at=utcnow()-timedelta(days=days_ago),
        fetched_at=utcnow(),
        content_excerpt=content,
        content_hash=f"{abs(hash(title)):064x}"[:64],
        language="zh",
        country=country,
        region=region,
        ka=["中国建筑"],
        subsidiary=[],
        industries=["基础设施"],
        intelligence_types=intelligence_types or ["ka_company"],
        matched_entities=[],
        ka_candidates=[],
        date_verification_status="verified",
        overseas_evidence=[f"项目位于{country}"] if is_overseas and country else [],
        ka_match_evidence=["标题命中中国建筑"],
        confidence_score=.92,
        verification_status="source_verified",
        is_primary_source=True,
        is_overseas=is_overseas,
        is_demo=False,
    )
    db.add(article);db.flush()
    return article


def test_cscec_events_show_sales_relevant_items_with_overseas_priority(client,admin_headers):
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中国建筑企业动态"))
        assert source is not None
        _add_cscec_article(
            db,source,"中国建筑与沙特业主签署新能源基础设施合作协议",2,
            country="沙特阿拉伯",region="中东",
            content="中国建筑与沙特业主签署新能源基础设施合作协议，双方将在海外基础设施项目上开展合作。",
            intelligence_types=["market_project","ka_company"],is_overseas=True,
        )
        _add_cscec_article(
            db,source,"中建三局与湖北某产业集团签署战略合作协议",1,
            country="中国",region="中国",
            content="中建三局与湖北某产业集团签署战略合作协议，围绕产业园、城市更新和基础设施建设开展合作。",
            intelligence_types=["ka_company"],is_overseas=False,
        )
        _add_cscec_article(
            db,source,"中国建筑2026年第一次临时股东会会议资料",0,
            country="中国",region="中国",
            content="中国建筑2026年第一次临时股东会会议资料，包含会议议程、议案和股东表决事项。",
            intelligence_types=["ka_company"],is_overseas=False,
        )
        _add_cscec_article(
            db,source,"中国建筑发布投资者关系管理制度",0,
            country="中国",region="中国",
            content="中国建筑发布投资者关系管理制度，规范投资者沟通和信息披露事项。",
            intelligence_types=["ka_company"],is_overseas=False,
        )
        db.commit()

    response=client.get("/api/ka/cscec/events",headers=admin_headers)
    assert response.status_code == 200
    items=response.json()["items"]
    titles=[item["title"] for item in items]
    assert titles[:2] == [
        "中国建筑与沙特业主签署新能源基础设施合作协议",
        "中建三局与湖北某产业集团签署战略合作协议",
    ]
    assert "中国建筑2026年第一次临时股东会会议资料" not in titles
    assert "中国建筑发布投资者关系管理制度" not in titles
    assert items[0]["country"] == "沙特阿拉伯"
    assert items[0]["region"] == "中东"


def test_cscec_leadership_and_org_events_include_sales_display_metadata(client,admin_headers):
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "中国建筑企业动态"))
        article=_add_cscec_article(
            db,source,"中国建筑董事长郑学选会见阿联酋能源企业负责人",3,
            country="阿联酋",region="中东",
            content="中国建筑董事长郑学选会见阿联酋能源企业负责人，双方围绕能源基础设施建设合作深入交流。",
            intelligence_types=["ka_leader","ka_company"],is_overseas=True,
        )
        db.add(CSCECLeadershipEvent(
            event_key="test-zheng-xuexuan-meeting",
            article_id=article.id,
            person_name="郑学选",
            entity_id="cscec-listed",
            title_after="董事长",
            appointment_type="meeting",
            effective_date=article.published_at,
            published_at=article.published_at,
            source_url=article.original_url,
            source_name=source.source_name,
            evidence_excerpt=article.content_excerpt,
            confidence=.9,
            verification_status="source_verified",
        ))
        db.add(CSCECOrgEvent(
            event_key="test-saudi-project-company-established",
            article_id=article.id,
            change_type="established",
            entity_before="中国建筑股份有限公司",
            entity_after="中国建筑股份有限公司",
            source_urls=[article.original_url],
            source_count=1,
            published_at=article.published_at,
            evidence_excerpt="中国建筑在沙特设立新能源基础设施项目公司，服务当地能源基础设施合作。",
            confidence=.88,
            verification_status="source_verified",
        ))
        db.commit()

    leadership=client.get("/api/ka/cscec/leadership-events",headers=admin_headers).json()
    meeting=next(item for item in leadership if item["person_name"] == "郑学选")
    assert meeting["counterparty"] == "阿联酋能源企业"
    assert meeting["country"] == "阿联酋"
    assert meeting["region"] == "中东"

    orgs=client.get("/api/ka/cscec/org-events",headers=admin_headers).json()
    org=next(item for item in orgs if item["change_type"] == "established")
    assert org["display_title"] == "设立：沙特新能源基础设施项目公司"
    assert org["display_title"] != "中国建筑股份有限公司 → 中国建筑股份有限公司"


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
