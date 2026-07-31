import os
import sqlite3
import subprocess
import sys
from pathlib import Path


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
