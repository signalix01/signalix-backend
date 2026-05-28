"""
Celery tasks for AI Screening Engine

This module implements async screening execution and scheduled screening runs.

Requirements: 9.5, 9.6, 9.7
"""
import logging
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from celery import Celery, Task
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, select
import os
import asyncio

from services.screening.models import ScreeningCriteria, ScreeningResult
from services.screening.engine import AIScreeningEngine
from shared.database.models import ScreeningCriteria as DBScreeningCriteria, ScreeningResult as DBScreeningResult

logger = logging.getLogger(__name__)

# Celery app configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    'screening',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per screening task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=86400,  # Results expire after 24 hours
)

# Task routes
celery_app.conf.task_routes = {
    'services.screening.tasks.run_screening_task': {'queue': 'screening'},
    'services.screening.tasks.run_scheduled_screening': {'queue': 'screening'},
}

# Database setup for tasks
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/signalixai")
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class AsyncTask(Task):
    """Base task class that supports async execution"""
    
    def __call__(self, *args, **kwargs):
        """Execute async task in event loop"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.run_async(*args, **kwargs))
    
    async def run_async(self, *args, **kwargs):
        """Override this method in subclasses"""
        raise NotImplementedError


@celery_app.task(name='services.screening.tasks.run_screening_task', bind=True, base=AsyncTask)
async def run_screening_task(self, criteria_id: str, universe: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run screening task asynchronously
    
    This task is enqueued by the on-demand screening API endpoint.
    It runs the full 3-layer screening pipeline and stores results.
    
    Args:
        criteria_id: UUID of screening criteria
        universe: Optional list of symbols to screen (if None, uses default universe)
        
    Returns:
        Dict with screening_id and result summary
        
    Raises:
        Exception: If screening fails
    """
    logger.info(
        f"Screening task started",
        extra={
            "task_id": self.request.id,
            "criteria_id": criteria_id,
            "universe_size": len(universe) if universe else None
        }
    )
    
    async with AsyncSessionLocal() as session:
        try:
            # Fetch criteria from database
            result = await session.execute(
                select(DBScreeningCriteria).where(DBScreeningCriteria.id == uuid.UUID(criteria_id))
            )
            db_criteria = result.scalar_one_or_none()
            
            if not db_criteria:
                raise ValueError(f"Screening criteria not found: {criteria_id}")
            
            # Parse criteria spec
            criteria = ScreeningCriteria(**db_criteria.criteria_spec)
            
            # Get universe if not provided
            if universe is None:
                engine_instance = AIScreeningEngine(session)
                universe = await engine_instance.get_default_universe(criteria.asset_class)
                
                if not universe:
                    raise ValueError(f"No instruments found for asset classes: {criteria.asset_class}")
            
            # Run screening
            engine_instance = AIScreeningEngine(session)
            screening_result = await engine_instance.run_screening(criteria, universe)
            
            # Store result in database
            result_record = DBScreeningResult(
                id=uuid.UUID(screening_result.screening_id),
                criteria_id=uuid.UUID(criteria_id),
                user_id=db_criteria.user_id,
                run_at=datetime.fromisoformat(screening_result.run_at),
                duration_seconds=screening_result.duration_seconds,
                instruments_scanned=screening_result.instruments_scanned,
                instruments_passed=screening_result.instruments_passed,
                results={
                    "results": [inst.model_dump() for inst in screening_result.results]
                }
            )
            
            session.add(result_record)
            await session.commit()
            
            logger.info(
                f"Screening task completed successfully",
                extra={
                    "task_id": self.request.id,
                    "criteria_id": criteria_id,
                    "screening_id": screening_result.screening_id,
                    "instruments_passed": screening_result.instruments_passed,
                    "duration_seconds": screening_result.duration_seconds
                }
            )
            
            # Check if we should trigger alerts
            if screening_result.instruments_passed > 0:
                # Trigger alert delivery for subscribed users
                try:
                    await _trigger_screening_alerts(
                        criteria_id=str(criteria_id),
                        screening_id=screening_result.screening_id,
                        instruments_passed=screening_result.instruments_passed,
                        criteria_name=screening_result.criteria_name
                    )
                except Exception as e:
                    logger.error(f"Failed to trigger screening alerts: {e}")
            
            return {
                "success": True,
                "screening_id": screening_result.screening_id,
                "criteria_name": screening_result.criteria_name,
                "instruments_passed": screening_result.instruments_passed,
                "duration_seconds": screening_result.duration_seconds
            }
            
        except Exception as e:
            logger.error(
                f"Screening task failed",
                extra={
                    "task_id": self.request.id,
                    "criteria_id": criteria_id,
                    "error": str(e)
                }
            )
            await session.rollback()
            raise


@celery_app.task(name='services.screening.tasks.run_scheduled_screening', bind=True, base=AsyncTask)
async def run_scheduled_screening(self, criteria_id: str) -> Dict[str, Any]:
    """
    Run scheduled screening task
    
    This task is triggered by Celery Beat based on the criteria's schedule_cron.
    It runs the screening and triggers alerts if results are found.
    
    Args:
        criteria_id: UUID of screening criteria
        
    Returns:
        Dict with screening_id and result summary
        
    Raises:
        Exception: If screening fails
    """
    logger.info(
        f"Scheduled screening task started",
        extra={
            "task_id": self.request.id,
            "criteria_id": criteria_id
        }
    )
    
    async with AsyncSessionLocal() as session:
        try:
            # Fetch criteria from database
            result = await session.execute(
                select(DBScreeningCriteria).where(
                    DBScreeningCriteria.id == uuid.UUID(criteria_id),
                    DBScreeningCriteria.schedule_enabled == True,
                    DBScreeningCriteria.is_active == True
                )
            )
            db_criteria = result.scalar_one_or_none()
            
            if not db_criteria:
                logger.warning(
                    f"Scheduled screening skipped - criteria not found or not enabled",
                    extra={
                        "task_id": self.request.id,
                        "criteria_id": criteria_id
                    }
                )
                return {
                    "success": False,
                    "message": "Criteria not found or scheduling not enabled"
                }
            
            # Parse criteria spec
            criteria = ScreeningCriteria(**db_criteria.criteria_spec)
            
            # Get default universe
            engine_instance = AIScreeningEngine(session)
            universe = await engine_instance.get_default_universe(criteria.asset_class)
            
            if not universe:
                raise ValueError(f"No instruments found for asset classes: {criteria.asset_class}")
            
            # Run screening
            screening_result = await engine_instance.run_screening(criteria, universe)
            
            # Store result in database
            result_record = DBScreeningResult(
                id=uuid.UUID(screening_result.screening_id),
                criteria_id=uuid.UUID(criteria_id),
                user_id=db_criteria.user_id,
                run_at=datetime.fromisoformat(screening_result.run_at),
                duration_seconds=screening_result.duration_seconds,
                instruments_scanned=screening_result.instruments_scanned,
                instruments_passed=screening_result.instruments_passed,
                results={
                    "results": [inst.model_dump() for inst in screening_result.results]
                }
            )
            
            session.add(result_record)
            await session.commit()
            
            logger.info(
                f"Scheduled screening completed successfully",
                extra={
                    "task_id": self.request.id,
                    "criteria_id": criteria_id,
                    "screening_id": screening_result.screening_id,
                    "instruments_passed": screening_result.instruments_passed,
                    "duration_seconds": screening_result.duration_seconds
                }
            )
            
            # Trigger alerts if results found
            if screening_result.instruments_passed > 0:
                # Trigger alert delivery for users subscribed to this screener
                try:
                    await _trigger_screening_alerts(
                        criteria_id=str(criteria_id),
                        screening_id=screening_result.screening_id,
                        instruments_passed=screening_result.instruments_passed,
                        criteria_name=screening_result.criteria_name,
                        user_id=str(db_criteria.user_id)
                    )
                except Exception as e:
                    logger.error(f"Failed to trigger screening alerts: {e}")
            
            return {
                "success": True,
                "screening_id": screening_result.screening_id,
                "criteria_name": screening_result.criteria_name,
                "instruments_passed": screening_result.instruments_passed,
                "duration_seconds": screening_result.duration_seconds
            }
            
        except Exception as e:
            logger.error(
                f"Scheduled screening task failed",
                extra={
                    "task_id": self.request.id,
                    "criteria_id": criteria_id,
                    "error": str(e)
                }
            )
            await session.rollback()
            raise


@celery_app.task(name='services.screening.tasks.register_dynamic_beat_schedules')
async def register_dynamic_beat_schedules() -> Dict[str, Any]:
    """
    Register dynamic Celery Beat schedules for all enabled screening criteria
    
    This task runs periodically (every 5 minutes) to sync the Celery Beat
    schedule with the database. It reads all criteria with schedule_enabled=True
    and registers/updates their beat schedules.
    
    Returns:
        Dict with count of registered schedules
    """
    logger.info("Registering dynamic beat schedules")
    
    async with AsyncSessionLocal() as session:
        try:
            # Fetch all enabled scheduled criteria
            result = await session.execute(
                select(DBScreeningCriteria).where(
                    DBScreeningCriteria.schedule_enabled == True,
                    DBScreeningCriteria.is_active == True,
                    DBScreeningCriteria.schedule_cron.isnot(None)
                )
            )
            criteria_list = result.scalars().all()
            
            # Build beat schedule dict
            beat_schedule = {}
            for criteria in criteria_list:
                task_name = f"screening_{criteria.id}"
                
                # Parse cron expression
                # Format: "minute hour day month day_of_week"
                # Example: "0 9 * * *" = every day at 9:00 AM
                cron_parts = criteria.schedule_cron.split()
                if len(cron_parts) != 5:
                    logger.warning(
                        f"Invalid cron expression for criteria {criteria.id}: {criteria.schedule_cron}"
                    )
                    continue
                
                beat_schedule[task_name] = {
                    'task': 'services.screening.tasks.run_scheduled_screening',
                    'schedule': {
                        'minute': cron_parts[0],
                        'hour': cron_parts[1],
                        'day_of_month': cron_parts[2],
                        'month_of_year': cron_parts[3],
                        'day_of_week': cron_parts[4],
                    },
                    'args': [str(criteria.id)]
                }
            
            # Update Celery Beat schedule
            celery_app.conf.beat_schedule = beat_schedule
            
            logger.info(
                f"Dynamic beat schedules registered",
                extra={
                    "schedule_count": len(beat_schedule),
                    "criteria_ids": [str(c.id) for c in criteria_list]
                }
            )
            
            return {
                "success": True,
                "schedule_count": len(beat_schedule),
                "criteria_ids": [str(c.id) for c in criteria_list]
            }
            
        except Exception as e:
            logger.error(f"Failed to register dynamic beat schedules: {str(e)}")
            raise


@celery_app.task(name='services.screening.tasks.refresh_screening_snapshot', bind=True, base=AsyncTask)
async def refresh_screening_snapshot(self, check_market_hours: bool = True) -> Dict[str, Any]:
    """
    Refresh the screening_snapshot materialized view
    
    This task runs every 15 minutes during market hours to update the
    materialized view with latest OHLCV data and computed indicators.
    
    Args:
        check_market_hours: If True, only refresh during market hours
        
    Returns:
        Dict with refresh status and duration
        
    Requirements: 9.3, 16.1
    """
    from datetime import datetime, time
    import pytz
    
    logger.info(
        f"Screening snapshot refresh task started",
        extra={
            "task_id": self.request.id,
            "check_market_hours": check_market_hours
        }
    )
    
    # Check market hours if requested
    if check_market_hours:
        ist = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist)
        
        # Check if it's a weekday
        if current_time.weekday() >= 5:  # Saturday or Sunday
            logger.info("Skipping refresh - weekend")
            return {
                "success": True,
                "skipped": True,
                "reason": "weekend"
            }
        
        # Market hours: 09:15 - 15:30 IST
        market_open = time(9, 15)
        market_close = time(15, 30)
        current_time_only = current_time.time()
        
        if not (market_open <= current_time_only <= market_close):
            logger.info(
                f"Skipping refresh - outside market hours",
                extra={"current_time": str(current_time_only)}
            )
            return {
                "success": True,
                "skipped": True,
                "reason": "outside_market_hours",
                "current_time": str(current_time_only)
            }
    
    # Refresh the materialized view
    start_time = datetime.utcnow()
    
    async with AsyncSessionLocal() as session:
        try:
            # Refresh materialized view concurrently (non-blocking)
            await session.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY screening_snapshot;")
            )
            await session.commit()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(
                f"Screening snapshot refreshed successfully",
                extra={
                    "task_id": self.request.id,
                    "duration_seconds": duration
                }
            )
            
            return {
                "success": True,
                "skipped": False,
                "duration_seconds": duration,
                "refreshed_at": end_time.isoformat()
            }
            
        except Exception as e:
            logger.error(
                f"Failed to refresh screening snapshot",
                extra={
                    "task_id": self.request.id,
                    "error": str(e)
                }
            )
            await session.rollback()
            raise


@celery_app.task(name='services.screening.tasks.run_scheduled_screeners', bind=True, base=AsyncTask)
async def run_scheduled_screeners(self) -> Dict[str, Any]:
    """
    Run all scheduled screeners that are due
    
    This task runs every 15 minutes and checks each criteria's cron schedule
    to determine if it should run. This is an alternative to dynamic beat
    schedules for simpler deployment.
    
    Returns:
        Dict with count of screeners run
        
    Requirements: 9.5, 9.6
    """
    from croniter import croniter
    from datetime import datetime
    import pytz
    
    logger.info(
        f"Running scheduled screeners check",
        extra={"task_id": self.request.id}
    )
    
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    async with AsyncSessionLocal() as session:
        try:
            # Fetch all enabled scheduled criteria
            result = await session.execute(
                select(DBScreeningCriteria).where(
                    DBScreeningCriteria.schedule_enabled == True,
                    DBScreeningCriteria.is_active == True,
                    DBScreeningCriteria.schedule_cron.isnot(None)
                )
            )
            criteria_list = result.scalars().all()
            
            screeners_run = 0
            screeners_skipped = 0
            errors = []
            
            for criteria in criteria_list:
                try:
                    # Parse cron expression
                    cron = croniter(criteria.schedule_cron, current_time)
                    
                    # Check if this screener should run now (within last 15 minutes)
                    prev_run = cron.get_prev(datetime)
                    time_since_prev = (current_time - prev_run).total_seconds()
                    
                    # If previous scheduled time was within last 15 minutes, run it
                    if time_since_prev <= 900:  # 15 minutes
                        logger.info(
                            f"Running scheduled screener",
                            extra={
                                "criteria_id": str(criteria.id),
                                "criteria_name": criteria.name,
                                "time_since_prev": time_since_prev
                            }
                        )
                        
                        # Enqueue the screening task
                        from services.screening.tasks import run_scheduled_screening
                        run_scheduled_screening.delay(str(criteria.id))
                        
                        screeners_run += 1
                    else:
                        screeners_skipped += 1
                        
                except Exception as e:
                    logger.error(
                        f"Error checking schedule for criteria {criteria.id}: {str(e)}"
                    )
                    errors.append({
                        "criteria_id": str(criteria.id),
                        "error": str(e)
                    })
            
            logger.info(
                f"Scheduled screeners check completed",
                extra={
                    "task_id": self.request.id,
                    "total_criteria": len(criteria_list),
                    "screeners_run": screeners_run,
                    "screeners_skipped": screeners_skipped,
                    "errors": len(errors)
                }
            )
            
            return {
                "success": True,
                "total_criteria": len(criteria_list),
                "screeners_run": screeners_run,
                "screeners_skipped": screeners_skipped,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(
                f"Failed to run scheduled screeners check",
                extra={
                    "task_id": self.request.id,
                    "error": str(e)
                }
            )
            raise


# Configure beat schedule for the schedule registration task itself
# This runs every 5 minutes to sync schedules with database
celery_app.conf.beat_schedule = {
    'register-dynamic-schedules': {
        'task': 'services.screening.tasks.register_dynamic_beat_schedules',
        'schedule': 300.0,  # Every 5 minutes
    },
}


async def _trigger_screening_alerts(
    criteria_id: str,
    screening_id: str,
    instruments_passed: int,
    criteria_name: str,
    user_id: Optional[str] = None
):
    """
    Trigger alert delivery for screening results
    
    This function sends screening result alerts to subscribed users via
    the alerts delivery engine.
    
    Args:
        criteria_id: UUID of screening criteria
        screening_id: UUID of screening result
        instruments_passed: Number of instruments that passed screening
        criteria_name: Name of the screening criteria
        user_id: User ID who owns the criteria
    """
    try:
        import httpx
        
        ALERTS_SERVICE_URL = os.getenv("ALERTS_SERVICE_URL", "http://localhost:8005")
        
        # Prepare alert payload
        alert_payload = {
            "type": "screening_result",
            "severity": "info",
            "title": f"Screening Complete: {criteria_name}",
            "description": f"Found {instruments_passed} instruments matching your criteria",
            "metadata": {
                "criteria_id": criteria_id,
                "screening_id": screening_id,
                "instruments_passed": instruments_passed,
                "criteria_name": criteria_name
            },
            "user_id": user_id
        }
        
        # Send to alerts delivery engine
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ALERTS_SERVICE_URL}/api/v1/alerts/deliver",
                json=alert_payload
            )
            
            if response.status_code == 200:
                logger.info(
                    f"Alert delivered for screening {screening_id}",
                    extra={
                        "screening_id": screening_id,
                        "criteria_id": criteria_id,
                        "instruments_passed": instruments_passed
                    }
                )
            else:
                logger.warning(
                    f"Failed to deliver alert: {response.status_code}",
                    extra={
                        "screening_id": screening_id,
                        "response": response.text
                    }
                )
                
    except Exception as e:
        logger.error(f"Error triggering screening alerts: {e}")
        raise
