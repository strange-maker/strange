"""Initial production schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op

from models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_articles_search_fts ON articles USING gin (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(content_excerpt,'')))")
        op.execute("CREATE INDEX IF NOT EXISTS ix_articles_title_trgm ON articles USING gin (title gin_trgm_ops)")


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
