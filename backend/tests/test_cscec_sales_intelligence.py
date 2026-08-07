from datetime import timedelta

from sqlalchemy import String, select

from database import SessionLocal
from models import (
    Article,
    CSCECLeadershipEvent,
    CSCECOrgEvent,
    Source,
    utcnow,
)
from cscec import cscec_org_display_title, record_cscec_article_events


def _cscec_source(db):
    source = db.scalar(
        select(Source).where(Source.source_tags.cast(String).ilike("%cscec%"))
    )
    if source is None:
        source = db.scalar(select(Source).where(Source.source_type == "official"))
    assert source is not None
    return source


def _article(db, source, *, title, url, score, event_id, days_ago=0):
    row = Article(
        title=title,
        display_title=title,
        original_title=title,
        summary="",
        sales_insight="",
        original_url=url,
        canonical_url=url,
        primary_source_id=source.id,
        source_name=source.source_name,
        source_type=source.source_type,
        reliability_level=source.reliability_level,
        published_at=utcnow() - timedelta(days=days_ago),
        fetched_at=utcnow(),
        content_excerpt=title,
        content_hash=f"{abs(hash(url)):064x}"[:64],
        language="zh",
        country="吉尔吉斯斯坦",
        region="中亚",
        ka=["中国建筑"],
        subsidiary=["中建五局"],
        industries=[],
        intelligence_types=["ka_company"],
        matched_entities=["中国建筑第五工程局有限公司"],
        external_parties=["吉尔吉斯斯坦交通和通信部"],
        event_types=["政府交流", "项目推进", "海外考察"],
        involved_leaders=[{"name": "田卫国", "title": "中建五局董事长"}],
        involved_departments=["中建五局海外事业部"],
        industry_tags=["交通基础设施", "道路"],
        product_opportunity_tags=["中低压配电", "能源管理"],
        topic_tags=["ka_dynamic"],
        ka_candidates=[],
        date_verification_status="verified",
        canonical_event_id=event_id,
        project_stage="前期交流/拟合作",
        overseas_evidence=["吉尔吉斯斯坦"],
        ka_match_evidence=["中建五局"],
        confidence_score=.9,
        verification_status="source_verified",
        cross_source_count=1,
        is_primary_source=True,
        review_status="pending",
        is_overseas=True,
        is_demo=False,
        sales_relevance_score=score,
        sales_score_evidence={"project_opportunity": {"score": 23}},
        sales_signal="吉尔吉斯斯坦政府与中建五局讨论拟合作项目后续推进。",
        sales_opportunity="可能形成中低压配电和能源管理机会。",
        recommended_contact="中建五局海外事业部",
        recommended_action="建议联系中建五局海外事业部确认项目和设计节点。",
        evidence_excerpt=title,
    )
    db.add(row)
    db.flush()
    return row


def test_cscec_events_use_sales_score_filters_and_canonical_dedup(
    client, admin_headers
):
    with SessionLocal() as db:
        source = _cscec_source(db)
        _article(
            db,
            source,
            title="吉尔吉斯斯坦交通和通信部到中建五局调研交流",
            url="https://example.com/cscec/high-primary",
            score=88,
            event_id="same-sales-event",
        )
        duplicate = _article(
            db,
            source,
            title="中建五局推进吉尔吉斯斯坦交通基础设施合作",
            url="https://example.com/cscec/high-copy",
            score=60,
            event_id="same-sales-event",
        )
        duplicate.is_primary_source = False
        _article(
            db,
            source,
            title="中建五局开展内部培训",
            url="https://example.com/cscec/low",
            score=12,
            event_id="low-sales-event",
        )
        db.commit()

    response = client.get(
        "/api/ka/cscec/events",
        headers=admin_headers,
        params={
            "country": "吉尔吉斯斯坦",
            "external_party": "交通和通信部",
            "event_type": "项目推进",
            "sales_value": "high",
            "sort": "sales_relevance_desc",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["display_title"] == "吉尔吉斯斯坦交通和通信部到中建五局调研交流"
    assert data["items"][0]["sales_relevance_score"] == 88
    assert data["items"][0]["canonical_event_id"] == "same-sales-event"


def test_record_cscec_business_activity_does_not_infer_appointment():
    with SessionLocal() as db:
        source = _cscec_source(db)
        article = _article(
            db,
            source,
            title="吉尔吉斯斯坦交通和通信部到中建五局调研交流",
            url="https://example.com/cscec/leadership-business",
            score=88,
            event_id="leadership-business-event",
        )
        article.content_excerpt = (
            "吉尔吉斯斯坦交通和通信部代表团到访中建五局。"
            "中建五局董事长田卫国参加，双方讨论拟合作项目后续推进计划。"
            "中建五局海外事业部参加。"
        )
        record_cscec_article_events(db, article, source)
        db.commit()

        event = db.scalar(
            select(CSCECLeadershipEvent).where(
                CSCECLeadershipEvent.article_id == article.id,
                CSCECLeadershipEvent.person_name == "田卫国",
            )
        )
        assert event is not None
        assert event.event_category == "business_activity"
        assert event.activity_type == "government_exchange"
        assert event.appointment_type == "meeting"
        assert event.title_after is None
        assert event.external_party == "吉尔吉斯斯坦交通和通信部"
        assert event.country == "吉尔吉斯斯坦"
        assert event.sales_impact
        assert event.recommended_action


def test_org_display_title_prefers_verified_change_keyword():
    row = CSCECOrgEvent(
        event_key="org-display-title",
        change_type="established",
        entity_before="中国建筑股份有限公司",
        entity_after="中国建筑股份有限公司",
        display_title="中建某局成立东南亚区域总部",
        source_urls=["https://example.com/org"],
        evidence_excerpt="中建某局成立东南亚区域总部，负责区域市场开发。",
    )

    assert cscec_org_display_title(row) == "中建某局成立东南亚区域总部"
