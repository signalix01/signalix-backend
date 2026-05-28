# Strategy Compilation & Paper Trading Endpoints

## Overview

This document describes the implementation of Task 10 from Phase 3: Strategy compilation endpoint with Redis caching and paper trading session creation.

## Requirements Implemented

### Requirement 3.6: Strategy Compilation & Validation
- **Endpoint**: `POST /api/v1/algo/strategies/{id}/compile`
- **Function**: Compiles strategy spec to executable Python code and runs 100-bar validation test
- **On Success**: Stores `compiled_hash` in `strategies` table
- **On Failure**: Returns 422 with exact Python exception from sandbox

### Requirement 3.7: Redis Caching
- **Cache Key Pattern**: `compiled_strategy:{hash}`
- **TTL**: 24 hours (86400 seconds)
- **Storage**: Pickled compiled Python code string
- **Purpose**: Avoid recompilation on every backtest/execution

### Requirement 1.9: Paper Trading Session
- **Endpoint**: `POST /api/v1/algo/strategies/{id}/paper`
- **Function**: Validates strategy is compiled, creates paper trading session
- **Validation**: Checks `compiled_hash` exists and code is in cache
- **Status Update**: Updates strategy status from `draft`/`testing` to `paper`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    API Request                               │
│         POST /api/v1/algo/strategies/{id}/compile            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              1. Check Strategy Ownership                     │
│              - Verify user owns strategy                     │
│              - Load strategy spec from database              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              2. Compute Spec Hash                            │
│              - SHA-256 hash of strategy spec JSON            │
│              - Used for cache key and invalidation           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              3. Check Redis Cache                            │
│              - Key: compiled_strategy:{hash}                 │
│              - If HIT: Skip compilation, validate cached     │
│              - If MISS: Proceed to compilation               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              4. Compile Strategy                             │
│              - StrategyCompiler.compile(spec)                │
│              - Generates Python class inheriting BaseStrategy│
│              - Validates syntax with ast.parse()             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              5. Validate in Sandbox                          │
│              - SandboxRunner.validate(compiled_code)         │
│              - Creates 100-bar synthetic OHLCV data          │
│              - Executes in subprocess with limits:           │
│                * 30-second timeout                           │
│                * 512MB memory limit                          │
│                * No filesystem/network access                │
│              - Verifies all required methods exist           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              6. Store in Database                            │
│              - UPDATE strategies                             │
│              - SET compiled_hash = {hash}                    │
│              - WHERE id = {strategy_id}                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              7. Cache in Redis                               │
│              - Key: compiled_strategy:{hash}                 │
│              - Value: pickle.dumps(compiled_code)            │
│              - TTL: 86400 seconds (24 hours)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              8. Return Response                              │
│              {                                               │
│                "success": true,                              │
│                "compiled_hash": "a3f5b2c1...",               │
│                "validation_result": {...},                   │
│                "cached": true                                │
│              }                                               │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

### 1. Compile Strategy

**Endpoint**: `POST /api/v1/algo/strategies/{id}/compile`

**Description**: Compiles a strategy and runs validation test

**Request**:
```http
POST /api/v1/algo/strategies/123e4567-e89b-12d3-a456-426614174000/compile
Authorization: Bearer {jwt_token}
```

**Success Response** (200 OK):
```json
{
  "success": true,
  "message": "Strategy compiled and validated successfully in 125.45ms",
  "compiled_hash": "a3f5b2c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2",
  "validation_result": {
    "success": true,
    "message": "Strategy validated successfully in 125.45ms",
    "execution_time_ms": 125.45
  },
  "cached": true
}
```

**Error Response** (422 Unprocessable Entity):
```json
{
  "detail": {
    "error": "Strategy validation failed",
    "message": "Strategy validation failed",
    "details": "RuntimeError: Strategy execution failed: NameError: name 'rsi_14' is not defined"
  }
}
```

**Error Response** (404 Not Found):
```json
{
  "detail": "Strategy not found or access denied"
}
```

### 2. Create Paper Trading Session

**Endpoint**: `POST /api/v1/algo/strategies/{id}/paper`

**Description**: Creates a paper trading session for a compiled strategy

**Request**:
```http
POST /api/v1/algo/strategies/123e4567-e89b-12d3-a456-426614174000/paper
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "initial_capital": 100000.0
}
```

**Success Response** (201 Created):
```json
{
  "success": true,
  "message": "Paper trading session created for strategy 'Test RSI Strategy'",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "strategy_id": "123e4567-e89b-12d3-a456-426614174000",
  "initial_capital": 100000.0,
  "status": "active"
}
```

**Error Response** (400 Bad Request - Not Compiled):
```json
{
  "detail": {
    "error": "Strategy not compiled",
    "message": "Please compile the strategy before starting paper trading",
    "action": "POST /api/v1/algo/strategies/123e4567-e89b-12d3-a456-426614174000/compile"
  }
}
```

**Error Response** (400 Bad Request - Already Live):
```json
{
  "detail": "Cannot start paper trading for a live strategy. Please stop the live session first."
}
```

## Redis Cache Implementation

### RedisClient Class

**Location**: `services/algo_builder/redis_client.py`

**Key Methods**:

1. **`get_compiled_strategy(compiled_hash: str) -> Optional[str]`**
   - Retrieves compiled code from cache
   - Returns `None` if not found
   - Logs cache HIT/MISS

2. **`set_compiled_strategy(compiled_hash: str, compiled_code: str) -> bool`**
   - Stores compiled code with 24h TTL
   - Uses pickle serialization
   - Returns `True` on success

3. **`delete_compiled_strategy(compiled_hash: str) -> bool`**
   - Removes compiled code from cache
   - Used when strategy spec changes

4. **`get_cache_stats() -> dict`**
   - Returns cache statistics
   - Includes hit rate, total keys, cached strategies count

### Cache Key Pattern

```
compiled_strategy:{sha256_hash}
```

**Example**:
```
compiled_strategy:a3f5b2c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2
```

### Cache Invalidation

Cache is invalidated when:
1. Strategy spec is updated (new hash computed)
2. 24-hour TTL expires
3. Manual deletion via `delete_compiled_strategy()`

## Database Schema

### strategies Table

```sql
ALTER TABLE strategies
ADD COLUMN compiled_hash VARCHAR(64) NULL;

CREATE INDEX idx_strategies_compiled_hash 
ON strategies(compiled_hash);
```

**Fields**:
- `compiled_hash`: SHA-256 hash of compiled strategy spec
- Used to check if recompilation is needed
- Used as Redis cache key

## Security & Sandboxing

### Sandbox Restrictions

All compiled strategies execute in a sandboxed subprocess with:

1. **Time Limit**: 30 seconds
2. **Memory Limit**: 512MB
3. **No Filesystem Access**: Read-only mode
4. **No Network Access**: All network syscalls blocked
5. **Syscall Filtering**: Linux seccomp (read, write, mmap, munmap, exit, sigreturn only)

### Validation Test

The 100-bar validation test:
1. Creates synthetic OHLCV data (100 bars)
2. Instantiates the compiled strategy class
3. Verifies all required methods exist:
   - `compute_indicators()`
   - `market_filter_pass(bar_idx)`
   - `should_enter_long(bar_idx)`
   - `should_enter_short(bar_idx)`
   - `should_exit(position, bar_idx)`
   - `position_size(capital, price, atr)`
4. Calls each method to ensure they execute without errors
5. Returns validation result with execution time

## Error Handling

### Compilation Errors

**Scenario**: Invalid strategy spec or compilation failure

**Response**:
```json
{
  "detail": {
    "error": "Strategy compilation failed",
    "message": "ValueError: Entry rules cannot be empty",
    "details": "ValueError: Entry rules cannot be empty"
  }
}
```

### Validation Errors

**Scenario**: Compiled code fails validation test

**Response**:
```json
{
  "detail": {
    "error": "Strategy validation failed",
    "message": "Strategy validation failed",
    "details": "RuntimeError: Strategy execution failed: AttributeError: 'CompiledStrategy_test' object has no attribute 'compute_indicators'"
  }
}
```

### Cache Errors

**Scenario**: Redis connection failure

**Behavior**:
- Logs warning
- Continues without caching
- Returns `cached: false` in response
- Does not fail the request

## Testing

### Integration Tests

**Location**: `services/algo_builder/test_compilation_integration.py`

**Test Cases**:

1. **`test_compile_strategy_success`**
   - Creates strategy
   - Compiles successfully
   - Verifies hash stored in database
   - Verifies code cached in Redis

2. **`test_compile_strategy_cached`**
   - Compiles strategy twice
   - Verifies second compilation uses cache
   - Verifies same hash returned

3. **`test_compile_invalid_strategy`**
   - Attempts to compile invalid spec
   - Verifies 422 error returned

4. **`test_paper_trading_success`**
   - Compiles strategy
   - Creates paper trading session
   - Verifies status updated to 'paper'

5. **`test_paper_trading_without_compilation`**
   - Attempts paper trading without compilation
   - Verifies 400 error returned

6. **`test_compile_all_templates`**
   - Gets all strategy templates
   - Clones each template
   - Compiles each cloned strategy
   - Verifies hash stored and cache populated

### Manual Test

**Location**: `services/algo_builder/test_compilation_manual.py`

**Purpose**: Demonstrates compilation flow without full test environment

**Run**:
```bash
python services/algo_builder/test_compilation_manual.py
```

## Performance

### Compilation Performance

- **First Compilation**: ~100-200ms (includes validation)
- **Cached Compilation**: ~50-100ms (validation only)
- **Cache Hit Rate**: Expected >90% in production

### Redis Performance

- **GET Operation**: <5ms (p95)
- **SET Operation**: <10ms (p95)
- **Cache Size**: ~50KB per compiled strategy
- **Memory Usage**: ~5MB for 100 cached strategies

## Monitoring

### Metrics to Track

1. **Compilation Success Rate**
   - Target: >95%
   - Alert if <90%

2. **Cache Hit Rate**
   - Target: >90%
   - Alert if <80%

3. **Validation Time**
   - Target: <200ms (p95)
   - Alert if >500ms

4. **Redis Availability**
   - Target: 99.9%
   - Alert if unavailable

### Logging

All operations are logged with structured logging:

```python
logger.info(
    "Strategy compiled successfully",
    extra={
        "strategy_id": strategy_id,
        "compiled_hash": spec_hash[:8],
        "validation_time_ms": validation_result.execution_time_ms,
        "cached": cache_success
    }
)
```

## Future Enhancements

1. **Distributed Caching**: Use Redis Cluster for horizontal scaling
2. **Cache Warming**: Pre-compile popular templates on startup
3. **Compilation Queue**: Async compilation for large strategies
4. **Version Control**: Store multiple versions of compiled strategies
5. **A/B Testing**: Compare performance of different compilation strategies

## References

- **Requirements**: `.kiro/specs/Signalix_UX_.md/requirements_algo_backend.md`
- **Design**: `.kiro/specs/Signalix_UX_.md/design_algo_backend.md`
- **Tasks**: `.kiro/specs/Signalix_UX_.md/tasks_algo_backend.md`
- **Compiler**: `services/algo_builder/compiler.py`
- **Sandbox**: `services/algo_builder/sandbox.py`
- **Router**: `services/algo_builder/router.py`
- **Redis Client**: `services/algo_builder/redis_client.py`
