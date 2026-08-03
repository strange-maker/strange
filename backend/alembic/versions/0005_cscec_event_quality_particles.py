"""Remove legacy CSCEC leadership tokens containing grammatical particles.

Revision ID: 0005_cscec_event_quality_particles
Revises: 0004_cscec_event_quality
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_cscec_event_quality_particles"
down_revision = "0004_cscec_event_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cscec_leadership_events" not in inspector.get_table_names():
        return
    bind.execute(
        sa.text(
            "DELETE FROM cscec_leadership_events "
            "WHERE person_name LIKE :particle"
        ),
        {"particle": "%的%"},
    )


def downgrade() -> None:
    # Deleted parser artifacts are intentionally not recreated.
    pass
