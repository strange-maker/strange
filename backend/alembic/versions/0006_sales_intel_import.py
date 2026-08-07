"""Add manual import audit and structured sales-intelligence fields.

Revision ID: 0006_sales_intel_import
Revises: 0005_cscec_particles
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_sales_intel_import"
down_revision = "0005_cscec_particles"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _add_index(table: str, name: str, columns: list[str]) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=False)


def upgrade() -> None:
    if "manual_import_batches" not in _tables():
        op.create_table(
            "manual_import_batches",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "requested_by",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("source_name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="processing"),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("missing_body_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    _add_index(
        "manual_import_batches",
        "ix_manual_import_batches_requested_by",
        ["requested_by"],
    )
    _add_index(
        "manual_import_batches",
        "ix_manual_import_batches_file_sha256",
        ["file_sha256"],
    )
    _add_index("manual_import_batches", "ix_manual_import_batches_status", ["status"])

    article_columns = (
        sa.Column("display_title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("manual_import_batch_id", sa.String(length=36), nullable=True),
        sa.Column("external_parties", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("involved_leaders", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("involved_departments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("industry_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("product_opportunity_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("topic_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sales_relevance_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_score_evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sales_signal", sa.Text(), nullable=False, server_default=""),
        sa.Column("sales_opportunity", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_contact", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False, server_default=""),
    )
    for column in article_columns:
        _add_column("articles", column)
    _add_index("articles", "ix_articles_display_title", ["display_title"])
    _add_index("articles", "ix_articles_manual_import_batch_id", ["manual_import_batch_id"])
    _add_index("articles", "ix_articles_sales_relevance_score", ["sales_relevance_score"])
    if op.get_bind().dialect.name == "postgresql":
        foreign_keys = {
            item.get("name")
            for item in sa.inspect(op.get_bind()).get_foreign_keys("articles")
        }
        constraint_name = "fk_articles_manual_import_batch_id"
        if constraint_name not in foreign_keys:
            op.create_foreign_key(
                constraint_name,
                "articles",
                "manual_import_batches",
                ["manual_import_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )

    leadership_columns = (
        sa.Column("event_category", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("activity_type", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("external_party", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("project_or_business", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("sales_impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""),
    )
    for column in leadership_columns:
        _add_column("cscec_leadership_events", column)
    _add_index(
        "cscec_leadership_events",
        "ix_cscec_leadership_events_event_category",
        ["event_category"],
    )
    _add_index(
        "cscec_leadership_events",
        "ix_cscec_leadership_events_activity_type",
        ["activity_type"],
    )
    _add_index(
        "cscec_leadership_events",
        "ix_cscec_leadership_events_country",
        ["country"],
    )

    org_columns = (
        sa.Column("display_title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("region_or_industry", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("sales_impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_contact", sa.Text(), nullable=False, server_default=""),
        sa.Column("manual_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for column in org_columns:
        _add_column("cscec_org_events", column)
    _add_index(
        "cscec_org_events",
        "ix_cscec_org_events_manual_confirmed",
        ["manual_confirmed"],
    )


def downgrade() -> None:
    # The application does not automatically destroy imported intelligence.
    # Explicit rollback is intentionally conservative and only removes the
    # additive schema when an operator invokes downgrade.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and "articles" in _tables():
        foreign_keys = {
            item.get("name") for item in sa.inspect(bind).get_foreign_keys("articles")
        }
        if "fk_articles_manual_import_batch_id" in foreign_keys:
            op.drop_constraint(
                "fk_articles_manual_import_batch_id", "articles", type_="foreignkey"
            )

    for table, columns in (
        (
            "cscec_org_events",
            [
                "manual_confirmed",
                "recommended_contact",
                "sales_impact",
                "region_or_industry",
                "display_title",
            ],
        ),
        (
            "cscec_leadership_events",
            [
                "recommended_action",
                "sales_impact",
                "project_or_business",
                "country",
                "external_party",
                "activity_type",
                "event_category",
            ],
        ),
        (
            "articles",
            [
                "evidence_excerpt",
                "exclusion_reason",
                "recommended_action",
                "recommended_contact",
                "sales_opportunity",
                "sales_signal",
                "sales_score_evidence",
                "sales_relevance_score",
                "topic_tags",
                "product_opportunity_tags",
                "industry_tags",
                "involved_departments",
                "involved_leaders",
                "event_types",
                "external_parties",
                "manual_import_batch_id",
                "display_title",
            ],
        ),
    ):
        for column in columns:
            if column in _columns(table):
                op.drop_column(table, column)
    if "manual_import_batches" in _tables():
        op.drop_table("manual_import_batches")

