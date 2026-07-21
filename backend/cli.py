from __future__ import annotations

import argparse
import getpass
import os
import secrets

from email_validator import EmailNotValidError,validate_email
from sqlalchemy import select

from adapters.registry import build_adapter
from database import SessionLocal
from models import AuditLog,Role,Source,User
from security import hash_password
from source_service import ensure_roles,sync_sources


def _validated_email(value: str) -> str:
    try:
        return validate_email(value,check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise SystemExit(f"invalid administrator email: {exc}") from exc


def _admin_password(args) -> tuple[str,bool]:
    if args.generate_password:
        return secrets.token_urlsafe(32),True
    if args.password_env:
        password=os.getenv(args.password_env,"")
        if not password: raise SystemExit(f"environment variable {args.password_env} is empty or missing")
        return password,False
    password=getpass.getpass("New administrator password: ")
    confirmation=getpass.getpass("Confirm administrator password: ")
    if password != confirmation: raise SystemExit("password confirmation does not match")
    return password,False


def bootstrap_admin(args):
    """Create the first admin once; never embeds or invents a default password."""
    email=_validated_email(args.email)
    password,generated=_admin_password(args)
    if len(password) < 12: raise SystemExit("password must contain at least 12 characters")
    with SessionLocal() as db:
        ensure_roles(db)
        existing_admin=db.scalar(select(User).join(Role,User.role_id == Role.id).where(Role.name == "admin"))
        if existing_admin: raise SystemExit(f"administrator already exists ({existing_admin.email}); no changes made")
        if db.scalar(select(User).where(User.email == email)): raise SystemExit("a non-admin user already uses this email; no changes made")
        role=db.scalar(select(Role).where(Role.name == "admin"))
        user=User(email=email,full_name=args.name,password_hash=hash_password(password),role_id=role.id)
        db.add(user); db.flush()
        db.add(AuditLog(user_id=user.id,action="bootstrap.admin_created",entity_type="user",entity_id=user.id,details={"email":email}))
        db.commit()
    print(f"created first administrator {email}")
    if generated:
        print("ONE-TIME GENERATED PASSWORD (store it now; it will not be shown again):")
        print(password)


def sync(_args):
    with SessionLocal() as db:
        ensure_roles(db)
        print(f"synchronized {sync_sources(db)} sources")


def check_adapters(_args):
    with SessionLocal() as db:
        for source in db.scalars(select(Source).where(Source.adapter_status == "active").order_by(Source.source_name)).all():
            try:
                result=build_adapter(source.source_name,source.source_url,source.adapter_config).health_check()
                print(f"{source.source_name}: {result}")
            except Exception as exc:
                print(f"{source.source_name}: error: {type(exc).__name__}: {exc}")


def add_admin_arguments(command):
    command.add_argument("--email",required=True)
    command.add_argument("--name",default="系统管理员")
    secret=command.add_mutually_exclusive_group()
    secret.add_argument("--generate-password",action="store_true",help="print a strong random password once in the interactive shell")
    secret.add_argument("--password-env",metavar="VARIABLE",help="read the password from a temporary environment variable")
    command.set_defaults(func=bootstrap_admin)


parser=argparse.ArgumentParser(description="Sales intelligence administration")
commands=parser.add_subparsers(required=True)
add_admin_arguments(commands.add_parser("bootstrap-admin",help="create the first administrator exactly once"))
add_admin_arguments(commands.add_parser("create-admin",help="backward-compatible alias for bootstrap-admin"))
sync_cmd=commands.add_parser("sync-sources"); sync_cmd.set_defaults(func=sync)
check=commands.add_parser("check-adapters"); check.set_defaults(func=check_adapters)

if __name__ == "__main__":
    args=parser.parse_args(); args.func(args)
