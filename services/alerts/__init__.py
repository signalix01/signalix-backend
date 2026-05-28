"""
Alerts Service - Anomaly Detection & Alert Engine
Requirements: 11.1-11.7, 12.1-12.4, 13.1-13.7, 14.1-14.5
"""

from services.alerts.deduplication import (
    DedupService,
    get_dedup_service,
    close_dedup_service
)

__all__ = [
    'DedupService',
    'get_dedup_service',
    'close_dedup_service'
]
