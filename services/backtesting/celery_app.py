"""
Celery application configuration for backtesting tasks.

This module configures Celery for async backtest execution.
In production, Celery workers run these tasks in the background.

Requirements: 4.1, 4.2, 16.5, 16.6
"""
import os
from celery import Celery
from shared.config.settings import settings

# Create Celery app
celery_app = Celery(
    'backtesting',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max per task
    task_soft_time_limit=1500,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (memory cleanup)
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    result_expires=86400,  # Results expire after 24 hours
)

# Task routes (optional - for multiple queues)
celery_app.conf.task_routes = {
    'services.backtesting.tasks.run_backtest_task': {'queue': 'backtesting'},
}

# Beat schedule for periodic tasks (if needed in future)
celery_app.conf.beat_schedule = {}
