import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_revision_ids_fit_version_table():
    """PostgreSQL's default alembic_version.version_num is VARCHAR(32)."""
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert revisions
    assert all(len(item.revision) <= 32 for item in revisions)


def test_alembic_upgrade_from_empty_database(tmp_path):
    backend=Path(__file__).resolve().parents[1]; database=tmp_path/"migration.db"; env=os.environ.copy(); env["DATABASE_URL"]=f"sqlite:///{database.as_posix()}"
    result=subprocess.run([sys.executable,"-m","alembic","-c","alembic.ini","upgrade","head"],cwd=backend,env=env,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as db:
        db.execute("insert into roles (name, description) values ('sentinel', 'must survive restart')")
        db.commit()
    second=subprocess.run([sys.executable,"-m","alembic","-c","alembic.ini","upgrade","head"],cwd=backend,env=env,capture_output=True,text=True)
    assert second.returncode == 0, second.stderr
    with sqlite3.connect(database) as db:
        tables={x[0] for x in db.execute("select name from sqlite_master where type='table'")}
        assert db.execute("select count(*) from roles where name='sentinel'").fetchone()[0] == 1
        source_columns={x[1] for x in db.execute("pragma table_info(sources)")}
        article_columns={x[1] for x in db.execute("pragma table_info(articles)")}
    assert {
        "users","articles","sources","crawl_runs","audit_logs","canonical_events",
        "canonical_projects","crawl_batches","backfill_runs","source_capability_checks",
        "cscec_entities","page_snapshots","page_diffs","cscec_leadership_events","cscec_org_events",
    }.issubset(tables)
    assert {"backfill_enabled","backfill_status","backfill_cursor","entity_id"}.issubset(source_columns)
    assert {"intelligence_types","ka_candidates","canonical_event_id","date_verification_status"}.issubset(article_columns)


def test_compatibility_migration_preserves_legacy_rows(tmp_path):
    backend=Path(__file__).resolve().parents[1]
    database=tmp_path/"legacy.db"
    with sqlite3.connect(database) as db:
        db.executescript("""
            create table roles (id integer primary key, name varchar(30), description varchar(200));
            insert into roles (id,name,description) values (1,'sentinel','must survive upgrade');
            create table ka_aliases (id integer primary key);
            create table sources (id varchar(36) primary key);
            create table articles (id varchar(36) primary key);
            create table article_sources (id varchar(36) primary key);
        """)
    env=os.environ.copy(); env["DATABASE_URL"]=f"sqlite:///{database.as_posix()}"
    stamp=subprocess.run([sys.executable,"-m","alembic","-c","alembic.ini","stamp","0001_initial"],cwd=backend,env=env,capture_output=True,text=True)
    assert stamp.returncode == 0, stamp.stderr
    upgrade=subprocess.run([sys.executable,"-m","alembic","-c","alembic.ini","upgrade","head"],cwd=backend,env=env,capture_output=True,text=True)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("select description from roles where name='sentinel'").fetchone()[0] == "must survive upgrade"
        assert {"backfill_enabled","backfill_status"}.issubset({x[1] for x in db.execute("pragma table_info(sources)")})
        assert {"intelligence_types","canonical_event_id"}.issubset({x[1] for x in db.execute("pragma table_info(articles)")})


def test_sales_intelligence_migration_creates_batch_and_fields(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "sales-intelligence.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(database) as db:
        tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
        article_columns = {row[1] for row in db.execute("pragma table_info(articles)")}
        leadership_columns = {
            row[1] for row in db.execute("pragma table_info(cscec_leadership_events)")
        }
        org_columns = {row[1] for row in db.execute("pragma table_info(cscec_org_events)")}

    assert "manual_import_batches" in tables
    assert {
        "display_title",
        "manual_import_batch_id",
        "external_parties",
        "event_types",
        "involved_leaders",
        "involved_departments",
        "industry_tags",
        "product_opportunity_tags",
        "sales_relevance_score",
        "sales_score_evidence",
        "sales_signal",
        "sales_opportunity",
        "recommended_contact",
        "recommended_action",
        "exclusion_reason",
        "evidence_excerpt",
        "topic_tags",
    } <= article_columns
    assert {
        "event_category",
        "activity_type",
        "external_party",
        "country",
        "project_or_business",
        "sales_impact",
        "recommended_action",
    } <= leadership_columns
    assert {
        "region_or_industry",
        "sales_impact",
        "recommended_contact",
        "manual_confirmed",
        "display_title",
    } <= org_columns
