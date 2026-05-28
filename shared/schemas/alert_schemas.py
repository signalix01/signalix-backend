"""
Alert Schemas

Re-exports commonly used alert/anomaly types for convenience.
Used by performance tests and external consumers.
"""

from shared.database.models import (
    AnomalyEvent,
    AnomalyType,
    AnomalySeverity,
)

# Alias for backward compatibility — some files import AlertSeverity
AlertSeverity = AnomalySeverity

__all__ = [
    "AnomalyEvent",
    "AnomalyType",
    "AnomalySeverity",
    "AlertSeverity",
]
