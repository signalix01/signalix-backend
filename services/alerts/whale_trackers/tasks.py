"""
Celery tasks for whale tracker data fetching.

Includes scheduled tasks for:
- FII/DII data fetching (daily at 16:45 IST after NSE publishes)
- COT report data fetching (every Friday at 22:30 IST after CFTC publishes)

Requirements: 12.1, 12.3, 12.4
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import httpx

from shared.config.settings import settings
from services.alerts.models import AnomalyEvent, AnomalySeverity, AnomalyType

logger = logging.getLogger(__name__)

# Create Celery app for whale trackers
celery_app = Celery(
    'whale_trackers',
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
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=86400,  # Results expire after 24 hours
)


def get_db_engine():
    """Create synchronous database engine for Celery tasks."""
    # Convert async URL to sync URL
    db_url = settings.DATABASE_URL.replace('+asyncpg', '')
    return create_engine(db_url)


def store_anomaly_event(event: AnomalyEvent) -> bool:
    """
    Store anomaly event in database.
    
    Args:
        event: AnomalyEvent to store
        
    Returns:
        True if stored successfully, False otherwise
    """
    engine = get_db_engine()
    
    try:
        with engine.connect() as conn:
            query = text("""
                INSERT INTO anomaly_events (
                    id, instrument, asset_class, anomaly_type, severity,
                    description, detected_at, z_score, price, raw_data
                )
                VALUES (
                    gen_random_uuid(), :instrument, :asset_class, :anomaly_type,
                    :severity, :description, :detected_at, :z_score, :price, :raw_data
                )
            """)
            
            conn.execute(
                query,
                {
                    "instrument": event.instrument,
                    "asset_class": event.asset_class,
                    "anomaly_type": event.anomaly_type.value,
                    "severity": event.severity.value,
                    "description": event.description,
                    "detected_at": event.detected_at,
                    "z_score": event.z_score,
                    "price": event.price,
                    "raw_data": event.raw_data
                }
            )
            conn.commit()
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to store anomaly event: {str(e)}")
        return False


@celery_app.task(name='services.alerts.whale_trackers.tasks.fetch_fii_dii_data')
def fetch_fii_dii_data() -> Dict[str, Any]:
    """
    Fetch FII/DII data from NSDL and generate anomaly events.
    
    This task runs daily at 16:45 IST after NSE publishes the data.
    Generates events for FII/DII net activity >= Rs 100 Cr.
    
    Requirements: 12.1, 12.3, 12.4
    
    Returns:
        Dictionary with fetch results:
        {
            "success": bool,
            "events_generated": int,
            "fii_net_cr": float,
            "dii_net_cr": float,
            "date": str
        }
    """
    logger.info("Starting FII/DII data fetch task")
    
    start_time = datetime.utcnow()
    
    try:
        # Fetch FII/DII data from NSDL
        # Note: This is a mock implementation. Replace with actual NSDL API endpoint
        # NSDL publishes data at: https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx
        
        # For now, we'll use a placeholder endpoint
        # In production, you would scrape the NSDL website or use an API
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Mock endpoint - replace with actual NSDL data source
            # response = await client.get("https://www.fpi.nsdl.co.in/api/fii-dii-data")
            
            # For demonstration, using mock data
            fii_dii_data = {
                "date": datetime.utcnow().date().isoformat(),
                "fii_net": 0.0,  # Will be populated from actual API
                "dii_net": 0.0,  # Will be populated from actual API
                "fii_buy": 0.0,
                "fii_sell": 0.0,
                "dii_buy": 0.0,
                "dii_sell": 0.0
            }
            
            # TODO: Parse actual response from NSDL
            # fii_dii_data = response.json()
        
        events_generated = 0
        FII_DII_NET_THRESHOLD_CR = 100.0
        
        fii_net_cr = float(fii_dii_data.get("fii_net", 0))
        dii_net_cr = float(fii_dii_data.get("dii_net", 0))
        
        # Generate FII event if threshold exceeded
        if abs(fii_net_cr) >= FII_DII_NET_THRESHOLD_CR:
            direction = "buying" if fii_net_cr > 0 else "selling"
            severity = AnomalySeverity.CRITICAL if abs(fii_net_cr) >= 500 else AnomalySeverity.HIGH
            
            event = AnomalyEvent(
                instrument="NIFTY",
                asset_class="equity",
                anomaly_type=AnomalyType.INSTITUTIONAL_FLOW,
                severity=severity,
                description=f"FII {direction} of Rs {abs(fii_net_cr):.2f} Cr detected",
                detected_at=datetime.utcnow(),
                z_score=None,
                price=None,
                raw_data={
                    "source": "NSDL_FII",
                    "net_value_cr": fii_net_cr,
                    "direction": direction,
                    "threshold_cr": FII_DII_NET_THRESHOLD_CR,
                    "original_data": fii_dii_data
                }
            )
            
            if store_anomaly_event(event):
                events_generated += 1
        
        # Generate DII event if threshold exceeded
        if abs(dii_net_cr) >= FII_DII_NET_THRESHOLD_CR:
            direction = "buying" if dii_net_cr > 0 else "selling"
            severity = AnomalySeverity.CRITICAL if abs(dii_net_cr) >= 500 else AnomalySeverity.HIGH
            
            event = AnomalyEvent(
                instrument="NIFTY",
                asset_class="equity",
                anomaly_type=AnomalyType.INSTITUTIONAL_FLOW,
                severity=severity,
                description=f"DII {direction} of Rs {abs(dii_net_cr):.2f} Cr detected",
                detected_at=datetime.utcnow(),
                z_score=None,
                price=None,
                raw_data={
                    "source": "NSDL_DII",
                    "net_value_cr": dii_net_cr,
                    "direction": direction,
                    "threshold_cr": FII_DII_NET_THRESHOLD_CR,
                    "original_data": fii_dii_data
                }
            )
            
            if store_anomaly_event(event):
                events_generated += 1
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "success": True,
            "events_generated": events_generated,
            "fii_net_cr": fii_net_cr,
            "dii_net_cr": dii_net_cr,
            "date": fii_dii_data.get("date"),
            "duration_seconds": duration,
            "timestamp": end_time.isoformat()
        }
        
        logger.info(
            f"FII/DII data fetch completed",
            extra=result
        )
        
        return result
        
    except Exception as e:
        logger.error(f"FII/DII data fetch failed: {str(e)}")
        return {
            "success": False,
            "events_generated": 0,
            "fii_net_cr": 0.0,
            "dii_net_cr": 0.0,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@celery_app.task(name='services.alerts.whale_trackers.tasks.fetch_cot_report_data')
def fetch_cot_report_data() -> Dict[str, Any]:
    """
    Fetch CFTC Commitments of Traders (COT) report data.
    
    This task runs every Friday at 22:30 IST after CFTC publishes the report.
    CFTC publishes COT reports every Friday at 3:30 PM EST (1:00 AM IST Saturday).
    
    Generates events for large speculator position changes >= 5,000 contracts.
    
    Requirements: 12.1
    
    Returns:
        Dictionary with fetch results:
        {
            "success": bool,
            "events_generated": int,
            "instruments_processed": int,
            "report_date": str
        }
    """
    logger.info("Starting COT report data fetch task")
    
    start_time = datetime.utcnow()
    
    try:
        # Fetch COT report from CFTC
        # CFTC publishes reports at: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
        
        # For now, we'll use a placeholder
        # In production, you would fetch from CFTC API or parse their CSV files
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Mock endpoint - replace with actual CFTC data source
            # CFTC provides data in CSV format
            # response = await client.get("https://www.cftc.gov/files/dea/cotarchives/2024/futures/deacot2024.zip")
            
            # For demonstration, using mock data
            cot_data = {
                "report_date": datetime.utcnow().date().isoformat(),
                "instruments": []
            }
            
            # TODO: Parse actual COT report CSV
            # cot_data = parse_cot_report(response.content)
        
        events_generated = 0
        COT_POSITION_CHANGE_THRESHOLD = 5000  # contracts
        
        # Process each instrument in the report
        for instrument_data in cot_data.get("instruments", []):
            instrument = instrument_data.get("instrument")
            position_change = instrument_data.get("large_spec_net_change", 0)
            
            if abs(position_change) >= COT_POSITION_CHANGE_THRESHOLD:
                direction = "long" if position_change > 0 else "short"
                severity = AnomalySeverity.HIGH if abs(position_change) >= 10000 else AnomalySeverity.MEDIUM
                
                event = AnomalyEvent(
                    instrument=instrument,
                    asset_class="forex",  # COT covers forex, commodities, etc.
                    anomaly_type=AnomalyType.INSTITUTIONAL_FLOW,
                    severity=severity,
                    description=f"COT: Large speculators {direction} position change of {abs(position_change):,} contracts in {instrument}",
                    detected_at=datetime.utcnow(),
                    z_score=None,
                    price=None,
                    raw_data={
                        "source": "CFTC_COT",
                        "position_change": position_change,
                        "direction": direction,
                        "threshold": COT_POSITION_CHANGE_THRESHOLD,
                        "original_data": instrument_data
                    }
                )
                
                if store_anomaly_event(event):
                    events_generated += 1
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        result = {
            "success": True,
            "events_generated": events_generated,
            "instruments_processed": len(cot_data.get("instruments", [])),
            "report_date": cot_data.get("report_date"),
            "duration_seconds": duration,
            "timestamp": end_time.isoformat()
        }
        
        logger.info(
            f"COT report data fetch completed",
            extra=result
        )
        
        return result
        
    except Exception as e:
        logger.error(f"COT report data fetch failed: {str(e)}")
        return {
            "success": False,
            "events_generated": 0,
            "instruments_processed": 0,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Beat schedule for whale tracker tasks
celery_app.conf.beat_schedule = {
    'fetch-fii-dii-data': {
        'task': 'services.alerts.whale_trackers.tasks.fetch_fii_dii_data',
        'schedule': crontab(hour=16, minute=45),  # Daily at 16:45 IST
    },
    'fetch-cot-report-data': {
        'task': 'services.alerts.whale_trackers.tasks.fetch_cot_report_data',
        'schedule': crontab(hour=22, minute=30, day_of_week=5),  # Friday at 22:30 IST
    },
}
