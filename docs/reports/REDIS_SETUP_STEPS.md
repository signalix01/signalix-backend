# 🚀 Quick Redis Setup Steps

## Current Situation
- ✅ Auth Service is running on port 8000
- ✅ Database (Supabase PostgreSQL) is connected
- ❌ Redis is not available (OTP emails won't work)
- ⚠️ System is in "auto-verify" mode (skips email verification)

---

## Quick Fix: Install Redis Locally

### Option 1: Memurai (Easiest for Windows) ⭐ RECOMMENDED

1. **Download Memurai**:
   - Go to: https://www.memurai.com/get-memurai
   - Click "Download Memurai Developer Edition" (Free)
   - Run the installer `Memurai-Developer-v4.x.x.msi`

2. **Install**:
   - Follow installation wizard
   - Keep default settings (Port 6379)
   - Service will start automatically

3. **Verify Installation**:
   ```powershell
   # Open PowerShell and run:
   memurai-cli ping
   ```
   Should return: `PONG`

4. **Update `.env`**:
   Open `signalixai-backend/.env` and change:
   ```bash
   # FROM:
   REDIS_URL=redis://localhost:6379
   
   # TO: (keep it the same, just make sure it says localhost)
   REDIS_URL=redis://localhost:6379
   ```

5. **Test Redis**:
   ```powershell
   cd signalixai-backend
   python test_redis.py
   ```
   Should show: `🎉 ALL TESTS PASSED`

6. **Restart Auth Service**:
   - Stop current service (Ctrl+C in terminal)
   - Start again:
     ```powershell
     python services/auth-service/main.py
     ```
   - Look for: `✅ Redis connected successfully`

---

### Option 2: Docker (If you have Docker Desktop)

1. **Install Docker Desktop**:
   - Download: https://www.docker.com/products/docker-desktop
   - Install and start Docker Desktop

2. **Run Redis**:
   ```powershell
   docker run -d --name redis-signalixai -p 6379:6379 redis:latest
   ```

3. **Verify**:
   ```powershell
   docker exec -it redis-signalixai redis-cli ping
   ```
   Should return: `PONG`

4. **Auto-start on Windows boot**:
   ```powershell
   docker update --restart unless-stopped redis-signalixai
   ```

5. **Continue with steps 4-6 from Option 1 above**

---

### Option 3: WSL2 (If you have Windows Subsystem for Linux)

1. **Open WSL2 terminal**:
   ```powershell
   wsl
   ```

2. **Install Redis**:
   ```bash
   sudo apt update
   sudo apt install redis-server -y
   ```

3. **Start Redis**:
   ```bash
   sudo service redis-server start
   ```

4. **Verify**:
   ```bash
   redis-cli ping
   ```
   Should return: `PONG`

5. **Continue with steps 4-6 from Option 1 above**

---

## After Redis is Running

### Test Full Registration Flow

1. **Register a new user** (via frontend or API):
   ```json
   POST http://localhost:8000/api/v1/auth/register
   {
     "email": "newuser@example.com",
     "password": "SecurePass123!"
   }
   ```

2. **Check Redis for OTP**:
   ```powershell
   # Memurai:
   memurai-cli GET "otp:email:newuser@example.com"
   
   # Docker:
   docker exec -it redis-signalixai redis-cli GET "otp:email:newuser@example.com"
   
   # WSL2:
   wsl redis-cli GET "otp:email:newuser@example.com"
   ```
   Should return a 6-digit OTP like: `"123456"`

3. **Verify email with OTP**:
   ```json
   POST http://localhost:8000/api/v1/auth/verify-email
   {
     "email": "newuser@example.com",
     "otp": "123456"
   }
   ```

---

## Troubleshooting

### Redis not starting?

**Memurai:**
```powershell
# Start service
net start Memurai

# Check status
sc query Memurai
```

**Docker:**
```powershell
# Check if container is running
docker ps

# Start if stopped
docker start redis-signalixai

# View logs
docker logs redis-signalixai
```

**WSL2:**
```bash
# Check status
sudo service redis-server status

# Start if stopped
sudo service redis-server start
```

### Port 6379 already in use?

```powershell
# Find what's using the port
netstat -ano | findstr :6379

# Kill the process (replace <PID> with actual number)
taskkill /PID <PID> /F
```

### Auth Service still says "Redis not available"?

1. Make sure Redis is running (test with `ping`)
2. Check `.env` has correct `REDIS_URL`
3. Restart Auth Service completely
4. Check Auth Service logs for connection errors

---

## Email Configuration (Optional)

To actually send OTP emails (not just store in Redis):

1. **Sign up for SendGrid**:
   - Visit: https://sendgrid.com
   - Create free account (100 emails/day)

2. **Get API Key**:
   - Settings → API Keys → Create API Key
   - Copy the key

3. **Update `.env`**:
   ```bash
   SENDGRID_API_KEY=SG.your-actual-api-key-here
   ```

4. **Verify sender email** in SendGrid dashboard

5. **Restart Auth Service**

Now OTPs will be sent to actual email addresses!

---

## Summary

**What you need to do:**

1. ✅ Install Memurai (or Docker/WSL2 Redis)
2. ✅ Run `python test_redis.py` to verify
3. ✅ Restart Auth Service
4. ✅ Test registration flow

**Expected result:**
- Registration creates user and stores OTP in Redis
- OTP can be retrieved from Redis
- Email verification works with OTP
- Full authentication flow is functional

---

## Current Files

- `REDIS_SETUP_GUIDE.md` - Detailed guide with all options
- `REDIS_SETUP_STEPS.md` - This file (quick steps)
- `test_redis.py` - Test script to verify Redis connection
- `.env` - Configuration file (update REDIS_URL here)

---

**Need help?** Check the detailed guide: `REDIS_SETUP_GUIDE.md`
