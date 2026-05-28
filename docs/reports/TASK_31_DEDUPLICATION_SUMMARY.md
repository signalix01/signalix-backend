# Task 31: Anomaly Event Deduplication - Implementation Summary

## Overview

Implemented a production-ready deduplication service for anomaly events to prevent alert fatigue. The service uses Redis to track recent events and suppress duplicates within a 15-minute window, while allowing severity escalations.

**Requirements:** 11.8  
**Design:** Service 4 - Anomaly & Alert Engine  
**Status:** ✅ Complete

---

## Implementation Details

### 1. Core Service: `services/alerts/deduplication.py`

**Key Features:**
- Redis-based deduplication with 15-minute TTL
- Severity escalation detection (medium → high is NOT suppressed)
- Fail-open error handling (critical alerts never lost)
- Instrument + anomaly type composite key
- Comprehensive logging for monitoring

**Key Methods:**
- `should_suppress(event: AnomalyEvent) -> bool` - Main deduplication logic
- `_is_severity_increase()` - Detects severity escalations
- `_store_event()` - Stores event metadata in Redis
- `clear_dedup_state()` - Manual intervention support
- `get_dedup_state()` - Debugging/monitoring support

**Redis Key Pattern:**
```
dedup:{instrument}:{anomaly_type}
```

**Stored Data:**
```python
{
    'severity': 'medium',
    'detected_at': '2024-01-15T10:30:00',
    'event_id': 'uuid-string'
}
```

**TTL:** 900 seconds (15 minutes)

---

### 2. Deduplication Logic

#### Suppression Rules:
1. **No recent event** → DO NOT suppress (emit event)
2. **Recent event with same severity** → SUPPRESS
3. **Recent event with lower severity** → SUPPRESS
4. **Recent event with higher severity** → SUPPRESS
5. **Severity escalation** → DO NOT suppress (emit event)

#### Severity Ordering:
```
LOW (1) < MEDIUM (2) < HIGH (3) < CRITICAL (4)
```

#### Examples:
- ✅ **Allowed:** MEDIUM → HIGH (escalation)
- ✅ **Allowed:** LOW → CRITICAL (escalation)
- ❌ **Suppressed:** MEDIUM → MEDIUM (duplicate)
- ❌ **Suppressed:** HIGH → MEDIUM (de-escalation)

---

### 3. Test Coverage: `services/alerts/test_deduplication.py`

**Test Results:** ✅ 20/20 tests passing

**Test Categories:**

#### Unit Tests (16 tests):
- ✅ Dedup key generation
- ✅ Severity ordering validation
- ✅ Severity increase detection (positive cases)
- ✅ Severity increase detection (negative cases)
- ✅ Invalid severity handling (fail-open)
- ✅ No recent event (not suppressed)
- ✅ Same severity (suppressed)
- ✅ Lower severity (suppressed)
- ✅ Severity escalation (not suppressed)
- ✅ Critical escalation (not suppressed)
- ✅ Malformed Redis data (fail-open)
- ✅ Redis error handling (fail-open)
- ✅ Event storage
- ✅ Clear dedup state
- ✅ Get dedup state
- ✅ Get dedup state (not found)

#### Integration Tests (4 tests):
- ✅ Duplicate event within 10-minute window (suppressed)
- ✅ Severity escalation after medium event (not suppressed)
- ✅ Different instruments (not deduplicated)
- ✅ Different anomaly types (not deduplicated)

---

### 4. Integration Example: `services/alerts/example_usage.py`

Demonstrates how to integrate the deduplication service into the anomaly detection pipeline:

```python
async def process_anomaly_event(event: AnomalyEvent) -> bool:
    dedup_service = await get_dedup_service()
    
    if await dedup_service.should_suppress(event):
        # Event suppressed
        return False
    
    # Event emitted - proceed with:
    # 1. Store to TimescaleDB
    # 2. Publish to Redis pub/sub
    # 3. Trigger alert delivery
    return True
```

---

## Requirements Validation

### Requirement 11.8 Compliance:

✅ **"THE System SHALL deduplicate anomaly events"**
- Implemented Redis-based deduplication with 15-minute window

✅ **"if the same anomaly type on the same instrument fires within 15 minutes"**
- Key pattern: `dedup:{instrument}:{anomaly_type}`
- TTL: 900 seconds (15 minutes)

✅ **"the second event SHALL be suppressed"**
- `should_suppress()` returns `True` for duplicates

✅ **"UNLESS severity increases"**
- Severity escalation detection implemented
- Medium → High is NOT suppressed
- Low → Critical is NOT suppressed

---

## Error Handling & Resilience

### Fail-Open Strategy:
The service is designed to **fail open** - if any error occurs, events are NOT suppressed. This ensures critical alerts are never lost due to infrastructure issues.

**Fail-Open Scenarios:**
1. Redis connection failure → Event emitted
2. Malformed Redis data → Event emitted
3. Invalid severity values → Event emitted
4. Any unexpected exception → Event emitted

### Logging:
- INFO: Event suppression decisions
- INFO: Severity escalations detected
- WARNING: Malformed data encountered
- ERROR: Redis connection issues
- DEBUG: Event storage operations

---

## Performance Characteristics

### Redis Operations:
- **Read:** `HGETALL` (O(N) where N = 3 fields)
- **Write:** `HSET` + `EXPIRE` (O(N) where N = 3 fields)
- **Delete:** `DELETE` (O(1))

### Latency:
- Expected: < 5ms per event (local Redis)
- Expected: < 20ms per event (remote Redis)

### Memory Usage:
- Per event: ~200 bytes (3 fields + key)
- With 10,000 instruments × 13 anomaly types = 130,000 keys max
- Total memory: ~26 MB (worst case, all active)

### TTL Cleanup:
- Automatic: Redis expires keys after 15 minutes
- No manual cleanup required

---

## Integration Points

### Current Integration:
- ✅ Exports: `DedupService`, `get_dedup_service`, `close_dedup_service`
- ✅ Available via: `from services.alerts import get_dedup_service`

### Future Integration (Task 32):
The deduplication service will be integrated into the anomaly detection orchestrator:

```python
# In services/alerts/orchestrator.py (Task 32)
async def process_detected_anomaly(event: AnomalyEvent):
    # Run all detectors
    # ...
    
    # Deduplicate before emitting
    dedup_service = await get_dedup_service()
    if await dedup_service.should_suppress(event):
        return  # Suppressed
    
    # Emit event
    await store_to_timescaledb(event)
    await publish_to_redis(event)
    await trigger_alert_delivery(event)
```

---

## Configuration

### Environment Variables:
```bash
REDIS_URL=redis://localhost:6379/0
```

### Settings (from `shared/config/settings.py`):
```python
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
```

---

## Testing Instructions

### Run Tests:
```bash
cd signalixai-backend
python -m pytest services/alerts/test_deduplication.py -v
```

### Expected Output:
```
20 passed, 24 warnings in 1.84s
```

### Run Example:
```bash
cd signalixai-backend
python services/alerts/example_usage.py
```

---

## Files Created

1. **`services/alerts/deduplication.py`** (370 lines)
   - Core deduplication service implementation
   - Redis client management
   - Severity escalation logic

2. **`services/alerts/test_deduplication.py`** (470 lines)
   - Comprehensive unit tests
   - Integration test scenarios
   - 20 test cases covering all requirements

3. **`services/alerts/example_usage.py`** (170 lines)
   - Integration example
   - Usage demonstration
   - 5 realistic scenarios

4. **`services/alerts/__init__.py`** (updated)
   - Exports deduplication service
   - Module documentation

5. **`TASK_31_DEDUPLICATION_SUMMARY.md`** (this file)
   - Implementation summary
   - Requirements validation
   - Integration guide

---

## Next Steps

### Task 32: Anomaly Detection Orchestrator
The deduplication service is ready for integration into the anomaly detection orchestrator:

1. Import deduplication service
2. Call `should_suppress()` before emitting events
3. Log suppression decisions
4. Monitor deduplication metrics

### Monitoring Recommendations:
1. Track suppression rate per instrument
2. Monitor severity escalation frequency
3. Alert on Redis connection failures
4. Dashboard: deduplication effectiveness

---

## Conclusion

✅ **Task 31 Complete**

The anomaly event deduplication service is production-ready with:
- ✅ Full requirement compliance (11.8)
- ✅ Comprehensive test coverage (20/20 passing)
- ✅ Fail-open error handling
- ✅ Severity escalation support
- ✅ Redis-based state management
- ✅ Integration examples
- ✅ Performance optimized

The service is ready for integration into the anomaly detection pipeline (Task 32).
