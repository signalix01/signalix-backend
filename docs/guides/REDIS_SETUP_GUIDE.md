# 🔧 Redis Setup Guide for Windows

## Why Redis is Needed

Redis is used for:
- **OTP Storage**: Email verification codes (10-minute expiry)
- **Password Reset Tokens**: Temporary tokens for password reset (1-hour expiry)
- **Session Management**: Rate limiting and caching
- **Real-time Features**: WebSocket pub/sub for live updates

---

## Option 1: Install Redis on Windows (Recommended for Development)

### Step 1: Download Redis for Windows

Redis doesn't officially support Windows, but there are two options:

#### Option A: Using Memurai (Redis-compatible, Windows-native)

1. **Download Memurai** (Free for development):
   - Visit: https://www.memurai.com/get-memurai
   - Download Memurai Developer Edition (Free)
   - Run the installer

2. **Install Memurai**:
   - Follow the installation wizard
   - Default port: 6379
   - Service will start automatically

3. **Verify Installation**:
   ```powershell
   # Test connection
   memurai-cli ping
   # Should return: PONG
   ```

#### Option B: Using WSL2 (Windows Subsystem for Linux)

1. **Install WSL2** (if not already installed):
   ```powershell
   # Run as Administrator
   wsl --install
   # Restart your computer
   ```

2. **Install Redis in WSL2**:
   ```bash
   # Open WSL2 terminal
   wsl
   
   # Update packages
   sudo apt update
   
   # Install Redis
   sudo apt install redis-server -y
   
   # Start Redis
   sudo service redis-server start
   
   # Verify
   redis-cli ping
   # Should return: PONG
   ```

3. **Make Redis accessible from Windows**:
   ```bash
   # Edit Redis config
   sudo nano /etc/redis/redis.conf
   
   # Find and change:
   bind 127.0.0.1 ::1
   # To:
   bind 0.0.0.0
   
   # Restart Redis
   sudo service redis-server restart
   ```

#### Option C: Using Docker (If you have Docker Desktop)

1. **Install Docker Desktop**:
   - Download from: https://www.docker.com/products/docker-desktop
   - Install and start Docker Desktop

2. **Run Redis Container**:
   ```powershell
   # Pull and run Redis
   docker run -d --name redis-signalixai -p 6379:6379 redis:latest
   
   # Verify
   docker exec -it redis-signalixai redis-cli ping
   # Should return: PONG
   ```

3. **Auto-start Redis on Windows startup**:
   ```powershell
   # Set restart policy
   docker update --restart unless-stopped redis-signalixai
   ```

---

## Option 2: Use Upstash Redis (Cloud - Already Configured)

Your `.env` already has Upstash Redis configured, but it's not reachable due to network issues.

### Troubleshooting Upstash Connection

1. **Check Firewall**:
   ```powershell
   # Test connection to Upstash
   Test-NetConnection -ComputerName giving-peacock-107072.upstash.io -Port 6379
   ```

2. **Check VPN/Proxy**:
   - Disable VPN temporarily
   - Check if corporate firewall is blocking port 6379

3. **Get Fresh Credentials**:
   - Login to: https://console.upstash.com
   - Go to your Redis database
   - Copy the connection string
   - Update `.env` with new credentials

---

## Step 2: Update `.env` File

Once Redis is running locally, update your `.env`:

```bash
# For Local Redis (Memurai/WSL2/Docker)
REDIS_URL=redis://localhost:6379
REDIS_MAX_CONNECTIONS=50

# OR for Upstash (if you fix the connection)
REDIS_URL=redis://default:YOUR_PASSWORD@giving-peacock-107072.upstash.io:6379
REDIS_MAX_CONNECTIONS=50
```

---

## Step 3: Test Redis Connection

Create a test script to verify Redis is working:

```python
# test_redis.py
import redis.asyncio as redis
import asyncio

async def test_redis():
    try:
        # Connect to Redis
        client = redis.from_url("redis://localhost:6379", decode_responses=True)
        
        # Test ping
        response = await client.ping()
        print(f"✅ Redis PING: {response}")
        
        # Test set/get
        await client.set("test_key", "Hello Redis!")
        value = await client.get("test_key")
        print(f"✅ Redis GET: {value}")
        
        # Test expiry
        await client.setex("temp_key", 5, "Expires in 5 seconds")
        print(f"✅ Redis SETEX: Success")
        
        await client.close()
        print("\n🎉 Redis is working correctly!")
        
    except Exception as e:
        print(f"❌ Redis Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_redis())
```

Run the test:
```powershell
cd signalixai-backend
python test_redis.py
```

---

## Step 4: Restart Auth Service

Once Redis is running:

```powershell
cd signalixai-backend

# Stop current service (if running)
# Press Ctrl+C in the terminal

# Start Auth Service
python services/auth-service/main.py
```

You should see:
```
✅ Redis connected successfully
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Step 5: Test Registration with OTP

Now the full flow will work:

1. **Register** → Sends OTP to email (or stores in Redis)
2. **Verify Email** → Checks OTP from Redis
3. **Login** → Returns JWT tokens

---

## Quick Commands Reference

### Memurai (Windows)
```powershell
# Start service
net start Memurai

# Stop service
net stop Memurai

# Test connection
memurai-cli ping

# Monitor commands
memurai-cli monitor
```

### WSL2 Redis
```bash
# Start Redis
sudo service redis-server start

# Stop Redis
sudo service redis-server stop

# Check status
sudo service redis-server status

# Test connection
redis-cli ping

# Monitor commands
redis-cli monitor
```

### Docker Redis
```powershell
# Start container
docker start redis-signalixai

# Stop container
docker stop redis-signalixai

# View logs
docker logs redis-signalixai

# Test connection
docker exec -it redis-signalixai redis-cli ping

# Monitor commands
docker exec -it redis-signalixai redis-cli monitor
```

---

## Troubleshooting

### Issue: "Connection refused"
```powershell
# Check if Redis is running
# For Memurai:
net start Memurai

# For WSL2:
wsl sudo service redis-server start

# For Docker:
docker start redis-signalixai
```

### Issue: "Port 6379 already in use"
```powershell
# Find what's using port 6379
netstat -ano | findstr :6379

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Issue: Auth Service still says "Redis not available"
1. Make sure Redis is running
2. Update `.env` with correct `REDIS_URL`
3. Restart Auth Service
4. Check logs for connection errors

---

## Email Configuration (Optional)

To actually send OTP emails, you need to configure SendGrid:

1. **Sign up for SendGrid**:
   - Visit: https://sendgrid.com
   - Create free account (100 emails/day free)

2. **Get API Key**:
   - Go to Settings → API Keys
   - Create new API key
   - Copy the key

3. **Update `.env`**:
   ```bash
   SENDGRID_API_KEY=SG.your-api-key-here
   ```

4. **Verify sender email**:
   - Go to Settings → Sender Authentication
   - Verify your email address

Without SendGrid, OTPs are stored in Redis but not emailed. You can:
- Check Redis directly: `redis-cli GET "otp:email:user@example.com"`
- Use development mode with OTP: `000000`

---

## Summary

**Recommended Setup for Development:**

1. ✅ Install **Memurai** (easiest for Windows)
2. ✅ Update `.env` to use `redis://localhost:6379`
3. ✅ Restart Auth Service
4. ✅ Test registration flow

**For Production:**
- Use **Upstash Redis** (already configured)
- Fix network/firewall issues
- Or use **Railway Redis** add-on

---

## Current Status

- ❌ Upstash Redis: Not reachable (network/firewall issue)
- ⚠️ Local Redis: Not installed yet
- ✅ Auth Service: Running with Redis disabled (auto-verify mode)

**Next Steps:**
1. Install Redis locally (Memurai recommended)
2. Update `.env` with `redis://localhost:6379`
3. Restart Auth Service
4. Test full registration flow with OTP

---

Generated: 2026-04-28
