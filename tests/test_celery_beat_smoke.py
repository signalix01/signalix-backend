"""
Smoke tests for Celery Beat scheduled tasks

This test suite verifies that each scheduled task can be manually triggered
without errors. It does not test the full functionality, only that tasks
can execute successfully.

Task 51: Celery beat configuration - smoke test
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from celery_config import celery_app, is_market_hours


class TestCeleryBeatSmoke:
    """Smoke tests for all Celery Beat scheduled tasks"""
    
    def test_celery_app_configuration(self):
        """Test that Celery app is configured correctly"""
        assert celery_app is not None
        assert celery_app.conf.timezone == 'Asia/Kolkata'
        assert celery_app.conf.task_serializer == 'json'
        assert celery_app.conf.enable_utc is True
    
    def test_beat_schedule_exists(self):
        """Test that beat schedule is configured"""
        assert hasattr(celery_app.conf, 'beat_schedule')
        assert len(celery_app.conf.beat_schedule) > 0
        
        # Verify all expected tasks are in schedule
        expected_tasks = [
            'refresh-screening-snapshot',
            'run-scheduled-screeners',
            'retrain-isolation-forest-models',
            'fetch-fii-dii-data',
            'fetch-cot-report-data',
            'purge-old-anomaly-events',
            'register-dynamic-beat-schedules'
        ]
        
        for task_name in expected_tasks:
            assert task_name in celery_app.conf.beat_schedule, f"Task {task_name} not in beat schedule"
    
    def test_task_routes_configured(self):
        """Test that task routes are configured"""
        assert hasattr(celery_app.conf, 'task_routes')
        assert len(celery_app.conf.task_routes) > 0
        
        # Verify key routes
        assert 'services.screening.tasks.run_screening_task' in celery_app.conf.task_routes
        assert 'services.alerts.tasks.retrain_isolation_forest_models' in celery_app.conf.task_routes
    
    def test_is_market_hours_weekday(self):
        """Test market hours detection for weekday"""
        # Monday 10:00 IST (within market hours)
        from datetime import datetime, time
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        test_time = datetime(2024, 1, 8, 10, 0, 0, tzinfo=ist)  # Monday
        
        result = is_market_hours(test_time)
        assert result is True
    
    def test_is_market_hours_weekend(self):
        """Test market hours detection for weekend"""
        from datetime import datetime
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        test_time = datetime(2024, 1, 6, 10, 0, 0, tzinfo=ist)  # Saturday
        
        result = is_market_hours(test_time)
        assert result is False
    
    def test_is_market_hours_before_open(self):
        """Test market hours detection before market opens"""
        from datetime import datetime
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        test_time = datetime(2024, 1, 8, 9, 0, 0, tzinfo=ist)  # Monday 9:00 AM
        
        result = is_market_hours(test_time)
        assert result is False
    
    def test_is_market_hours_after_close(self):
        """Test market hours detection after market closes"""
        from datetime import datetime
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        test_time = datetime(2024, 1, 8, 16, 0, 0, tzinfo=ist)  # Monday 4:00 PM
        
        result = is_market_hours(test_time)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_screening_snapshot_task(self):
        """Smoke test: refresh_screening_snapshot task can be triggered"""
        from services.screening.tasks import refresh_screening_snapshot
        
        # Mock database session
        with patch('services.screening.tasks.AsyncSessionLocal') as mock_session:
            mock_conn = MagicMock()
            mock_conn.execute = MagicMock()
            mock_conn.commit = MagicMock()
            mock_session.return_value.__aenter__.return_value = mock_conn
            
            # Create mock task instance
            mock_task = MagicMock()
            mock_task.request.id = "test-task-id"
            
            # Call task with check_market_hours=False to skip time check
            result = await refresh_screening_snapshot.run_async(
                mock_task,
                check_market_hours=False
            )
            
            assert result is not None
            assert 'success' in result
    
    @pytest.mark.asyncio
    async def test_run_scheduled_screeners_task(self):
        """Smoke test: run_scheduled_screeners task can be triggered"""
        from services.screening.tasks import run_scheduled_screeners
        
        # Mock database session
        with patch('services.screening.tasks.AsyncSessionLocal') as mock_session:
            mock_conn = MagicMock()
            mock_conn.execute = MagicMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
            mock_session.return_value.__aenter__.return_value = mock_conn
            
            # Create mock task instance
            mock_task = MagicMock()
            mock_task.request.id = "test-task-id"
            
            # Call task
            result = await run_scheduled_screeners.run_async(mock_task)
            
            assert result is not None
            assert 'success' in result
            assert 'total_criteria' in result
    
    def test_retrain_isolation_forest_models_task(self):
        """Smoke test: retrain_isolation_forest_models task can be triggered"""
        from services.alerts.tasks import retrain_isolation_forest_models
        
        # Mock database and detector
        with patch('services.alerts.tasks.get_active_instruments') as mock_instruments, \
             patch('services.alerts.tasks.fetch_historical_data') as mock_data, \
             patch('services.alerts.tasks.IsolationForestDetector') as mock_detector:
            
            # Return empty list to skip actual training
            mock_instruments.return_value = []
            
            # Call task
            result = retrain_isolation_forest_models()
            
            assert result is not None
            assert 'success' in result or 'total_instruments' in result
            assert result['total_instruments'] == 0
    
    def test_purge_old_anomaly_events_task(self):
        """Smoke test: purge_old_anomaly_events task can be triggered"""
        from services.alerts.tasks import purge_old_anomaly_events
        
        # Mock database
        with patch('services.alerts.tasks.get_db_engine') as mock_engine:
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.rowcount = 0
            mock_conn.execute = MagicMock(return_value=mock_result)
            mock_conn.commit = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_engine.return_value.connect = MagicMock(return_value=mock_conn)
            
            # Call task
            result = purge_old_anomaly_events()
            
            assert result is not None
            assert 'success' in result
            assert 'total_deleted' in result
    
    def test_fetch_fii_dii_data_task(self):
        """Smoke test: fetch_fii_dii_data task can be triggered"""
        from services.alerts.whale_trackers.tasks import fetch_fii_dii_data
        
        # Mock HTTP client and database
        with patch('services.alerts.whale_trackers.tasks.httpx.AsyncClient') as mock_client, \
             patch('services.alerts.whale_trackers.tasks.store_anomaly_event') as mock_store:
            
            mock_store.return_value = True
            
            # Call task
            result = fetch_fii_dii_data()
            
            assert result is not None
            assert 'success' in result
            assert 'events_generated' in result
    
    def test_fetch_cot_report_data_task(self):
        """Smoke test: fetch_cot_report_data task can be triggered"""
        from services.alerts.whale_trackers.tasks import fetch_cot_report_data
        
        # Mock HTTP client and database
        with patch('services.alerts.whale_trackers.tasks.httpx.AsyncClient') as mock_client, \
             patch('services.alerts.whale_trackers.tasks.store_anomaly_event') as mock_store:
            
            mock_store.return_value = True
            
            # Call task
            result = fetch_cot_report_data()
            
            assert result is not None
            assert 'success' in result
            assert 'events_generated' in result
    
    def test_all_tasks_have_annotations(self):
        """Test that all scheduled tasks have proper annotations"""
        if hasattr(celery_app.conf, 'task_annotations'):
            annotations = celery_app.conf.task_annotations
            
            # Verify key tasks have rate limits
            assert 'services.screening.tasks.refresh_screening_snapshot' in annotations
            assert 'rate_limit' in annotations['services.screening.tasks.refresh_screening_snapshot']
            
            assert 'services.alerts.tasks.retrain_isolation_forest_models' in annotations
            assert 'rate_limit' in annotations['services.alerts.tasks.retrain_isolation_forest_models']
    
    def test_task_time_limits_configured(self):
        """Test that tasks have appropriate time limits"""
        # Check global time limits
        assert celery_app.conf.task_time_limit == 3600  # 1 hour
        assert celery_app.conf.task_soft_time_limit == 3300  # 55 minutes
        
        # Check task-specific limits
        if hasattr(celery_app.conf, 'task_annotations'):
            annotations = celery_app.conf.task_annotations
            
            # Screening snapshot should have shorter time limit
            snapshot_task = 'services.screening.tasks.refresh_screening_snapshot'
            if snapshot_task in annotations:
                assert annotations[snapshot_task]['time_limit'] == 600  # 10 minutes


class TestCeleryBeatSchedules:
    """Test individual task schedules"""
    
    def test_refresh_screening_snapshot_schedule(self):
        """Test refresh_screening_snapshot runs every 15 minutes"""
        schedule = celery_app.conf.beat_schedule['refresh-screening-snapshot']
        
        assert schedule['task'] == 'services.screening.tasks.refresh_screening_snapshot'
        assert 'schedule' in schedule
        # Crontab schedule for every 15 minutes
        assert schedule['schedule'].minute == '*/15'
    
    def test_retrain_isolation_forest_schedule(self):
        """Test retrain_isolation_forest_models runs daily at 03:00 IST"""
        schedule = celery_app.conf.beat_schedule['retrain-isolation-forest-models']
        
        assert schedule['task'] == 'services.alerts.tasks.retrain_isolation_forest_models'
        assert 'schedule' in schedule
        # Crontab schedule for 03:00
        assert schedule['schedule'].hour == 3
        assert schedule['schedule'].minute == 0
    
    def test_fetch_fii_dii_schedule(self):
        """Test fetch_fii_dii_data runs daily at 16:45 IST"""
        schedule = celery_app.conf.beat_schedule['fetch-fii-dii-data']
        
        assert schedule['task'] == 'services.alerts.whale_trackers.tasks.fetch_fii_dii_data'
        assert 'schedule' in schedule
        # Crontab schedule for 16:45
        assert schedule['schedule'].hour == 16
        assert schedule['schedule'].minute == 45
    
    def test_fetch_cot_report_schedule(self):
        """Test fetch_cot_report_data runs every Friday at 22:30 IST"""
        schedule = celery_app.conf.beat_schedule['fetch-cot-report-data']
        
        assert schedule['task'] == 'services.alerts.whale_trackers.tasks.fetch_cot_report_data'
        assert 'schedule' in schedule
        # Crontab schedule for Friday 22:30
        assert schedule['schedule'].hour == 22
        assert schedule['schedule'].minute == 30
        assert schedule['schedule'].day_of_week == 5  # Friday
    
    def test_purge_old_anomaly_events_schedule(self):
        """Test purge_old_anomaly_events runs daily at 02:00 IST"""
        schedule = celery_app.conf.beat_schedule['purge-old-anomaly-events']
        
        assert schedule['task'] == 'services.alerts.tasks.purge_old_anomaly_events'
        assert 'schedule' in schedule
        # Crontab schedule for 02:00
        assert schedule['schedule'].hour == 2
        assert schedule['schedule'].minute == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
