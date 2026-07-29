"""Add one-year intelligence, canonical events, backfills and crawl batches.

Revision ID: 0002_year_intelligence
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

from models import Base


revision = "0002_year_intelligence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add_missing_columns(table: str, columns: list[sa.Column]) -> None:
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)

    def create_missing_index(table: str, name: str, columns: list[str]) -> None:
        existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)

    add_missing_columns("ka_aliases", [
        sa.Column("alias_strength", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("entity_relation", sa.String(30), nullable=False, server_default="alias"),
    ])
    create_missing_index("ka_aliases", "ix_ka_aliases_alias_strength", ["alias_strength"])

    add_missing_columns("sources", [
        sa.Column("backfill_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backfill_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backfill_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backfill_page_limit", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("backfill_status", sa.String(30), nullable=False, server_default="not_started"),
        sa.Column("backfill_cursor", sa.String(500), nullable=True),
        sa.Column("last_backfill_at", sa.DateTime(timezone=True), nullable=True),
    ])
    create_missing_index("sources", "ix_sources_backfill_enabled", ["backfill_enabled"])
    create_missing_index("sources", "ix_sources_backfill_status", ["backfill_status"])

    add_missing_columns("articles", [
        sa.Column("intelligence_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("matched_entities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ka_candidates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("date_verification_status", sa.String(30), nullable=False, server_default="verified"),
        sa.Column("canonical_event_id", sa.String(36), nullable=True),
    ])
    create_missing_index("articles", "ix_articles_date_verification_status", ["date_verification_status"])
    create_missing_index("articles", "ix_articles_canonical_event_id", ["canonical_event_id"])

    add_missing_columns("article_sources", [
        sa.Column("source_role", sa.String(30), nullable=False, server_default="supplemental"),
        sa.Column("consistency_status", sa.String(30), nullable=False, server_default="unknown"),
    ])
    create_missing_index("article_sources", "ix_article_sources_source_role", ["source_role"])

    # New tables are defined in SQLAlchemy models and created without touching
    # existing tables or rows. Alembic still records this revision exactly once.
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    for table in [
        "backfill_checkpoints", "backfill_runs", "source_capability_checks",
        "crawl_batch_items", "crawl_batches", "ka_leader_events",
        "ka_entity_relations", "ka_entities", "policy_intelligence",
        "event_sources", "canonical_events", "canonical_projects",
    ]:
        op.drop_table(table)

    op.drop_index("ix_article_sources_source_role", table_name="article_sources")
    op.drop_column("article_sources", "consistency_status")
    op.drop_column("article_sources", "source_role")
    op.drop_index("ix_articles_canonical_event_id", table_name="articles")
    op.drop_index("ix_articles_date_verification_status", table_name="articles")
    op.drop_column("articles", "canonical_event_id")
    op.drop_column("articles", "date_verification_status")
    op.drop_column("articles", "ka_candidates")
    op.drop_column("articles", "matched_entities")
    op.drop_column("articles", "intelligence_types")
    op.drop_index("ix_sources_backfill_status", table_name="sources")
    op.drop_index("ix_sources_backfill_enabled", table_name="sources")
    op.drop_column("sources", "last_backfill_at")
    op.drop_column("sources", "backfill_cursor")
    op.drop_column("sources", "backfill_status")
    op.drop_column("sources", "backfill_page_limit")
    op.drop_column("sources", "backfill_end_date")
    op.drop_column("sources", "backfill_start_date")
    op.drop_column("sources", "backfill_enabled")
    op.drop_index("ix_ka_aliases_alias_strength", table_name="ka_aliases")
    op.drop_column("ka_aliases", "entity_relation")
    op.drop_column("ka_aliases", "alias_strength")
