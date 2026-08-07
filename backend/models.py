from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(500))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    role: Mapped[Role] = relationship()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class Country(Base):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    iso_code: Mapped[str | None] = mapped_column(String(3), nullable=True, unique=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    company_type: Mapped[str] = mapped_column(String(50), default="unknown")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True)


class KAGroup(Base):
    __tablename__ = "ka_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    ka_type: Mapped[str] = mapped_column(String(50), default="EPC KA")


class KAAlias(Base):
    __tablename__ = "ka_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ka_group_id: Mapped[str] = mapped_column(ForeignKey("ka_groups.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(200), index=True)
    is_ambiguous: Mapped[bool] = mapped_column(Boolean, default=False)
    alias_strength: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    entity_relation: Mapped[str] = mapped_column(String(30), default="alias")
    __table_args__ = (UniqueConstraint("ka_group_id", "alias"),)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1200))
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    reliability_level: Mapped[str] = mapped_column(String(20), index=True)
    region_focus: Mapped[list] = mapped_column(JSON, default=list)
    country_focus: Mapped[list] = mapped_column(JSON, default=list)
    industry_focus: Mapped[list] = mapped_column(JSON, default=list)
    source_tags: Mapped[list] = mapped_column(JSON, default=list)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    crawl_method: Mapped[str] = mapped_column(String(30))
    adapter_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adapter_status: Mapped[str] = mapped_column(String(30), default="pending_adapter", index=True)
    adapter_config: Mapped[dict] = mapped_column(JSON, default=dict)
    schedule_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    backfill_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    backfill_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backfill_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backfill_page_limit: Mapped[int] = mapped_column(Integer, default=25)
    backfill_status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    backfill_cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_backfill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(30), default="schedule")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    crawl_job_id: Mapped[str | None] = mapped_column(ForeignKey("crawl_jobs.id"), nullable=True, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrawlError(Base):
    __tablename__ = "crawl_errors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    crawl_run_id: Mapped[str] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True)
    error_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManualImportBatch(Base):
    __tablename__ = "manual_import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    requested_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_body_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(500), index=True)
    display_title: Mapped[str] = mapped_column(String(500), default="", index=True)
    original_title: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    sales_insight: Mapped[str] = mapped_column(Text, default="")
    original_url: Mapped[str] = mapped_column(String(1600), index=True)
    canonical_url: Mapped[str] = mapped_column(String(1600), unique=True, index=True)
    primary_source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    manual_import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("manual_import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    reliability_level: Mapped[str] = mapped_column(String(20), index=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_excerpt: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(20), default="unknown")
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ka: Mapped[list] = mapped_column(JSON, default=list)
    subsidiary: Mapped[list] = mapped_column(JSON, default=list)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    intelligence_types: Mapped[list] = mapped_column(JSON, default=list)
    matched_entities: Mapped[list] = mapped_column(JSON, default=list)
    external_parties: Mapped[list] = mapped_column(JSON, default=list)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    involved_leaders: Mapped[list] = mapped_column(JSON, default=list)
    involved_departments: Mapped[list] = mapped_column(JSON, default=list)
    industry_tags: Mapped[list] = mapped_column(JSON, default=list)
    product_opportunity_tags: Mapped[list] = mapped_column(JSON, default=list)
    topic_tags: Mapped[list] = mapped_column(JSON, default=list)
    ka_candidates: Mapped[list] = mapped_column(JSON, default=list)
    date_verification_status: Mapped[str] = mapped_column(String(30), default="verified", index=True)
    canonical_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    project_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    project_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    overseas_evidence: Mapped[list] = mapped_column(JSON, default=list)
    ka_match_evidence: Mapped[list] = mapped_column(JSON, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    sales_relevance_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    sales_score_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    sales_signal: Mapped[str] = mapped_column(Text, default="")
    sales_opportunity: Mapped[str] = mapped_column(Text, default="")
    recommended_contact: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified", index=True)
    cross_source_count: Mapped[int] = mapped_column(Integer, default=1)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    is_overseas: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ai_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_result_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_articles_country_region", "country", "region"),)


class ArticleSource(Base):
    __tablename__ = "article_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    original_url: Mapped[str] = mapped_column(String(1600))
    title: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reliability_level: Mapped[str] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source_role: Mapped[str] = mapped_column(String(30), default="supplemental", index=True)
    consistency_status: Mapped[str] = mapped_column(String(30), default="unknown")
    __table_args__ = (UniqueConstraint("article_id", "original_url"),)


class ArticleDuplicate(Base):
    __tablename__ = "article_duplicates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canonical_article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    duplicate_url: Mapped[str] = mapped_column(String(1600), unique=True)
    match_method: Mapped[str] = mapped_column(String(50))
    similarity_score: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArticleTag(Base):
    __tablename__ = "article_tags"
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)


class ArticleCompanyMatch(Base):
    __tablename__ = "article_company_matches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    company_name: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class ArticleLocationMatch(Base):
    __tablename__ = "article_location_matches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserReadStatus(Base):
    __tablename__ = "user_read_status"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReviewRecord(Base):
    __tablename__ = "review_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
    before_data: Mapped[dict] = mapped_column(JSON, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CanonicalProject(Base):
    __tablename__ = "canonical_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    intelligence_types: Mapped[list] = mapped_column(JSON, default=list)
    project_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    project_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    first_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CanonicalEvent(Base):
    __tablename__ = "canonical_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_project_id: Mapped[str | None] = mapped_column(ForeignKey("canonical_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    primary_article_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    project_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    matched_entities: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(300), nullable=True)
    epc: Mapped[str | None] = mapped_column(String(300), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    intelligence_types: Mapped[list] = mapped_column(JSON, default=list)
    project_value: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    official_source_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified", index=True)
    conflict_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canonical_event_id: Mapped[str] = mapped_column(ForeignKey("canonical_events.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    article_source_id: Mapped[str | None] = mapped_column(ForeignKey("article_sources.id", ondelete="SET NULL"), nullable=True)
    source_role: Mapped[str] = mapped_column(String(30), default="supplemental", index=True)
    consistency_status: Mapped[str] = mapped_column(String(30), default="unknown")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("canonical_event_id", "source_id", "article_id"),)


class PolicyIntelligence(Base):
    __tablename__ = "policy_intelligence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), unique=True, index=True)
    publishing_country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    affected_countries: Mapped[list] = mapped_column(JSON, default=list)
    issuing_body: Mapped[str | None] = mapped_column(String(300), nullable=True)
    policy_types: Mapped[list] = mapped_column(JSON, default=list)
    applicable_industries: Mapped[list] = mapped_column(JSON, default=list)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tax_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_rate_change: Mapped[str | None] = mapped_column(String(200), nullable=True)
    investment_threshold: Mapped[str | None] = mapped_column(String(300), nullable=True)
    foreign_ownership_ratio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    localization_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_procurement_ratio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    incentives: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_tariff: Mapped[str | None] = mapped_column(String(200), nullable=True)
    export_controls: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_standards: Mapped[str | None] = mapped_column(Text, nullable=True)
    certification_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    china_company_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    schneider_sales_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KAEntity(Base):
    __tablename__ = "ka_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    ka_group_id: Mapped[str] = mapped_column(ForeignKey("ka_groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    entity_relation: Mapped[str] = mapped_column(String(30), default="business_mapping", index=True)
    is_verified_relation: Mapped[bool] = mapped_column(Boolean, default=False)
    official_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("ka_group_id", "name"),)


class KAEntityRelation(Base):
    __tablename__ = "ka_entity_relations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    ka_group_id: Mapped[str] = mapped_column(ForeignKey("ka_groups.id", ondelete="CASCADE"), index=True)
    ka_entity_id: Mapped[str] = mapped_column(ForeignKey("ka_entities.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="business_mapping", index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KALeaderEvent(Base):
    __tablename__ = "ka_leader_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    person_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    person_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ka_group: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    matched_entity: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    action_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    meeting_party: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    factual_summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1600))
    source_name: Mapped[str] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")


class CrawlBatch(Base):
    __tablename__ = "crawl_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    singleton_key: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    total_sources: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    empty_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CrawlBatchItem(Base):
    __tablename__ = "crawl_batch_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("crawl_batches.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    crawl_job_id: Mapped[str | None] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    skip_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("batch_id", "source_id"),)


class SourceCapabilityCheck(Base):
    __tablename__ = "source_capability_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    test_method: Mapped[str] = mapped_column(String(100))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawlable: Mapped[bool] = mapped_column(Boolean, default=False)
    one_year_backfill: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_fields: Mapped[list] = mapped_column(JSON, default=list)
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_limits: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class BackfillRun(Base):
    __tablename__ = "backfill_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    page_limit: Mapped[int] = mapped_column(Integer, default=25)
    current_page: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    date_unverified_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BackfillCheckpoint(Base):
    __tablename__ = "backfill_checkpoints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    backfill_run_id: Mapped[str] = mapped_column(ForeignKey("backfill_runs.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oldest_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("backfill_run_id", "page_number"),)


class CSCECEntity(Base):
    __tablename__ = "cscec_entities"
    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    short_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    parent_entity_id: Mapped[str | None] = mapped_column(ForeignKey("cscec_entities.entity_id", ondelete="SET NULL"), nullable=True, index=True)
    entity_level: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    stock_code: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    official_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="中国", index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    overseas: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(40), default="pending_verification", index=True)
    verification_source: Mapped[str | None] = mapped_column(String(1600), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("cscec_entities.entity_id", ondelete="SET NULL"), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True)
    page_type: Mapped[str] = mapped_column(String(60), index=True)
    page_url: Mapped[str] = mapped_column(String(1600), index=True)
    raw_html: Mapped[str] = mapped_column(Text)
    cleaned_text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (Index("ix_page_snapshots_url_captured", "page_url", "captured_at"),)


class PageDiff(Base):
    __tablename__ = "page_diffs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("cscec_entities.entity_id", ondelete="SET NULL"), nullable=True, index=True)
    page_type: Mapped[str] = mapped_column(String(60), index=True)
    page_url: Mapped[str] = mapped_column(String(1600))
    before_snapshot_id: Mapped[str] = mapped_column(ForeignKey("page_snapshots.id", ondelete="CASCADE"), index=True)
    after_snapshot_id: Mapped[str] = mapped_column(ForeignKey("page_snapshots.id", ondelete="CASCADE"), index=True)
    before_text: Mapped[str] = mapped_column(Text)
    after_text: Mapped[str] = mapped_column(Text)
    diff_text: Mapped[str] = mapped_column(Text)
    detected_changes: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(40), default="pending_review", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CSCECLeadershipEvent(Base):
    __tablename__ = "cscec_leadership_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    article_id: Mapped[str | None] = mapped_column(ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)
    person_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("cscec_entities.entity_id", ondelete="SET NULL"), nullable=True, index=True)
    parent_entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    title_before: Mapped[str | None] = mapped_column(String(300), nullable=True)
    title_after: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    appointment_type: Mapped[str] = mapped_column(String(50), index=True)
    event_category: Mapped[str] = mapped_column(String(60), default="", index=True)
    activity_type: Mapped[str] = mapped_column(String(60), default="", index=True)
    external_party: Mapped[str] = mapped_column(String(300), default="")
    country: Mapped[str] = mapped_column(String(100), default="", index=True)
    project_or_business: Mapped[str] = mapped_column(String(500), default="")
    sales_impact: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1600))
    source_name: Mapped[str] = mapped_column(String(300))
    evidence_excerpt: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(40), default="pending_review", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CSCECOrgEvent(Base):
    __tablename__ = "cscec_org_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    article_id: Mapped[str | None] = mapped_column(ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_before: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entity_after: Mapped[str | None] = mapped_column(String(300), nullable=True)
    parent_before: Mapped[str | None] = mapped_column(String(300), nullable=True)
    parent_after: Mapped[str | None] = mapped_column(String(300), nullable=True)
    relation_before: Mapped[str | None] = mapped_column(String(100), nullable=True)
    relation_after: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_title: Mapped[str] = mapped_column(String(500), default="")
    region_or_industry: Mapped[str] = mapped_column(String(300), default="")
    sales_impact: Mapped[str] = mapped_column(Text, default="")
    recommended_contact: Mapped[str] = mapped_column(Text, default="")
    manual_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    diff_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("page_diffs.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(40), default="pending_review", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
