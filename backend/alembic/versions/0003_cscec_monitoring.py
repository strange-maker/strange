"""Add CSCEC organization and leadership monitoring tables.

Revision ID: 0003_cscec_monitoring
Revises: 0002_year_intelligence
"""

from alembic import op
import sqlalchemy as sa

from models import Base


revision = "0003_cscec_monitoring"
down_revision = "0002_year_intelligence"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "entity_id" not in _column_names(inspector, "sources"):
        with op.batch_alter_table("sources") as batch:
            batch.add_column(sa.Column("entity_id", sa.String(length=100), nullable=True))
            batch.create_index("ix_sources_entity_id", ["entity_id"], unique=False)
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in (
        "cscec_org_events",
        "cscec_leadership_events",
        "page_diffs",
        "page_snapshots",
        "cscec_entities",
    ):
        if table in tables:
            op.drop_table(table)

    inspector = sa.inspect(bind)
    if "entity_id" in _column_names(inspector, "sources"):
        indexes = {item["name"] for item in inspector.get_indexes("sources")}
        with op.batch_alter_table("sources") as batch:
            if "ix_sources_entity_id" in indexes:
                batch.drop_index("ix_sources_entity_id")
            batch.drop_column("entity_id")
