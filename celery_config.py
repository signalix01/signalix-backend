"""
Celery Beat Configuration for Signalix Backend

This module configures all scheduled tasks for:
- Screening snapshot refresh (every 15 minutes during market hours)
- Scheduled screeners (dynamic, based on user criteria)
- Isolation Forest model retraining (daily at 03:00 IST)
- FII/DII data fetching (daily at 16:45 IST)
- COT report data fetching (every Friday at 22:30 IST)
- Old anomaly event purging (daily at 02:00 IST)

Requirements: 9.3, 11.4, 12.1, 16.1, 16.2, 16.7

Task 51: Celery beat configuration
"""

import os
from datetime import datetime, time
from celery import Celery
from celery.schedules import crontab
import pytz

from shared.config.settings import settings


# Create main Celery app
celery_app = Celery(
    'signalix',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='Asia/Kolkata',  # IST for Indian market tasks
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    worker_disable_rate_limits=False,
    
    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    result_backend_transport_options={
        'master_name': 'mymaster',
        'visibility_timeout': 3600,
    },
    
    # Broker configuration
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# Task routes - distribute tasks across queues
celery_app.conf.task_routes = {
    # Screening tasks
    'services.screening.tasks.run_screening_task': {'queue': 'screening'},
    'services.screening.tasks.run_scheduled_screening': {'queue': 'screening'},
    'services.screening.tasks.refresh_screening_snapshot': {'queue': 'screening'},
    
    # Alert tasks
    'services.alerts.tasks.retrain_isolation_forest_models': {'queue': 'ml'},
    'services.alerts.tasks.train_isolation_forest_for_instrument': {'queue': 'ml'},
    'services.alerts.tasks.purge_old_anomaly_events': {'queue': 'maintenance'},
    
    # Whale tracker tasks
    'services.alerts.whale_trackers.tasks.fetch_fii_dii_data': {'queue': 'data'},
    'services.alerts.whale_trackers.tasks.fetch_cot_report_data': {'queue': 'data'},
    
    # Default queue for other tasks
    '*': {'queue': 'default'},
}


def is_market_hours(current_time: datetime = None) -> bool:
    """
    Check if current time is within NSE market hours (09:15 - 15:30 IST).
    
    Args:
        current_time: Optional datetime to check (defaults to now in IST)
        
    Returns:
        True if within market hours, False otherwise
    """
    if current_time is None:
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if current_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Market hours: 09:15 - 15:30 IST
    market_open = time(9, 15)
    market_close = time(15, 30)
    current_time_only = current_time.time()
    
    return market_open <= current_time_only <= market_close


# Celery Beat Schedule
# This defines all periodic tasks and their schedules
celery_app.conf.beat_schedule = {
    
    # ========================================================================
    # SCREENING TASKS
    # ========================================================================
    
    'refresh-screening-snapshot': {
        'task': 'services.screening.tasks.refresh_screening_snapshot',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {
            'expires': 600,  # Task expires after 10 minutes if not executed
        },
        'kwargs': {
            'check_market_hours': True,  # Only run during market hours
        },
    },
    
    'run-scheduled-screeners': {
        'task': 'services.screening.tasks.run_scheduled_screeners',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {
            'expires': 600,
        },
    },
    
    # ========================================================================
    # ML MODEL TRAINING TASKS
    # ========================================================================
    
    'retrain-isolation-forest-models': {
        'task': 'services.alerts.tasks.retrain_isolation_forest_models',
        'schedule': crontab(hour=3, minute=0),  # Daily at 03:00 IST
        'options': {
            'expires': 3600,  # Task expires after 1 hour
        },
    },
    
    # ========================================================================
    # DATA FETCHING TASKS
    # ========================================================================
    
    'fetch-fii-dii-data': {
        'task': 'services.alerts.whale_trackers.tasks.fetch_fii_dii_data',
        'schedule': crontab(hour=16, minute=45),  # Daily at 16:45 IST
        'options': {
            'expires': 1800,  # Task expires after 30 minutes
        },
    },
    
    'fetch-cot-report-data': {
        'task': 'services.alerts.whale_trackers.tasks.fetch_cot_report_data',
        'schedule': crontab(
            hour=22,
            minute=30,
            day_of_week=5  # Friday (0=Monday, 6=Sunday)
        ),  # Every Friday at 22:30 IST
        'options': {
            'expires': 3600,
        },
    },
    
    # ========================================================================
    # MAINTENANCE TASKS
    # ========================================================================
    
    'purge-old-anomaly-events': {
        'task': 'services.alerts.tasks.purge_old_anomaly_events',
        'schedule': crontab(hour=2, minute=0),  # Daily at 02:00 IST
        'options': {
            'expires': 3600,
        },
    },
    
    # ========================================================================
    # DYNAMIC SCHEDULE REGISTRATION
    # ========================================================================
    
    'register-dynamic-beat-schedules': {
        'task': 'services.screening.tasks.register_dynamic_beat_schedules',
        'schedule': 300.0,  # Every 5 minutes
        'options': {
            'expires': 240,
        },
    },
}


# ============================================================================
# TASK CONFIGURATION
# ============================================================================

# Task-specific configurations
celery_app.conf.task_annotations = {
    'services.screening.tasks.refresh_screening_snapshot': {
        'rate_limit': '4/h',  # Max 4 times per hour (every 15 min)
        'time_limit': 600,  # 10 minutes max
        'soft_time_limit': 540,  # 9 minutes soft limit
    },
    'services.screening.tasks.run_scheduled_screeners': {
        'rate_limit': '4/h',
        'time_limit': 300,  # 5 minutes max
        'soft_time_limit': 240,
    },
    'services.alerts.tasks.retrain_isolation_forest_models': {
        'rate_limit': '1/d',  # Once per day
        'time_limit': 3600,  # 1 hour max
        'soft_time_limit': 3300,
    },
    'services.alerts.whale_trackers.tasks.fetch_fii_dii_data': {
        'rate_limit': '1/d',
        'time_limit': 1800,  # 30 minutes max
        'soft_time_limit': 1500,
    },
    'services.alerts.whale_trackers.tasks.fetch_cot_report_data': {
        'rate_limit': '1/w',  # Once per week
        'time_limit': 3600,
        'soft_time_limit': 3300,
    },
    'services.alerts.tasks.purge_old_anomaly_events': {
        'rate_limit': '1/d',
        'time_limit': 1800,
        'soft_time_limit': 1500,
    },
}


# ============================================================================
# MONITORING & LOGGING
# ============================================================================

# Event monitoring
celery_app.conf.worker_send_task_events = True
celery_app.conf.task_send_sent_event = True

# Logging
celery_app.conf.worker_log_format = (
    '[%(asctime)s: %(levelname)s/%(processName)s] '
    '[%(task_name)s(%(task_id)s)] %(message)s'
)
celery_app.conf.worker_task_log_format = (
    '[%(asctime)s: %(levelname)s/%(processName)s] '
    '[%(task_name)s(%(task_id)s)] %(message)s'
)


# ============================================================================
# QUEUE CONFIGURATION
# ============================================================================

# Define queue priorities
celery_app.conf.task_default_priority = 5
celery_app.conf.task_queue_max_priority = 10

# Queue definitions with priorities
celery_app.conf.task_queues = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
        'priority': 5,
    },
    'screening': {
        'exchange': 'screening',
        'routing_key': 'screening',
        'priority': 7,  # Higher priority for screening tasks
    },
    'ml': {
        'exchange': 'ml',
        'routing_key': 'ml',
        'priority': 6,
    },
    'data': {
        'exchange': 'data',
        'routing_key': 'data',
        'priority': 6,
    },
    'maintenance': {
        'exchange': 'maintenance',
        'routing_key': 'maintenance',
        'priority': 3,  # Lower priority for maintenance
    },
}


# ============================================================================
# RESULT BACKEND CONFIGURATION
# ============================================================================

celery_app.conf.result_backend_transport_options = {
    'visibility_timeout': 3600,
    'retry_policy': {
        'timeout': 5.0,
    },
}


# ============================================================================
# BEAT SCHEDULER CONFIGURATION
# ============================================================================

# Use database scheduler for dynamic schedules (optional)
# Uncomment if using django-celery-beat or similar
# celery_app.conf.beat_scheduler = 'django_celery_beat.schedulers:DatabaseScheduler'

# Beat sync configuration
celery_app.conf.beat_sync_every = 0  # Sync immediately
celery_app.conf.beat_max_loop_interval = 5  # Check for new tasks every 5 seconds


# ============================================================================
# EXPORT
# ============================================================================

__all__ = ['celery_app', 'is_market_hours']
