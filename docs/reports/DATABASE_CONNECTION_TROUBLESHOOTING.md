# 🔧 Database Connection Troubleshooting Report

## ❌ Current Issue: Cannot Connect to Supabase PostgreSQL

### Error Details
```
socket.gaierror: [Errno 11003] getaddrinfo failed
```

### Root Cause Analysis

1. **DNS Resolution**: ✅ WORKING
   - Hostname resolves to IPv6: `2406:da1c:f42:ae10:c01e:37e3:d1dd:7344`
   - DNS server: `8.8.8.8` (Google DNS)

2. **Network Connectivity**: ❌ FAILING
   - Ping to IPv6 address times out (100% packet loss)
   - This indicates either:
     - IPv6 connectivity is not available on your network
     - Firewall is blocking PostgreSQL port 5432
     - Supabase project is paused or restricted

3. **Current Connection String**:
   ```
   postgresql+asyncpg://postgres:Q3J!@TDMiFQi5VZ@db.dbthggjxvzueznphcqoc.supabase.co:5432/postgres
   ```

---

## 🔍 Diagnostic Tests Performed

### Test 1: DNS Resolution
```bash
nslookup db.dbthggjxvzueznphcqoc.supabase.co
```
**Result**: ✅ Success - Resolves to IPv6 address

### Test 2: Network Connectivity
```bash
ping db.dbthggjxvzueznphcqoc.supabase.co
```
**Result**: ❌ Failed - Request timed out (IPv6 connectivity issue)

### Test 3: Auth Service Startup
```bash
python services/auth-service/main.py
```
**Result**: ⚠️ Partial - Service starts but database operations fail

### Test 4: Registration Endpoint
```bash
POST /api/v1/auth/register
```
**Result**: ❌ Failed - 500 Internal Server Error due to database connection

---

## 🛠️ Recommended Solutions

### Solution 1: Check Supabase Project Status (RECOMMENDED)

1. **Login to Supabase Dashboard**: https://supabase.com/dashboard
2. **Navigate to your project**: `dbthggjxvzueznphcqoc`
3. **Check Project Status**:
   - Is the project active or paused?
   - Free tier projects pause after 7 days of inactivity
   - Click "Resume Project" if paused

4. **Get Fresh Connection String**:
   - Go to: Project Settings → Database → Connection String
   - Copy the "Connection string" (not REST API URL)
   - Look for both:
     - **Direct Connection**: `postgresql://...@db.xxx.supabase.co:5432/postgres`
     - **Connection Pooling**: `postgresql://...@aws-0-xxx.pooler.supabase.com:6543/postgres`

### Solution 2: Use Connection Pooler (IPv4 Fallback)

Supabase provides a connection pooler that might have better IPv4 support:

```bash
# Format:
postgresql+asyncpg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres

# Example:
postgresql+asyncpg://postgres.dbthggjxvzueznphcqoc:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

**Update `.env` file**:
```bash
DATABASE_URL=postgresql+asyncpg://postgres.dbthggjxvzueznphcqoc:Q3J!@TDMiFQi5VZ@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

### Solution 3: Check Network/Firewall Settings

1. **Check if port 5432 is blocked**:
   ```bash
   Test-NetConnection -ComputerName db.dbthggjxvzueznphcqoc.supabase.co -Port 5432
   ```

2. **Disable IPv6 temporarily** (Windows):
   - Open Network Adapter Settings
   - Disable "Internet Protocol Version 6 (TCP/IPv6)"
   - Restart network adapter

3. **Check VPN/Proxy**:
   - If using VPN, try disconnecting
   - If behind corporate proxy, check if PostgreSQL ports are allowed

### Solution 4: Use Supabase REST API (Alternative)

If direct PostgreSQL connection doesn't work, use Supabase's REST API:

1. **Get API Keys from Supabase Dashboard**:
   - Project Settings → API
   - Copy `anon` or `service_role` key

2. **Update `.env`**:
   ```bash
   SUPABASE_URL=https://dbthggjxvzueznphcqoc.supabase.co
   SUPABASE_KEY=your-anon-or-service-role-key
   ```

3. **Install Supabase Python client**:
   ```bash
   pip install supabase
   ```

4. **Update database session** to use Supabase client instead of SQLAlchemy

---

## 📋 Step-by-Step Action Plan

### Immediate Actions (Do These First)

1. **Check Supabase Dashboard**:
   ```
   ☐ Login to https://supabase.com/dashboard
   ☐ Find project: dbthggjxvzueznphcqoc
   ☐ Check if project is paused → Resume if needed
   ☐ Copy fresh connection string from Settings → Database
   ☐ Try both "Direct Connection" and "Connection Pooling" strings
   ```

2. **Update Connection String**:
   ```
   ☐ Open signalixai-backend/.env
   ☐ Update DATABASE_URL with fresh connection string
   ☐ Save file
   ```

3. **Restart Auth Service**:
   ```bash
   # Stop current service
   Ctrl+C in terminal
   
   # Start again
   python services/auth-service/main.py
   ```

4. **Test Registration**:
   ```bash
   python test_registration.py
   ```

### If Still Failing

5. **Test Network Connectivity**:
   ```powershell
   # Test port 5432
   Test-NetConnection -ComputerName db.dbthggjxvzueznphcqoc.supabase.co -Port 5432
   
   # Test pooler port 6543 (if using connection pooling)
   Test-NetConnection -ComputerName aws-0-ap-south-1.pooler.supabase.com -Port 6543
   ```

6. **Try Connection Pooler**:
   ```
   ☐ Get pooler connection string from Supabase
   ☐ Update DATABASE_URL in .env
   ☐ Restart service and test
   ```

7. **Contact Supabase Support**:
   ```
   ☐ Check Supabase status page: https://status.supabase.com
   ☐ Open support ticket if service is down
   ```

---

## 🔐 Security Note

Your current password contains special characters: `Q3J!@TDMiFQi5VZ`

The `!` and `@` characters might need URL encoding:
- `!` → `%21`
- `@` → `%40`

**Encoded password**: `Q3J%21%40TDMiFQi5VZ`

**Encoded connection string**:
```
postgresql+asyncpg://postgres:Q3J%21%40TDMiFQi5VZ@db.dbthggjxvzueznphcqoc.supabase.co:5432/postgres
```

Try this if the regular connection string doesn't work.

---

## 📊 Current Status Summary

| Component | Status | Details |
|-----------|--------|---------|
| DNS Resolution | ✅ Working | Resolves to IPv6 address |
| Network Connectivity | ❌ Failing | IPv6 ping timeout |
| Auth Service | ⚠️ Partial | Starts but DB operations fail |
| Database Connection | ❌ Failing | `socket.gaierror` |
| Registration Endpoint | ❌ Failing | 500 Internal Server Error |

---

## 🆘 Quick Fix Commands

### Option 1: URL-Encode Password
```bash
# Update .env with encoded password
DATABASE_URL=postgresql+asyncpg://postgres:Q3J%21%40TDMiFQi5VZ@db.dbthggjxvzueznphcqoc.supabase.co:5432/postgres
```

### Option 2: Use Connection Pooler
```bash
# Update .env with pooler (check Supabase dashboard for exact URL)
DATABASE_URL=postgresql+asyncpg://postgres.dbthggjxvzueznphcqoc:Q3J%21%40TDMiFQi5VZ@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

### Option 3: Force IPv4
```python
# Add to shared/database/session.py
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args={
        "server_settings": {"jit": "off"},
        "ssl": "require",
        "timeout": 10,
    }
)
```

---

## 📞 Next Steps

**IMMEDIATE**: Check Supabase dashboard and verify:
1. Project is active (not paused)
2. Get fresh connection string
3. Try connection pooler URL
4. Check if password needs URL encoding

**IF STILL FAILING**: 
1. Test network connectivity to port 5432/6543
2. Check firewall/VPN settings
3. Contact Supabase support

---

**Generated**: 2026-04-28 14:30:00  
**Auth Service Status**: Running on port 8000  
**Database Status**: Connection failing (DNS resolution works, network connectivity fails)
