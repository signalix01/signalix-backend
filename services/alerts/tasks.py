"""
Celery tasks for alert system.

Includes scheduled tasks for:
- Isolation Forest model retraining (daily at 03:00 IST)
- Anomaly detection pipeline
- Alert delivery

Requirements: 11.4, 16.7
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.config.settings import settings
from services.alerts.detectors.isolation_forest import IsolationForestDetector


# Create Celery app for alerts
celery_app = Celery(
    'alerts',
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
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=86400,  # Results expire after 24 hours
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'retrain-isolation-forest-models': {
        'task': 'services.alerts.tasks.retrain_isolation_forest_models',
        'schedule': crontab(hour=3, minute=0),  # Daily at 03:00 IST
    },
    'purge-old-anomaly-events': {
        'task': 'services.alerts.tasks.purge_old_anomaly_events',
        'schedule': crontab(hour=2, minute=0),  # Daily at 02:00 IST
    },
}


def get_db_engine():
    """Create synchronous database engine for Celery tasks."""
    # Convert async URL to sync URL
    db_url = settings.DATABASE_URL.replace('+asyncpg', '')
    return create_engine(db_url)


def fetch_historical_data(instrument: str, days: int = 90) -> pd.DataFrame:
    """
    Fetch historical OHLCV data for an instrument.
    
    Args:
        instrument: Instrument symbol
        days: Number of days of historical data (default: 90)
    
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    engine = get_db_engine()
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Query historical data from TimescaleDB
    # Assuming there's a market_data table with OHLCV data
    query = text("""
        SELECT 
            timestamp,
            open,
            high,
            low,
            close,
            volume
        FROM market_data
        WHERE instrument = :instrument
          AND timestamp >= :start_date
          AND timestamp <= :end_date
        ORDER BY timestamp ASC
    """)
    
    with engine.connect() as conn:
        result = conn.execute(
            query,
            {
                "instrument": instrument,
                "start_date": start_date,
                "end_date": end_date
            }
        )
        
        rows = result.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        return df


def get_active_instruments() -> List[str]:
    """
    Get list of instruments that need model retraining.
    
    Returns instruments that are:
    - In users' watchlists
    - Have active alert rules
    - Have sufficient trading volume
    
    Returns:
        List of instrument symbols
    """
    engine = get_db_engine()
    
    # Query for instruments in watchlists and alert rules
    query = text("""
        SELECT DISTINCT instrument
        FROM (
            -- Instruments from alert rules
            SELECT UNNEST(instruments) as instrument
            FROM alert_rules
            WHERE instruments != ARRAY['ALL']
            
            UNION
            
            -- Instruments from user watchlists (if watchlist table exists)
            -- SELECT instrument FROM watchlists WHERE active = true
            
            -- For now, we'll use a default set of popular instruments
            SELECT 'NIFTY' as instrument
            UNION SELECT 'BANKNIFTY'
            UNION SELECT 'RELIANCE'
            UNION SELECT 'TCS'
            UNION SELECT 'INFY'
            UNION SELECT 'HDFCBANK'
            UNION SELECT 'ICICIBANK'
            UNION SELECT 'SBIN'
            UNION SELECT 'BTCUSDT'
            UNION SELECT 'ETHUSDT'
        ) instruments
        LIMIT 100  -- Limit to prevent excessive training
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query)
        instruments = [row[0] for row in result.fetchall()]
    
    return instruments


@celery_app.task(name='services.alerts.tasks.retrain_isolation_forest_models')
def retrain_isolation_forest_models() -> Dict[str, Any]:
    """
    Retrain Isolation Forest models for all active instruments.
    
    This task runs daily at 03:00 IST to retrain models on a rolling 90-day window.
    Models are stored in Redis with 48h TTL.
    
    Requirements: 11.4, 16.7
    
    Returns:
        Dictionary with training results:
        {
            "total_instruments": int,
            "successful": int,
            "failed": int,
            "failed_instruments": List[str],
            "duration_seconds": float
        }
    """
    start_time = datetime.utcnow()
    
    # Get list of instruments to train
    instruments = get_active_instruments()
    
    if not instruments:
        return {
            "total_instruments": 0,
            "successful": 0,
            "failed": 0,
            "failed_instruments": [],
            "duration_seconds": 0.0,
            "message": "No instruments found for training"
        }
    
    # Initialize detector
    detector = IsolationForestDetector(
        contamination=0.02,  # 2% expected anomaly rate
        n_estimators=100,
        max_samples=256,
        random_state=42
    )
    
    successful = 0
    failed = 0
    failed_instruments = []
    
    # Train model for each instrument
    for instrument in instruments:
        try:
            # Fetch 90 days of historical data
            data = fetch_historical_data(instrument, days=90)
            
            if len(data) < 30:
                # Insufficient data
                failed += 1
                failed_instruments.append(f"{instrument} (insufficient data: {len(data)} rows)")
                continue
            
            # Train model
            detector.train(data, instrument)
            successful += 1
            
        except Exception as e:
            failed += 1
            failed_instruments.append(f"{instrument} (error: {str(e)})")
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    result = {
        "total_instruments": len(instruments),
        "successful": successful,
        "failed": failed,
        "failed_instruments": failed_instruments,
        "duration_seconds": duration,
        "timestamp": end_time.isoformat()
    }
    
    return result


@celery_app.task(name='services.alerts.tasks.train_isolation_forest_for_instrument')
def train_isolation_forest_for_instrument(instrument: str, days: int = 90) -> Dict[str, Any]:
    """
    Train Isolation Forest model for a specific instrument.
    
    This task can be called on-demand to train/retrain a model for a single instrument.
    
    Args:
        instrument: Instrument symbol
        days: Number of days of historical data (default: 90)
    
    Returns:
        Dictionary with training result:
        {
            "instrument": str,
            "success": bool,
            "data_rows": int,
            "feature_rows": int,
            "error": str (if failed)
        }
    """
    try:
        # Fetch historical data
        data = fetch_historical_data(instrument, days=days)
        
        if len(data) < 30:
            return {
                "instrument": instrument,
                "success": False,
                "data_rows": len(data),
                "feature_rows": 0,
                "error": f"Insufficient data: {len(data)} rows (minimum 30 required)"
            }
        
        # Initialize detector
        detector = IsolationForestDetector(
            contamination=0.02,
            n_estimators=100,
            max_samples=256,
            random_state=42
        )
        
        # Train model
        model = detector.train(data, instrument)
        
        # Compute features to get feature count
        features = detector._compute_features(data)
        
        return {
            "instrument": instrument,
            "success": True,
            "data_rows": len(data),
            "feature_rows": len(features),
            "error": None
        }
        
    except Exception as e:
        return {
            "instrument": instrument,
            "success": False,
            "data_rows": 0,
            "feature_rows": 0,
            "error": str(e)
        }


@celery_app.task(name='services.alerts.tasks.purge_old_anomaly_events')
def purge_old_anomaly_events() -> Dict[str, Any]:
    """
    Purge old anomaly events based on data retention policies.
    
    This task runs daily at 02:00 IST to clean up old anomaly events:
    - Free tier: Keep 30 days
    - Pro tier: Keep 90 days
    
    Requirements: 16.2, 16.3
    
    Returns:
        Dictionary with purge results:
        {
            "total_deleted": int,
            "free_tier_deleted": int,
            "pro_tier_deleted": int,
            "duration_seconds": float
        }
    """
    start_time = datetime.utcnow()
    
    engine = get_db_engine()
    
    try:
        with engine.connect() as conn:
            # Calculate retention dates
            free_tier_cutoff = datetime.utcnow() - timedelta(days=30)
            pro_tier_cutoff = datetime.utcnow() - timedelta(days=90)
            
            # Delete old events for free tier users
            free_tier_query = text("""
                DELETE FROM anomaly_events
                WHERE detected_at < :cutoff_date
                  AND user_id IN (
                      SELECT id FROM users 
                      WHERE subscription_tier IN ('free', 'equity')
                  )
            """)
            
            free_tier_result = conn.execute(
                free_tier_query,
                {"cutoff_date": free_tier_cutoff}
            )
            free_tier_deleted = free_tier_result.rowcount
            
            # Delete old events for pro tier users
            pro_tier_query = text("""
                DELETE FROM anomaly_events
                WHERE detected_at < :cutoff_date
                  AND user_id IN (
                      SELECT id FROM users 
                      WHERE subscription_tier IN ('fo', 'pro', 'enterprise')
                  )
            """)
            
            pro_tier_result = conn.execute(
                pro_tier_query,
                {"cutoff_date": pro_tier_cutoff}
            )
            pro_tier_deleted = pro_tier_result.rowcount
            
            conn.commit()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            result = {
                "success": True,
                "total_deleted": free_tier_deleted + pro_tier_deleted,
                "free_tier_deleted": free_tier_deleted,
                "pro_tier_deleted": pro_tier_deleted,
                "free_tier_cutoff": free_tier_cutoff.isoformat(),
                "pro_tier_cutoff": pro_tier_cutoff.isoformat(),
                "duration_seconds": duration,
                "timestamp": end_time.isoformat()
            }
            
            return result
            
    except Exception as e:
        return {
            "success": False,
            "total_deleted": 0,
            "free_tier_deleted": 0,
            "pro_tier_deleted": 0,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
