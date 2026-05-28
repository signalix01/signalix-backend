"""
Scheduler Configuration

Sets up rq scheduler for background tasks including daily retention computation.

Requirements: 10.9
Task: 23
"""

import logging
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from datetime import datetime

from app.config import settings
from app.tasks.retention_tasks import schedule_daily_retention_job

logger = logging.getLogger(__name__)


def get_redis_connection():
    """
    Get Redis connection
    
    Returns:
        Redis connection instance
    """
    try:
        redis_conn = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=False
        )
        # Test connection
        redis_conn.ping()
        logger.info("Redis connection established")
        return redis_conn
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        raise


def get_scheduler():
    """
    Get rq Scheduler instance
    
    Returns:
        Scheduler instance
    """
    try:
        redis_conn = get_redis_connection()
        scheduler = Scheduler(connection=redis_conn, queue_name='marketing')
        logger.info("Scheduler initialized")
        return scheduler
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}")
        raise


def get_queue():
    """
    Get rq Queue instance
    
    Returns:
        Queue instance
    """
    try:
        redis_conn = get_redis_connection()
        queue = Queue('marketing', connection=redis_conn)
        logger.info("Queue initialized")
        return queue
    except Exception as e:
        logger.error(f"Failed to initialize queue: {str(e)}")
        raise


def setup_scheduled_jobs():
    """
    Set up all scheduled jobs
    
    This should be called on service startup to schedule recurring jobs.
    """
    try:
        scheduler = get_scheduler()
        
        # Clear any existing jobs with the same ID to avoid duplicates
        for job in scheduler.get_jobs():
            if job.id == "daily_retention_computation":
                scheduler.cancel(job)
                logger.info(f"Cancelled existing job: {job.id}")
        
        # Schedule daily retention computation
        job = schedule_daily_retention_job(scheduler)
        
        logger.info(f"Scheduled jobs set up successfully. Job ID: {job.id}")
        
        return {
            "success": True,
            "jobs": [
                {
                    "id": job.id,
                    "description": job.description,
                    "next_run": job.meta.get('next_run')
                }
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to set up scheduled jobs: {str(e)}")
        raise


def enqueue_task(func, *args, **kwargs):
    """
    Enqueue a task to run in the background
    
    Args:
        func: Function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        Job instance
    """
    try:
        queue = get_queue()
        job = queue.enqueue(func, *args, **kwargs)
        logger.info(f"Enqueued task: {func.__name__} (Job ID: {job.id})")
        return job
    except Exception as e:
        logger.error(f"Failed to enqueue task: {str(e)}")
        raise


def get_job_status(job_id: str):
    """
    Get status of a job
    
    Args:
        job_id: Job ID
        
    Returns:
        Job status information
    """
    try:
        from rq.job import Job
        
        redis_conn = get_redis_connection()
        job = Job.fetch(job_id, connection=redis_conn)
        
        return {
            "id": job.id,
            "status": job.get_status(),
            "result": job.result,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "exc_info": job.exc_info
        }
        
    except Exception as e:
        logger.error(f"Failed to get job status: {str(e)}")
        raise
