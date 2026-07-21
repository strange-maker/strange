import os
from pathlib import Path

TEST_DB=Path(__file__).with_name("test_runtime.db")
os.environ["ENVIRONMENT"]="test"
os.environ["DATABASE_URL"]=f"sqlite:///{TEST_DB.as_posix()}"
os.environ["JWT_SECRET"]="test-secret-with-more-than-thirty-two-characters"
os.environ["REDIS_URL"]="redis://localhost:6399/15"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api import app
from database import SessionLocal, engine
from models import Base, Role, User
from security import hash_password
from source_service import ensure_roles, sync_sources


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_roles(db); sync_sources(db)
        role=db.scalar(select(Role).where(Role.name == "admin"))
        db.add(User(email="admin@example.com",full_name="测试管理员",password_hash=hash_password("A-secure-test-password!"),role_id=role.id)); db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app) as value: yield value


@pytest.fixture
def admin_headers(client):
    payload=client.post("/api/auth/login",json={"email":"admin@example.com","password":"A-secure-test-password!"}).json()
    return {"Authorization":f"Bearer {payload['access_token']}"}
