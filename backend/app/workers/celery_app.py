"""
Celery application setup for BI-Platform.

Configuration
-------------
* Broker  : Redis (CELERY_BROKER_URL from settings)
* Backend : Redis (CELERY_RESULT_BACKEND from settings)
* Queues  : discovery-queue, audit-queue, export-queue
* Beat    : periodic health-check and cleanup tasks

Usage::

    # Start worker consuming all queues
    celery -A app.workers.celery_app worker --loglevel=info -Q discovery-queue,audit-queue,export-queue

    # Start beat scheduler
    celery -A app.workers.celery_app beat --loglevel=info
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.core.config import settings

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

celery_app = Celery(
    "bi_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.discovery_worker",
        "app.workers.audit_worker",
        "app.workers.export_worker",
    ],
)

# ---------------------------------------------------------------------------
# Serialisation / content
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    # Result expiry: keep results for 24 hours
    result_expires=86_400,
    # Prevent tasks from running longer than 10 minutes by default
    task_soft_time_limit=540,
    task_time_limit=600,
    # Acknowledge tasks only after they complete (safer for idempotent tasks)
    task_acks_late=True,
    # Prefetch one task at a time per worker process
    worker_prefetch_multiplier=1,
    # Store full result (not just OK/FAIL)
    task_track_started=True,
    # Re-raise exceptions so the task is marked FAILURE on error
    task_always_eager=False,
    # Retry: default exponential back-off; individual tasks override this
    task_default_retry_delay=60,
    task_max_retries=3,
)

# ---------------------------------------------------------------------------
# Queue routing
# ---------------------------------------------------------------------------

_default_exchange = Exchange("default", type="direct")
_discovery_exchange = Exchange("discovery", type="direct")
_audit_exchange = Exchange("audit", type="direct")
_export_exchange = Exchange("export", type="direct")

celery_app.conf.task_queues = (
    Queue("default", _default_exchange, routing_key="default"),
    Queue("discovery-queue", _discovery_exchange, routing_key="discovery"),
    Queue("audit-queue", _audit_exchange, routing_key="audit"),
    Queue("export-queue", _export_exchange, routing_key="export"),
)

celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

celery_app.conf.task_routes = {
    # Discovery tasks
    "app.workers.discovery_worker.run_discovery_job": {
        "queue": "discovery-queue",
        "routing_key": "discovery",
    },
    "app.workers.discovery_worker.process_discovery_result": {
        "queue": "discovery-queue",
        "routing_key": "discovery",
    },
    # Audit tasks
    "app.workers.audit_worker.run_audit_job": {
        "queue": "audit-queue",
        "routing_key": "audit",
    },
    "app.workers.audit_worker.run_bulk_audit": {
        "queue": "audit-queue",
        "routing_key": "audit",
    },
    # Export tasks
    "app.workers.export_worker.export_to_csv": {
        "queue": "export-queue",
        "routing_key": "export",
    },
    "app.workers.export_worker.export_to_excel": {
        "queue": "export-queue",
        "routing_key": "export",
    },
    "app.workers.export_worker.export_to_pdf": {
        "queue": "export-queue",
        "routing_key": "export",
    },
    "app.workers.export_worker.generate_audit_pdf": {
        "queue": "export-queue",
        "routing_key": "export",
    },
}

# ---------------------------------------------------------------------------
# Beat schedule (periodic tasks)
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Prune stale discovery jobs that have been running for > 2 hours
    "cleanup-stale-discovery-jobs": {
        "task": "app.workers.discovery_worker.cleanup_stale_jobs",
        "schedule": crontab(minute="*/30"),  # every 30 minutes
        "options": {"queue": "discovery-queue"},
    },
    # Prune old export files (> 24 h)
    "cleanup-old-exports": {
        "task": "app.workers.export_worker.cleanup_old_exports",
        "schedule": crontab(hour="2", minute="0"),  # daily at 02:00 UTC
        "options": {"queue": "export-queue"},
    },
    # Health-check heartbeat — useful for monitoring
    "worker-heartbeat": {
        "task": "app.workers.discovery_worker.worker_heartbeat",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
        "options": {"queue": "default"},
    },
}
