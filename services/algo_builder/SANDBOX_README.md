# Sandboxed Execution Environment

## Overview

The sandbox module provides secure execution of compiled trading strategies with comprehensive security restrictions to prevent malicious code from accessing system resources.

**Requirements Implemented:** 3.3, 3.4, 3.5, 3.6

## Security Features

### 1. Process Isolation
- All strategy code runs in a separate subprocess
- Parent process is protected from crashes in strategy code
- Clean separation of execution contexts

### 2. Memory Limits
- **Limit:** 512MB RAM per strategy execution
- **Implementation:** `resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))`
- **Platform:** Linux only (gracefully skipped on Windows)

### 3. Time Limits
- **Timeout:** 30 seconds maximum execution time
- **Implementation:** `subprocess.run()` with `timeout=30`
- **Behavior:** Process is killed if timeout is exceeded

### 4. Syscall Filtering (Linux Only)
- **Library:** libseccomp via ctypes
- **Allowed syscalls:**
  - read, write, mmap, munmap
  - exit, exit_group, rt_sigreturn
  - brk, mprotect, close, fstat, lseek
  - getpid, getuid, getgid, geteuid, getegid
  - arch_prctl, futex, set_tid_address, set_robust_list
  - prlimit64, getrandom, rseq
- **Blocked:** All network syscalls (socket, connect, etc.)
- **Fallback:** Gracefully continues without syscall filtering on Windows or if libseccomp is unavailable

### 5. Filesystem Restrictions
- **Read access:** Limited to temporary directory with input data
- **Write access:** Limited to temporary directory for output
- **No access to:** User files, system files, other strategies

### 6. Network Restrictions
- **Implementation:** Syscall filtering blocks network syscalls on Linux
- **Fallback:** On Windows, network access may be available but strategies should not rely on it
- **Testing:** Network access attempts are tested to ensure they fail or are handled gracefully

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Parent Process                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SandboxRunner                            │  │
│  │  • Prepares execution environment                     │  │
│  │  • Serializes inputs (code, data, capital)            │  │
│  │  • Launches subprocess                                │  │
│  │  • Monitors timeout                                   │  │
│  │  • Deserializes outputs                               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ subprocess.run()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Sandboxed Subprocess                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Execution Script (exec_script.py)             │  │
│  │                                                        │  │
│  │  1. Apply resource limits (memory)                    │  │
│  │  2. Apply syscall filtering (Linux)                   │  │
│  │  3. Load serialized inputs                            │  │
│  │  4. Execute strategy code                             │  │
│  │  5. Instantiate strategy class                        │  │
│  │  6. Serialize output                                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  Restrictions:                                               │
│  • Memory: 512MB max                                         │
│  • Time: 30 seconds max                                      │
│  • Network: Blocked (Linux)                                  │
│  • Filesystem: Temp dir only                                 │
└─────────────────────────────────────────────────────────────┘
```

## API Reference

### SandboxRunner

Main class for executing strategies in a sandbox.

```python
from services.algo_builder.sandbox import SandboxRunner

runner = SandboxRunner()
```

#### Methods

##### `execute(compiled_code: str, data: pd.DataFrame, capital: float) -> Any`

Execute compiled strategy code in a sandboxed subprocess.

**Parameters:**
- `compiled_code` (str): Python class string from StrategyCompiler
- `data` (pd.DataFrame): OHLCV DataFrame with indicators
- `capital` (float): Starting capital

**Returns:**
- Strategy instance after execution

**Raises:**
- `TimeoutError`: If execution exceeds 30 seconds
- `MemoryError`: If execution exceeds memory limit
- `RuntimeError`: If execution fails for other reasons

**Example:**
```python
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.sandbox import SandboxRunner
import pandas as pd

# Compile strategy
compiler = StrategyCompiler()
compiled_code = compiler.compile(strategy_spec)

# Create test data
data = pd.DataFrame({
    'open': [100, 101, 102],
    'high': [102, 103, 104],
    'low': [99, 100, 101],
    'close': [101, 102, 103],
    'volume': [1000, 1100, 1200]
})

# Execute in sandbox
runner = SandboxRunner()
strategy = runner.execute(compiled_code, data, 100000.0)
```

##### `validate(compiled_code: str) -> ValidationResult`

Validate compiled strategy code by running a 100-bar smoke test.

**Parameters:**
- `compiled_code` (str): Python class string from StrategyCompiler

**Returns:**
- `ValidationResult` with success status and details

**Example:**
```python
result = runner.validate(compiled_code)

if result.success:
    print(f"✓ Strategy validated in {result.execution_time_ms:.2f}ms")
else:
    print(f"✗ Validation failed: {result.error}")
```

### ValidationResult

Dataclass representing validation results.

**Fields:**
- `success` (bool): Whether validation succeeded
- `message` (str): Human-readable message
- `error` (Optional[str]): Error message if validation failed
- `execution_time_ms` (Optional[float]): Execution time in milliseconds

**Methods:**
- `to_dict() -> dict`: Convert to dictionary for JSON serialization

### Convenience Functions

##### `validate_strategy(compiled_code: str) -> ValidationResult`

Convenience function for validating a compiled strategy.

```python
from services.algo_builder.sandbox import validate_strategy

result = validate_strategy(compiled_code)
```

## Testing

### Running Tests

```bash
# Run all sandbox tests
python services/algo_builder/run_sandbox_tests.py

# Or use pytest directly
pytest services/algo_builder/test_sandbox.py -v
```

### Test Coverage

The test suite verifies:

1. **Successful Validation**
   - Simple strategies validate correctly
   - Complex multi-condition strategies validate correctly
   - All required methods are callable

2. **Timeout Enforcement**
   - Infinite loops are killed after 30 seconds
   - Timeout error is returned to caller

3. **Memory Limit Enforcement** (Linux only)
   - Excessive memory allocation is blocked
   - Memory errors are handled gracefully

4. **Network Access Blocking**
   - Network access attempts fail or are handled gracefully
   - Strategy execution continues despite blocked network

5. **Error Handling**
   - Missing methods are detected
   - Syntax errors are caught and reported
   - Runtime errors are caught and reported

6. **Integration with Compiler**
   - Compiled strategies execute correctly
   - Turtle-style strategies validate
   - Complex multi-indicator strategies validate

### Test Results

Expected test results:
```
test_sandbox.py::TestSandboxRunner::test_validate_simple_strategy_success PASSED
test_sandbox.py::TestSandboxRunner::test_validate_timeout_kills_correctly PASSED
test_sandbox.py::TestSandboxRunner::test_validate_network_access_blocked PASSED
test_sandbox.py::TestSandboxRunner::test_validate_memory_limit_enforced PASSED (Linux only)
test_sandbox.py::TestSandboxRunner::test_validate_missing_methods PASSED
test_sandbox.py::TestSandboxRunner::test_validate_syntax_error PASSED
test_sandbox.py::TestSandboxRunner::test_execute_with_real_data PASSED
test_sandbox.py::TestSandboxRunner::test_create_test_data PASSED
test_sandbox.py::TestSandboxRunner::test_validation_result_to_dict PASSED
test_sandbox.py::TestSandboxRunner::test_convenience_function PASSED
test_sandbox.py::TestSandboxIntegration::test_compile_and_validate_turtle_strategy PASSED
test_sandbox.py::TestSandboxIntegration::test_compile_and_validate_complex_strategy PASSED
```

## Platform Compatibility

### Linux
- ✓ Full security features enabled
- ✓ Memory limits enforced
- ✓ Syscall filtering active
- ✓ Network access blocked

### Windows
- ✓ Process isolation
- ✓ Time limits enforced
- ⚠ Memory limits not enforced (resource module limitation)
- ⚠ Syscall filtering not available
- ⚠ Network access may be available

### macOS
- ✓ Process isolation
- ✓ Time limits enforced
- ⚠ Memory limits may work (untested)
- ⚠ Syscall filtering not available
- ⚠ Network access may be available

## Performance

### Validation Performance
- **Typical validation time:** 100-500ms
- **100-bar smoke test:** < 1 second
- **Overhead:** ~50-100ms for subprocess creation and serialization

### Execution Performance
- **Subprocess creation:** ~50ms
- **Data serialization:** ~10-50ms (depends on data size)
- **Strategy execution:** Varies by strategy complexity
- **Total overhead:** ~100-200ms per execution

## Security Considerations

### What is Protected

1. **Filesystem**
   - Strategy cannot read user files
   - Strategy cannot write to system directories
   - Strategy can only access temporary directory

2. **Network**
   - Strategy cannot make HTTP requests (Linux)
   - Strategy cannot open sockets (Linux)
   - Strategy cannot access external services (Linux)

3. **System Resources**
   - Strategy cannot consume excessive memory
   - Strategy cannot run indefinitely
   - Strategy cannot fork processes

4. **Other Users**
   - Strategy cannot access other users' data
   - Strategy runs in isolated process
   - Strategy cannot interfere with other strategies

### What is NOT Protected (Windows)

On Windows, the following restrictions are not enforced:
- Memory limits (resource module not available)
- Network access (syscall filtering not available)
- Filesystem access beyond temporary directory

**Recommendation:** For production deployments on Windows, consider using Docker containers with `--network=none` and `--read-only` flags as an additional security layer.

## Integration with Compiler

The sandbox is designed to work seamlessly with the StrategyCompiler:

```python
from services.algo_builder.compiler import StrategyCompiler
from services.algo_builder.sandbox import SandboxRunner

# 1. Compile strategy
compiler = StrategyCompiler()
compiled_code = compiler.compile(strategy_spec)

# 2. Validate in sandbox
runner = SandboxRunner()
result = runner.validate(compiled_code)

if result.success:
    # 3. Execute with real data
    strategy = runner.execute(compiled_code, historical_data, capital)
```

## Error Handling

### Common Errors

1. **TimeoutError**
   ```
   Strategy execution exceeded 30 second timeout
   ```
   **Cause:** Strategy has infinite loop or is too slow
   **Solution:** Optimize strategy logic or reduce data size

2. **MemoryError** (Linux only)
   ```
   Strategy execution failed: MemoryError
   ```
   **Cause:** Strategy allocates more than 512MB
   **Solution:** Reduce memory usage in strategy

3. **RuntimeError**
   ```
   Strategy execution failed: [error details]
   ```
   **Cause:** Various runtime errors in strategy code
   **Solution:** Check error details and fix strategy code

4. **ValidationResult.success = False**
   ```
   Missing required methods: compute_indicators, should_enter_long
   ```
   **Cause:** Compiled strategy is missing required methods
   **Solution:** Check compiler output and strategy spec

## Future Enhancements

Potential improvements for future versions:

1. **Docker-based Sandbox**
   - Use Docker containers for stronger isolation
   - Better cross-platform compatibility
   - Network isolation on all platforms

2. **Resource Monitoring**
   - Track CPU usage during execution
   - Monitor memory usage in real-time
   - Collect execution metrics

3. **Caching**
   - Cache validation results by code hash
   - Reuse validated strategies
   - Reduce validation overhead

4. **Enhanced Syscall Filtering**
   - More granular syscall control
   - Whitelist specific file paths
   - Allow controlled network access for data fetching

## References

- **Requirements:** `.kiro/specs/Signalix_UX_.md/requirements_algo_backend.md` (Requirement 3)
- **Design:** `.kiro/specs/Signalix_UX_.md/design_algo_backend.md` (Service 1: Algo Builder)
- **Tasks:** `.kiro/specs/Signalix_UX_.md/tasks_algo_backend.md` (Task 9)

## Support

For issues or questions about the sandbox implementation:
1. Check test results: `python run_sandbox_tests.py`
2. Review error messages in ValidationResult
3. Check platform compatibility section
4. Consult the integration examples above
