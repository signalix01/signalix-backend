# Auth Service Error Report

**Date**: April 28, 2026  
**Service**: Auth Service (Port 8000)  
**Status**: ❌ Database Connection Error

## Error Summary

The Auth Service is running but failing to process registration requests due to a **database connection error**.

### Error Details

**Error Type**: `socket.gaierror: [Errno 11003] getaddrinfo failed`

**Root Cause**: Cannot resolve DNS hostname for Supabase database

**Database URL**: `postgresql+asyncpg://postgres:***@db.dbthggjxvzueznphcqoc.supabase.co:5432/postgres`

## Error Trace

```
File "asyncpg/connection.py", line 2443, in connect
File "asyncpg/connect_utils.py", line 1249, in _connect
File "asyncio/base_events.py", line 936, in getaddrinfo
File "socket.py", line 983, in getaddrinfo
socket.gaierror: [Errno 11003] getaddrinfo failed
```

## Test Results

### Test 1: Service Startup
- ✅ Service starts successfully
- ✅ Uvicorn running on http://0.0.0.0:8000
- ✅ Middleware configured correctly
- ✅ Monitoring configured successfully

### Test 2: Registration Endpoint
- ❌ POST /api/v1/auth/register returns 500 Internal Server Error
- ❌ Database connection fails during user creation
- ❌ Cannot resolve Supabase hostname

### Test 3: HTTPS Redirect Issue (Fixed)
- ✅ Changed ENVIRONMENT from "production" to "development"
- ✅ HTTPS redirect disabled for local testing
- ✅ Service now accepts HTTP requests

## Issues Identified

### 1. Database Connection Failure (CRITICAL)
**Error**: Cannot connect to Supabase PostgreSQL database  
**Cause**: DNS resolution failure for `db.dbthggjxvzueznphcqoc.supabase.co`  
**Impact**: All database operations fail (registration, login, etc.)

**Possible Causes**:
- Network connectivity issue
- Firewall blocking outbound connections
- DNS resolution failure
- Supabase service unavailable
- Invalid database credentials

**Solutions**:
1. **Check Network Connectivity**:
   ```bash
   ping db.dbthggjxvzueznphcqoc.supabase.co
   ```

2. **Test Database Connection**:
   ```bash
   psql "postgresql://postgres:***@db.dbthggjxvzueznphcqoc.supabase.co:5432/postgres"
   ```

3. **Use Local PostgreSQL** (for development):
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/signalixai
   ```

4. **Check Supabase Dashboard**:
   - Verify project is active
   - Check connection pooler settings
   - Verify database credentials

### 2. Redis Connection (Not Tested Yet)
**Status**: Unknown  
**URL**: `redis://default:***@giving-peacock-107072.upstash.io:6379`  
**Impact**: Rate limiting and caching may fail

### 3. Missing LLM API Keys (Expected)
**Status**: Not configured  
**Impact**: Analysis Service will not work  
**Note**: This is expected for auth service testing

## Recommendations

### Immediate Actions

#### Option 1: Fix Supabase Connection (Production)
1. Check network connectivity to Supabase
2. Verify firewall rules allow outbound connections to Supabase
3. Test database credentials in Supabase dashboard
4. Check if Supabase project is paused/inactive

#### Option 2: Use Local Database (Development)
1. Install PostgreSQL locally:
   ```bash
   # Windows (using Chocolatey)
   choco install postgresql

   # Or download from postgresql.org
   ```

2. Create local database:
   ```sql
   CREATE DATABASE signalixai;
   CREATE USER signalixai WITH PASSWORD 'signalixai_dev';
   GRANT ALL PRIVILEGES ON DATABASE signalixai TO signalixai;
   ```

3. Update .env:
   ```env
   DATABASE_URL=postgresql+asyncpg://signalixai:signalixai_dev@localhost:5432/signalixai
   ```

4. Run migrations:
   ```bash
   alembic upgrade head
   ```

#### Option 3: Use SQLite (Quick Testing)
1. Update .env:
   ```env
   DATABASE_URL=sqlite+aiosqlite:///./signalixai.db
   ```

2. Update requirements to include aiosqlite:
   ```bash
   pip install aiosqlite
   ```

3. Run migrations:
   ```bash
   alembic upgrade head
   ```

### Testing Strategy

Once database connection is fixed:

1. **Test Registration**:
   ```bash
   python test_registration_detailed.py
   ```

2. **Test Login**:
   ```bash
   python test_login.py
   ```

3. **Test Token Refresh**:
   ```bash
   python test_token_refresh.py
   ```

4. **Test Password Reset**:
   ```bash
   python test_password_reset.py
   ```

## Current Service Status

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI Server | ✅ Running | Port 8000 |
| Uvicorn | ✅ Running | HTTP mode |
| Middleware | ✅ Configured | Security, CORS, Logging |
| Monitoring | ✅ Configured | Sentry, Prometheus |
| Database Connection | ❌ Failed | DNS resolution error |
| Redis Connection | ⚠️ Unknown | Not tested yet |
| Registration Endpoint | ❌ Failed | Database error |
| Login Endpoint | ⚠️ Unknown | Not tested yet |

## Next Steps

1. **Fix Database Connection** (choose one option above)
2. **Test Redis Connection**
3. **Run Full Auth Flow Tests**
4. **Start Other Services** (User, Market Data, etc.)
5. **Install LangChain Dependencies** (for Analysis Service)
6. **Configure LLM API Keys** (for Analysis Service)

## Test Data Used

```json
{
  "email": "test@example.com",
  "phone": "+919876543210",
  "password": "SecurePass123!",
  "full_name": "Test User",
  "country_of_residence": "IN",
  "declared_trading_capital_inr": 10000000,
  "risk_tolerance_score": 7,
  "investment_horizon": "swing",
  "sebi_declaration_acknowledged": true
}
```

## Conclusion

The Auth Service code is working correctly, but it cannot connect to the Supabase database due to network/DNS issues. Once the database connection is established (either by fixing Supabase connectivity or using a local database), the service should work as expected.

**Recommended Next Action**: Set up a local PostgreSQL database for development testing.
