from sqlalchemy import select

import crawl_service
from adapters.base import SourceItem
from api import serialize_article
from crawl_service import execute_crawl
from database import SessionLocal
from ingestion import ingest_item
from models import Article, CrawlJob, Source


def make_source(name: str,source_type: str,reliability: str) -> Source:
    return Source(
        source_name=name,source_url=f"https://{name.lower().replace(' ','-')}.example.com/",
        source_type=source_type,reliability_level=reliability,region_focus=[],country_focus=[],industry_focus=[],
        source_tags=[],crawl_method="html",adapter_status="active",enabled=True,notes="test",
    )


def test_cross_source_count_uses_distinct_sources_and_official_source_is_promoted():
    with SessionLocal() as db:
        media=make_source("Test Media","media","medium"); official=make_source("Test Official","official","high")
        db.add_all([media,official]); db.flush()
        first=SourceItem(title="Saudi Arabia solar EPC project",url="https://media.example.com/a",excerpt="Saudi Arabia solar EPC project tender")
        same_media=SourceItem(title=first.title,url="https://media.example.com/a-copy",excerpt=first.excerpt)
        official_copy=SourceItem(title=first.title,url="https://official.example.com/notice",excerpt=first.excerpt)

        assert ingest_item(db,media,first) == "new"
        article=db.scalar(select(Article).where(Article.title == first.title)); assert article and article.cross_source_count == 1
        assert ingest_item(db,media,same_media) == "duplicate"
        assert article.cross_source_count == 1
        assert ingest_item(db,official,official_copy) == "duplicate"
        assert article.cross_source_count == 2
        assert article.source_name == "Test Official" and article.reliability_level == "high"
        assert article.is_primary_source is True and article.verification_status == "source_verified"


def test_multiple_media_sources_still_require_official_verification():
    with SessionLocal() as db:
        first=make_source("Media One","media","medium"); second=make_source("Media Two","media","medium")
        db.add_all([first,second]); db.flush()
        item=SourceItem(title="Mexico solar EPC project",url="https://one.example.com/a",excerpt="Mexico solar EPC project")
        assert ingest_item(db,first,item) == "new"
        assert ingest_item(db,second,SourceItem(title=item.title,url="https://two.example.com/a",excerpt=item.excerpt)) == "duplicate"
        article=db.scalar(select(Article).where(Article.title == item.title)); assert article and article.cross_source_count == 2
        assert serialize_article(article)["verification_notice"] == "媒体线索，建议核验官方公告"


def test_crawl_service_completes_job_and_inserts_article(monkeypatch):
    class FakeAdapter:
        last_http_status=200
        def fetch_list(self):
            return [SourceItem(title="Saudi Arabia solar EPC project",url="https://example.com/project",excerpt="Saudi Arabia international solar EPC project")]
        def fetch_detail(self,item): return item

    monkeypatch.setattr(crawl_service,"build_adapter",lambda *_args,**_kwargs:FakeAdapter())
    with SessionLocal() as db:
        source=make_source("Runnable Source","media","medium"); source.adapter_key="test"; db.add(source); db.flush()
        job=CrawlJob(source_id=source.id,status="queued"); db.add(job); db.commit()
        run=execute_crawl(db,source,job)
        assert run.status == "success" and run.http_status == 200 and run.fetched_count == 1 and run.new_count == 1
        assert db.get(CrawlJob,job.id).status == "success"
        assert db.scalar(select(Article).where(Article.title == "Saudi Arabia solar EPC project"))


def test_country_specific_source_context_is_valid_overseas_evidence():
    with SessionLocal() as db:
        source=db.scalar(select(Source).where(Source.source_name == "Mexico News Daily")); assert source
        source.industry_focus=["新能源"]
        item=SourceItem(title="Government announces a new solar tender",url="https://example.com/tender",excerpt="The public tender opens next month.")
        assert ingest_item(db,source,item) == "new"
        article=db.scalar(select(Article).where(Article.title == item.title)); assert article
        assert article.country == "墨西哥" and article.region == "拉美"
        assert "Mexico" in article.overseas_evidence or "墨西哥" in article.overseas_evidence
        assert "中压" in article.industries
