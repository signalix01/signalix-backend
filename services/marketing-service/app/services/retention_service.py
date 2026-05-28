"""
Retention Service

Computes Day 1, Day 7, Day 30 cohort retention rates from user sessions.
Tracks retention by activation status and enables cohort analysis.

Requirements: 10.9
Task: 23
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RetentionService:
    """
    Service for computing and tracking retention metrics
    
    Computes Day 1, Day 7, Day 30 cohort retention rates.
    Tracks retention by activation status for cohort analysis.
    """
    
    def __init__(self):
        """Initialize retention service"""
        # In-memory storage for demo purposes
        # In production, this would use PostgreSQL
        self.user_sessions: Dict[str, List[datetime]] = {}
        self.user_signups: Dict[str, datetime] = {}
        self.user_activation_status: Dict[str, bool] = {}
        self.retention_metrics: List[Dict[str, Any]] = []
    
    def record_user_signup(self, user_id: str, signup_time: datetime, is_activated: bool = False):
        """
        Record a user signup
        
        Args:
            user_id: User ID
            signup_time: Signup timestamp
            is_activated: Whether user is activated
        """
        self.user_signups[user_id] = signup_time
        self.user_activation_status[user_id] = is_activated
        logger.info(f"Recorded signup for user {user_id} at {signup_time}")
    
    def record_user_session(self, user_id: str, session_time: datetime):
        """
        Record a user session
        
        Args:
            user_id: User ID
            session_time: Session timestamp
        """
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        
        self.user_sessions[user_id].append(session_time)
        logger.debug(f"Recorded session for user {user_id} at {session_time}")
    
    def update_activation_status(self, user_id: str, is_activated: bool):
        """
        Update user activation status
        
        Args:
            user_id: User ID
            is_activated: Whether user is activated
        """
        self.user_activation_status[user_id] = is_activated
        logger.info(f"Updated activation status for user {user_id}: {is_activated}")
    
    def compute_retention_for_cohort(
        self,
        cohort_date: datetime,
        retention_day: int
    ) -> Dict[str, Any]:
        """
        Compute retention rate for a specific cohort and retention day
        
        Args:
            cohort_date: Date of the cohort (signup date)
            retention_day: Day to measure retention (1, 7, or 30)
            
        Returns:
            Dictionary with retention metrics
        """
        # Get users who signed up on cohort_date
        cohort_start = cohort_date.replace(hour=0, minute=0, second=0, microsecond=0)
        cohort_end = cohort_start + timedelta(days=1)
        
        cohort_users = [
            user_id for user_id, signup_time in self.user_signups.items()
            if cohort_start <= signup_time < cohort_end
        ]
        
        if not cohort_users:
            return {
                "cohort_date": cohort_date.date().isoformat(),
                "retention_day": retention_day,
                "cohort_size": 0,
                "retained_users": 0,
                "retention_rate": 0.0,
                "activated_cohort_size": 0,
                "activated_retained_users": 0,
                "activated_retention_rate": 0.0,
                "non_activated_cohort_size": 0,
                "non_activated_retained_users": 0,
                "non_activated_retention_rate": 0.0
            }
        
        # Calculate retention window
        retention_date = cohort_start + timedelta(days=retention_day)
        retention_window_start = retention_date
        retention_window_end = retention_date + timedelta(days=1)
        
        # Count retained users (users who had a session on retention_day)
        retained_users = []
        activated_users = []
        non_activated_users = []
        
        for user_id in cohort_users:
            sessions = self.user_sessions.get(user_id, [])
            
            # Check if user had a session on retention day
            had_session = any(
                retention_window_start <= session_time < retention_window_end
                for session_time in sessions
            )
            
            if had_session:
                retained_users.append(user_id)
                
                # Track by activation status
                if self.user_activation_status.get(user_id, False):
                    activated_users.append(user_id)
                else:
                    non_activated_users.append(user_id)
        
        # Calculate overall retention rate
        cohort_size = len(cohort_users)
        retained_count = len(retained_users)
        retention_rate = (retained_count / cohort_size * 100) if cohort_size > 0 else 0.0
        
        # Calculate retention by activation status
        activated_cohort = [
            user_id for user_id in cohort_users
            if self.user_activation_status.get(user_id, False)
        ]
        non_activated_cohort = [
            user_id for user_id in cohort_users
            if not self.user_activation_status.get(user_id, False)
        ]
        
        activated_cohort_size = len(activated_cohort)
        activated_retained_count = len(activated_users)
        activated_retention_rate = (
            (activated_retained_count / activated_cohort_size * 100)
            if activated_cohort_size > 0 else 0.0
        )
        
        non_activated_cohort_size = len(non_activated_cohort)
        non_activated_retained_count = len(non_activated_users)
        non_activated_retention_rate = (
            (non_activated_retained_count / non_activated_cohort_size * 100)
            if non_activated_cohort_size > 0 else 0.0
        )
        
        return {
            "cohort_date": cohort_date.date().isoformat(),
            "retention_day": retention_day,
            "cohort_size": cohort_size,
            "retained_users": retained_count,
            "retention_rate": round(retention_rate, 2),
            "activated_cohort_size": activated_cohort_size,
            "activated_retained_users": activated_retained_count,
            "activated_retention_rate": round(activated_retention_rate, 2),
            "non_activated_cohort_size": non_activated_cohort_size,
            "non_activated_retained_users": non_activated_retained_count,
            "non_activated_retention_rate": round(non_activated_retention_rate, 2)
        }
    
    def compute_all_retention_metrics(self, as_of_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Compute retention metrics for all cohorts
        
        Computes Day 1, Day 7, Day 30 retention for all cohorts that have
        reached the respective retention day.
        
        Args:
            as_of_date: Date to compute metrics as of (defaults to now)
            
        Returns:
            List of retention metrics for all cohorts
        """
        if as_of_date is None:
            as_of_date = datetime.now(timezone.utc)
        
        metrics = []
        
        # Get unique cohort dates
        cohort_dates = set()
        for signup_time in self.user_signups.values():
            cohort_date = signup_time.replace(hour=0, minute=0, second=0, microsecond=0)
            cohort_dates.add(cohort_date)
        
        # Compute retention for each cohort
        for cohort_date in sorted(cohort_dates):
            # Compute Day 1 retention (if cohort is at least 1 day old)
            if as_of_date >= cohort_date + timedelta(days=1):
                day1_metrics = self.compute_retention_for_cohort(cohort_date, 1)
                metrics.append(day1_metrics)
            
            # Compute Day 7 retention (if cohort is at least 7 days old)
            if as_of_date >= cohort_date + timedelta(days=7):
                day7_metrics = self.compute_retention_for_cohort(cohort_date, 7)
                metrics.append(day7_metrics)
            
            # Compute Day 30 retention (if cohort is at least 30 days old)
            if as_of_date >= cohort_date + timedelta(days=30):
                day30_metrics = self.compute_retention_for_cohort(cohort_date, 30)
                metrics.append(day30_metrics)
        
        return metrics
    
    def store_retention_metrics(self, metrics: List[Dict[str, Any]], computed_at: datetime):
        """
        Store retention metrics for historical tracking
        
        Args:
            metrics: List of retention metrics
            computed_at: Timestamp when metrics were computed
        """
        for metric in metrics:
            metric_record = {
                **metric,
                "computed_at": computed_at.isoformat()
            }
            self.retention_metrics.append(metric_record)
        
        logger.info(f"Stored {len(metrics)} retention metrics computed at {computed_at}")
    
    def get_retention_metrics(
        self,
        cohort_date: Optional[str] = None,
        retention_day: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get stored retention metrics with optional filters
        
        Args:
            cohort_date: Filter by cohort date (ISO format)
            retention_day: Filter by retention day (1, 7, or 30)
            start_date: Filter cohorts from this date onwards
            end_date: Filter cohorts up to this date
            
        Returns:
            List of retention metrics matching filters
        """
        filtered_metrics = self.retention_metrics
        
        if cohort_date:
            filtered_metrics = [
                m for m in filtered_metrics
                if m["cohort_date"] == cohort_date
            ]
        
        if retention_day is not None:
            filtered_metrics = [
                m for m in filtered_metrics
                if m["retention_day"] == retention_day
            ]
        
        if start_date:
            filtered_metrics = [
                m for m in filtered_metrics
                if m["cohort_date"] >= start_date
            ]
        
        if end_date:
            filtered_metrics = [
                m for m in filtered_metrics
                if m["cohort_date"] <= end_date
            ]
        
        return filtered_metrics
    
    def get_retention_summary(self) -> Dict[str, Any]:
        """
        Get summary of retention metrics
        
        Returns:
            Summary statistics for retention
        """
        if not self.retention_metrics:
            return {
                "total_cohorts": 0,
                "total_users": 0,
                "avg_day1_retention": 0.0,
                "avg_day7_retention": 0.0,
                "avg_day30_retention": 0.0
            }
        
        # Get unique cohorts
        cohorts = set(m["cohort_date"] for m in self.retention_metrics)
        
        # Calculate average retention rates
        day1_rates = [
            m["retention_rate"] for m in self.retention_metrics
            if m["retention_day"] == 1
        ]
        day7_rates = [
            m["retention_rate"] for m in self.retention_metrics
            if m["retention_day"] == 7
        ]
        day30_rates = [
            m["retention_rate"] for m in self.retention_metrics
            if m["retention_day"] == 30
        ]
        
        return {
            "total_cohorts": len(cohorts),
            "total_users": len(self.user_signups),
            "avg_day1_retention": round(sum(day1_rates) / len(day1_rates), 2) if day1_rates else 0.0,
            "avg_day7_retention": round(sum(day7_rates) / len(day7_rates), 2) if day7_rates else 0.0,
            "avg_day30_retention": round(sum(day30_rates) / len(day30_rates), 2) if day30_rates else 0.0
        }
    
    def run_daily_retention_computation(self):
        """
        Daily cron job to compute retention metrics
        
        This should be scheduled to run daily via rq scheduler.
        Computes retention for all cohorts and stores results.
        """
        logger.info("Starting daily retention computation...")
        
        computed_at = datetime.now(timezone.utc)
        
        # Compute all retention metrics
        metrics = self.compute_all_retention_metrics(as_of_date=computed_at)
        
        # Store metrics for historical tracking
        self.store_retention_metrics(metrics, computed_at)
        
        logger.info(f"Daily retention computation complete. Computed {len(metrics)} metrics.")
        
        return {
            "success": True,
            "computed_at": computed_at.isoformat(),
            "metrics_count": len(metrics),
            "summary": self.get_retention_summary()
        }


# Global retention service instance
retention_service = RetentionService()
