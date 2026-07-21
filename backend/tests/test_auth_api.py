from sqlalchemy import select

from database import SessionLocal
from models import AuditLog, Role, User
from security import hash_password


def test_login_refresh_and_me(client):
    login=client.post("/api/auth/login",json={"email":"admin@example.com","password":"A-secure-test-password!"})
    assert login.status_code == 200
    tokens=login.json(); assert tokens["user"]["role"] == "admin"
    me=client.get("/api/auth/me",headers={"Authorization":f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "admin@example.com"
    refreshed=client.post("/api/auth/refresh",json={"refresh_token":tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/api/auth/refresh",json={"refresh_token":tokens["refresh_token"]}).status_code == 401


def test_role_checks_and_login_lock(client):
    with SessionLocal() as db:
        role=db.scalar(select(Role).where(Role.name == "viewer")); db.add(User(email="viewer@example.com",full_name="只读用户",password_hash=hash_password("Viewer-test-password!"),role_id=role.id)); db.commit()
    token=client.post("/api/auth/login",json={"email":"viewer@example.com","password":"Viewer-test-password!"}).json()["access_token"]
    assert client.get("/api/sources",headers={"Authorization":f"Bearer {token}"}).status_code == 200
    source=client.get("/api/sources",headers={"Authorization":f"Bearer {token}"}).json()[0]
    assert client.patch(f"/api/sources/{source['id']}",headers={"Authorization":f"Bearer {token}"},json={"enabled":False}).status_code == 403
    for _ in range(5): client.post("/api/auth/login",json={"email":"viewer@example.com","password":"wrong"})
    assert client.post("/api/auth/login",json={"email":"viewer@example.com","password":"Viewer-test-password!"}).status_code == 429
    with SessionLocal() as db: assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_failed")) is not None
