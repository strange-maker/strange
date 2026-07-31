from __future__ import annotations

from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from adapters.base import SourceItem, canonicalize_url, content_digest
from intelligence import (
    PROJECT_TYPES,
    canonical_event_fingerprint,
    canonical_project_fingerprint,
    classify_intelligence,
    detect_action_type,
    extract_leader_event,
    match_ka_candidates,
    policy_dimensions,
    source_role,
)
from models import (
    Article, ArticleDuplicate, ArticleSource, CanonicalEvent, CanonicalProject,
    EventSource, KALeaderEvent, PolicyIntelligence, Source, utcnow,
)
from rules import detect_overseas, product_opportunities, rule_summary


def ingest_item(db: Session, source: Source, item: SourceItem, is_manual: bool = False) -> str:
    canonical=canonicalize_url(item.url)
    existing=db.scalar(select(Article).where(Article.canonical_url == canonical))
    if existing:
        existing.last_seen_at=utcnow(); _attach_source(db,existing,source,item,_is_first_party(source,item)); _promote_primary(existing,source,item)
        return "updated"

    digest=content_digest(item.title,item.excerpt)
    exact=db.scalar(select(Article).where(Article.content_hash == digest))
    if exact:
        _duplicate(db,exact,item,"content_hash",1.0); _attach_source(db,exact,source,item,_is_first_party(source,item)); _promote_primary(exact,source,item)
        return "duplicate"

    recent=db.scalars(select(Article).where(Article.published_at >= (item.published_at or utcnow()) - timedelta(days=7)).limit(100)).all()
    for candidate in recent:
        similarity=SequenceMatcher(None,candidate.title.lower(),item.title.lower()).ratio()
        if similarity >= .92:
            _duplicate(db,candidate,item,"title_similarity",similarity); _attach_source(db,candidate,source,item,_is_first_party(source,item)); _promote_primary(candidate,source,item)
            return "duplicate"

    source_context=" ".join([source.source_name,*(source.country_focus or []),*(source.region_focus or [])])
    text=f"{item.title}\n{item.excerpt}"; overseas=detect_overseas(item.title,f"{item.excerpt}\n来源范围：{source_context}")
    if not overseas["is_overseas"]:
        if _is_cscec_governance_item(source,text):
            overseas={"is_overseas":False,"country":"中国","region":"中国","overseas_confidence":.75,"overseas_evidence":["中建组织与领导动态专属监测；不进入普通海外项目情报流"]}
        elif is_manual:
            overseas={"is_overseas":True,"country":None,"region":None,"overseas_confidence":.2,"overseas_evidence":["用户手动导入，海外属性待人工核验"]}
        else:
            return "skipped"
    candidates=match_ka_candidates(item.title,item.excerpt,source.source_name,source.source_url)
    kas=list(dict.fromkeys(x["ka_group"] for x in candidates))
    matched=list(dict.fromkeys(e["alias"] for x in candidates for e in x["evidence"]))
    ka_conf=max((x["confidence"] for x in candidates),default=.35)
    effective_source_type=_effective_source_type(source,item)
    effective_reliability=_effective_reliability(source,item)
    intelligence_types=classify_intelligence(text,effective_source_type)
    products=product_opportunities(" ".join(source.industry_focus or []),text)
    first_party=_is_first_party(source,item)
    event_key=canonical_event_fingerprint(item.title,item.published_at,overseas["country"],candidates,intelligence_types)
    canonical_event=db.scalar(select(CanonicalEvent).where(CanonicalEvent.event_key == event_key))
    if canonical_event and canonical_event.primary_article_id:
        representative=db.get(Article,canonical_event.primary_article_id)
        if representative:
            _duplicate(db,representative,item,"canonical_event",max(.65,canonical_event.confidence_score))
            _attach_source(db,representative,source,item,first_party)
            _promote_primary(representative,source,item)
            return "duplicate"

    primary_type=next((x for x in intelligence_types if x in PROJECT_TYPES),None)
    article=Article(
        title=item.title, original_title=item.title, summary=rule_summary(item.excerpt or item.title),
        sales_insight="待销售团队基于已核验事实评估产品机会。" if first_party else "媒体线索，建议核验官方公告。",
        original_url=item.url, canonical_url=canonical, primary_source_id=source.id, source_name=source.source_name,
        source_type=effective_source_type, reliability_level=effective_reliability, author=item.author,
        published_at=item.published_at, content_excerpt=item.excerpt[:6000], content_hash=digest, language=item.language,
        country=overseas["country"], region=overseas["region"], ka=kas, subsidiary=[], industries=products,
        intelligence_types=intelligence_types,matched_entities=[x["matched_entity"] for x in candidates],
        ka_candidates=candidates,date_verification_status="verified" if item.published_at else "date_unverified",
        overseas_evidence=overseas["overseas_evidence"], ka_match_evidence=matched,
        confidence_score=min(.98,max(overseas["overseas_confidence"],ka_conf)),
        verification_status="source_verified" if first_party else "unverified", is_primary_source=first_party,
        review_status="pending", is_overseas=overseas["is_overseas"], is_demo=False,project_type=primary_type,
        ai_payload={"factual_summary":rule_summary(item.excerpt or item.title),"why_it_matters":"","project_stage":None,"related_ka":kas,"subsidiary":[],"country":overseas["country"],"region":overseas["region"],"opportunity_type":None,"schneider_product_opportunities":products,"recommended_sales_action":"核验项目状态并联系相关账户","evidence":overseas["overseas_evidence"],"uncertainty":["尚未经过人工审核"],"confidence":min(.98,max(overseas["overseas_confidence"],ka_conf))},
        ai_model="rules", ai_prompt_version="rules-v1", ai_generated_at=utcnow(), ai_result_version=1,
    )
    db.add(article); db.flush()
    canonical_event=_create_event_models(db,article,source,item,event_key,candidates,intelligence_types,first_party)
    article.canonical_event_id=canonical_event.id
    _attach_source(db,article,source,item,first_party)
    _add_policy_and_leader(db,article,text)
    from cscec import record_cscec_article_events
    record_cscec_article_events(db,article,source)
    return "new"


def _attach_source(db: Session, article: Article, source: Source, item: SourceItem, is_primary: bool=False) -> ArticleSource:
    exists=db.scalar(select(ArticleSource).where(ArticleSource.article_id == article.id,ArticleSource.original_url == item.url))
    if not exists:
        exists=ArticleSource(article_id=article.id,source_id=source.id,original_url=item.url,title=item.title,published_at=item.published_at,reliability_level=_effective_reliability(source,item),is_primary=is_primary,source_role=source_role(_effective_source_type(source,item),source.source_name,item.language),consistency_status="consistent")
        db.add(exists); db.flush()
    article.cross_source_count=max(1,db.scalar(select(func.count(distinct(ArticleSource.source_id))).where(ArticleSource.article_id == article.id)) or 1)
    if article.canonical_event_id:
        linked=db.scalar(select(EventSource).where(EventSource.canonical_event_id == article.canonical_event_id,EventSource.source_id == source.id,EventSource.article_id == article.id))
        if not linked:
            db.add(EventSource(canonical_event_id=article.canonical_event_id,article_id=article.id,source_id=source.id,article_source_id=exists.id,source_role=exists.source_role,consistency_status=exists.consistency_status,published_at=item.published_at))
            db.flush()
        event=db.get(CanonicalEvent,article.canonical_event_id)
        if event:
            event.source_count=db.scalar(select(func.count(distinct(EventSource.source_id))).where(EventSource.canonical_event_id == event.id)) or 1
            event.official_source_count=db.scalar(select(func.count(distinct(EventSource.source_id))).where(EventSource.canonical_event_id == event.id,EventSource.source_role == "official")) or 0
            event.verification_status="cross_verified" if event.source_count >= 2 and event.official_source_count else ("source_verified" if event.official_source_count else "unverified")
            event.conflict_status="consistent"
    return exists


def _effective_source_type(source: Source, item: SourceItem) -> str:
    return "wechat_manual" if item.raw.get("wechat_link_only") else source.source_type


def _effective_reliability(source: Source, item: SourceItem) -> str:
    return "low" if item.raw.get("wechat_link_only") else source.reliability_level


def _is_first_party(source: Source, item: SourceItem | None = None) -> bool:
    if item and item.raw.get("wechat_link_only"):
        return False
    return source.source_type in {"official","procurement","stock_disclosure","policy","chamber","competitor"}


def _is_cscec_governance_item(source: Source, text: str) -> bool:
    if "cscec" not in (source.source_tags or []):
        return False
    from cscec import classify_leadership_event, classify_org_change
    return bool(classify_leadership_event(text) or classify_org_change(text))


def _promote_primary(article: Article, source: Source, item: SourceItem) -> None:
    if not _is_first_party(source,item) or (article.reliability_level == "high" and article.is_primary_source): return
    article.primary_source_id=source.id; article.source_name=source.source_name; article.source_type=source.source_type
    article.reliability_level="high"; article.original_url=item.url; article.is_primary_source=True
    article.verification_status="source_verified"
    article.sales_insight="已获得高可信来源支撑，建议销售团队核验项目时效并评估产品机会。"


def _create_event_models(db: Session,article: Article,source: Source,item: SourceItem,event_key: str,candidates: list[dict],intelligence_types: list[str],first_party: bool) -> CanonicalEvent:
    project=None
    if set(intelligence_types) & PROJECT_TYPES:
        project_key=canonical_project_fingerprint(article.country,candidates,intelligence_types,item.title)
        project=db.scalar(select(CanonicalProject).where(CanonicalProject.project_key == project_key))
        if not project:
            project=CanonicalProject(project_key=project_key,name=item.title,country=article.country,region=article.region,industries=article.industries,intelligence_types=intelligence_types,project_stage=article.project_stage,project_value=article.project_value,currency=article.currency,first_event_at=item.published_at,last_event_at=item.published_at,event_count=1)
            db.add(project); db.flush()
        else:
            project.event_count += 1
            values=[
                value.replace(tzinfo=utcnow().tzinfo) if value and value.tzinfo is None else value
                for value in (project.last_event_at,item.published_at)
            ]
            project.last_event_at=max(filter(None,values),default=project.last_event_at)
    event=CanonicalEvent(event_key=event_key,canonical_project_id=project.id if project else None,primary_article_id=article.id,title=item.title,project_name=item.title,company_name=candidates[0]["ka_group"] if candidates else None,matched_entities=[x["matched_entity"] for x in candidates],country=article.country,region=article.region,event_type=detect_action_type(item.title+" "+item.excerpt),intelligence_types=intelligence_types,project_value=article.project_value,currency=article.currency,event_date=item.published_at,source_count=1,official_source_count=1 if first_party else 0,verification_status="source_verified" if first_party else "unverified",conflict_status="unknown",confidence_score=article.confidence_score)
    db.add(event); db.flush(); return event


def _add_policy_and_leader(db: Session,article: Article,text: str) -> None:
    dimensions=policy_dimensions(text,article.country,article.intelligence_types,article.industries)
    if dimensions:
        db.add(PolicyIntelligence(article_id=article.id,**dimensions))
    leader=extract_leader_event(text,{
        "intelligence_types":article.intelligence_types,"ka_candidates":article.ka_candidates,
        "country":article.country,"published_at":article.published_at,"summary":article.summary,
        "original_url":article.original_url,"source_name":article.source_name,
    })
    if leader:
        db.add(KALeaderEvent(article_id=article.id,**leader))


def _duplicate(db: Session, article: Article, item: SourceItem, method: str, score: float) -> None:
    if not db.scalar(select(ArticleDuplicate).where(ArticleDuplicate.duplicate_url == item.url)):
        db.add(ArticleDuplicate(canonical_article_id=article.id,duplicate_url=item.url,match_method=method,similarity_score=score))
