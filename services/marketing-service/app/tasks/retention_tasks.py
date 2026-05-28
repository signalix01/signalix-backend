"""
Retention Tasks

Background tasks for retention computation using rq.
Includes daily cron job for computing retention metrics.

Requirements: 10.9
Task: 23
"""

from datetime import datetime, timezone
import logging

from app.services.retention_service import retention_service

logger = logging.getLogger(__name__)


def compute_daily_retention():
    """
    Daily cron job to compute retention metrics
    
    This task should be scheduled to run daily via rq scheduler.
    Computes Day 1, Day 7, Day 30 retention for all cohorts.
    """
    logger.info("Starting daily retention computation task...")
    
    try:
        result = retention_service.run_daily_retention_computation()
        
        logger.info(
            f"Daily retention computation complete. "
            f"Computed {result['metrics_count']} metrics. "
            f"Summary: {result['summary']}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in daily retention computation: {str(e)}")
        raise


def schedule_daily_retention_job(scheduler):
    """
    Schedule the daily retention computation job
    
    Args:
        scheduler: rq Scheduler instance
        
    This should be called on service startup to schedule the daily job.
    The job will run every day at 2:00 AM UTC.
    """
    from rq.job import Job
    
    # Schedule job to run daily at 2:00 AM UTC
    job = scheduler.cron(
        cron_string="0 2 * * *",  # Every day at 2:00 AM
        func=compute_daily_retention,
        id="daily_retention_computation",
        description="Daily retention metrics computation",
        timeout=600,  # 10 minutes timeout
    )
    
    logger.info(f"Scheduled daily retention computation job: {job.id}")
    
    return job


def compute_retention_for_date(date_str: str):
    """
    Compute retention metrics for a specific date
    
    Args:
        date_str: Date string in ISO format (YYYY-MM-DD)
        
    This can be used to backfill retention metrics for historical dates.
    """
    logger.info(f"Computing retention metrics for date: {date_str}")
    
    try:
        # Parse date
        target_date = datetime.fromisoformat(date_str)
        
        # Compute metrics as of target date
        metrics = retention_service.compute_all_retention_metrics(as_of_date=target_date)
        
        # Store metrics
        retention_service.store_retention_metrics(metrics, target_date)
        
        logger.info(f"Computed {len(metrics)} retention metrics for {date_str}")
        
        return {
            "success": True,
            "date": date_str,
            "metrics_count": len(metrics)
        }
        
    except Exception as e:
        logger.error(f"Error computing retention for date {date_str}: {str(e)}")
        raise


def backfill_retention_metrics(start_date: str, end_date: str):
    """
    Backfill retention metrics for a date range
    
    Args:
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)
        
    This can be used to compute historical retention metrics.
    """
    logger.info(f"Backfilling retention metrics from {start_date} to {end_date}")
    
    try:
        from datetime import timedelta
        
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        current_date = start
        total_metrics = 0
        
        while current_date <= end:
            date_str = current_date.date().isoformat()
            result = compute_retention_for_date(date_str)
            total_metrics += result["metrics_count"]
            
            current_date += timedelta(days=1)
        
        logger.info(
            f"Backfill complete. Computed {total_metrics} metrics "
            f"from {start_date} to {end_date}"
        )
        
        return {
            "success": True,
            "start_date": start_date,
            "end_date": end_date,
            "total_metrics": total_metrics
        }
        
    except Exception as e:
        logger.error(f"Error backfilling retention metrics: {str(e)}")
        raise
