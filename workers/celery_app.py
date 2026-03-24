from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "eximpe_payments",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.payment_worker", "workers.reconciliation_worker", "workers.fx_worker"],
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
        "refresh-fx-rates": {
            "task": "workers.fx_worker.refresh_fx_rates",
            "schedule": 60.0,  # every 60 seconds
        },
        "reconcile-settlements": {
            "task": "workers.reconciliation_worker.reconcile_settlements",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)
