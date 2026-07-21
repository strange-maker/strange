from __future__ import annotations

from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.base import SourceItem, canonicalize_url, content_digest
from models import Article, ArticleDuplicate, ArticleSource, Source, utcnow
from rules import detect_ka, detect_overseas, product_opportunities, rule_summary


def ingest_item(db: Session, source: Source, item: SourceItem, is_manual: bool = False) -> str:
    canonical=canonicalize_url(item.url)
    existing=db.scalar(select(Article).where(Article.canonical_url == canonical))
    if existing:
        existing.last_seen_at=utcnow(); existing.cross_source_count=max(existing.cross_source_count, 1)
        _attach_source(db, existing, source, item)
        return "updated"

    digest=content_digest(item.title,item.excerpt)
    exact=db.scalar(select(Article).where(Article.content_hash == digest))
    if exact:
        _duplicate(db,exact,item,"content_hash",1.0); _attach_source(db,exact,source,item)
        exact.cross_source_count += 1
        if source.reliability_level == "high" and exact.reliability_level != "high":
            exact.primary_source_id=source.id; exact.source_name=source.source_name; exact.source_type=source.source_type; exact.reliability_level="high"; exact.original_url=item.url; exact.is_primary_source=True
        return "duplicate"

    recent=db.scalars(select(Article).where(Article.published_at >= (item.published_at or utcnow()) - timedelta(days=7)).limit(100)).all()
    for candidate in recent:
        similarity=SequenceMatcher(None,candidate.title.lower(),item.title.lower()).ratio()
        if similarity >= .92:
            _duplicate(db,candidate,item,"title_similarity",similarity); _attach_source(db,candidate,source,item); candidate.cross_source_count += 1
            return "duplicate"

    text=f"{item.title}\n{item.excerpt}"; overseas=detect_overseas(item.title,item.excerpt)
    if not overseas["is_overseas"]:
        if not is_manual: return "skipped"
        overseas={"is_overseas":True,"country":None,"region":None,"overseas_confidence":.2,"overseas_evidence":["用户手动导入，海外属性待人工核验"]}
    kas,matched,ka_conf=detect_ka(item.title,item.excerpt,source.source_name)
    products=product_opportunities(None,text)
    first_party=source.source_type in {"official","procurement","stock_disclosure","policy","chamber"}
    article=Article(
        title=item.title, original_title=item.title, summary=rule_summary(item.excerpt or item.title),
        sales_insight="待销售团队基于已核验事实评估产品机会。" if first_party else "媒体线索，建议核验官方公告。",
        original_url=item.url, canonical_url=canonical, primary_source_id=source.id, source_name=source.source_name,
        source_type=source.source_type, reliability_level=source.reliability_level, author=item.author,
        published_at=item.published_at, content_excerpt=item.excerpt[:6000], content_hash=digest, language=item.language,
        country=overseas["country"], region=overseas["region"], ka=kas, subsidiary=[], industries=products,
        overseas_evidence=overseas["overseas_evidence"], ka_match_evidence=matched,
        confidence_score=min(.98,max(overseas["overseas_confidence"],ka_conf)),
        verification_status="source_verified" if first_party else "unverified", is_primary_source=first_party,
        review_status="pending", is_overseas=True, is_demo=False,
        ai_payload={"factual_summary":rule_summary(item.excerpt or item.title),"why_it_matters":"","project_stage":None,"related_ka":kas,"subsidiary":[],"country":overseas["country"],"region":overseas["region"],"opportunity_type":None,"schneider_product_opportunities":products,"recommended_sales_action":"核验项目状态并联系相关账户","evidence":overseas["overseas_evidence"],"uncertainty":["尚未经过人工审核"],"confidence":min(.98,max(overseas["overseas_confidence"],ka_conf))},
        ai_model="rules", ai_prompt_version="rules-v1", ai_generated_at=utcnow(), ai_result_version=1,
    )
    db.add(article); db.flush(); _attach_source(db,article,source,item,first_party); return "new"


def _attach_source(db: Session, article: Article, source: Source, item: SourceItem, is_primary: bool=False) -> None:
    exists=db.scalar(select(ArticleSource).where(ArticleSource.article_id == article.id,ArticleSource.original_url == item.url))
    if not exists: db.add(ArticleSource(article_id=article.id,source_id=source.id,original_url=item.url,title=item.title,published_at=item.published_at,reliability_level=source.reliability_level,is_primary=is_primary))


def _duplicate(db: Session, article: Article, item: SourceItem, method: str, score: float) -> None:
    if not db.scalar(select(ArticleDuplicate).where(ArticleDuplicate.duplicate_url == item.url)):
        db.add(ArticleDuplicate(canonical_article_id=article.id,duplicate_url=item.url,match_method=method,similarity_score=score))
