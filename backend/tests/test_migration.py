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
    assert {"users","articles","sources","crawl_runs","audit_logs"}.issubset(tables)
