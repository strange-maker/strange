from celery import Celery
from celery.schedules import crontab

from config import get_settings

settings=get_settings()
celery=Celery("sales_intelligence",broker=settings.redis_url,backend=settings.redis_url,include=["tasks"])
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout":3600,"health_check_interval":30},
    result_backend_transport_options={"health_check_interval":30},
    enable_utc=True,
    timezone="UTC",
)
celery.conf.beat_schedule={"dispatch-due-sources-every-minute":{"task":"tasks.dispatch_due_sources","schedule":crontab(minute="*")}}
