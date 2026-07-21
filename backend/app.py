"""Compatibility entrypoint: `python app.py` or `uvicorn app:app`."""
from api import app

if __name__ == "__main__":
    import uvicorn
    from config import get_settings
    settings=get_settings()
    uvicorn.run("api:app",host="0.0.0.0",port=settings.port,reload=not settings.production,proxy_headers=True,forwarded_allow_ips=settings.forwarded_allow_ips)
