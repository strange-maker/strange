"""Development-only schema initializer. Production must run Alembic."""
from database import SessionLocal,engine
from models import Base
from source_service import ensure_roles,sync_sources

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_roles(db); print(f"Synchronized {sync_sources(db)} source definitions; no demo articles loaded.")
