from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "cross_border_payments",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Runs daily at 18:30 UTC = 00:00 IST
        "daily-reconciliation": {
            "task": "workers.tasks.daily_reconciliation_job",
            "schedule": crontab(hour=18, minute=30),
        },
    },
)
