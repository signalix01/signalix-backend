"""
Test Redis Connection
"""
import redis.asyncio as redis
import asyncio

async def test_redis():
    """Test Redis connection and basic operations"""
    
    print("=" * 80)
    print("Testing Redis Connection")
    print("=" * 80)
    print()
    
    # Try localhost first
    redis_url = "redis://localhost:6379"
    print(f"Connecting to: {redis_url}")
    print()
    
    try:
        # Connect to Redis
        client = redis.from_url(redis_url, decode_responses=True)
        
        # Test 1: Ping
        print("Test 1: PING")
        response = await client.ping()
        print(f"✅ Response: {response}")
        print()
        
        # Test 2: Set/Get
        print("Test 2: SET/GET")
        await client.set("test_key", "Hello Redis!")
        value = await client.get("test_key")
        print(f"✅ Stored: 'Hello Redis!'")
        print(f"✅ Retrieved: '{value}'")
        print()
        
        # Test 3: Expiry (SETEX)
        print("Test 3: SETEX (with expiry)")
        await client.setex("temp_key", 10, "Expires in 10 seconds")
        ttl = await client.ttl("temp_key")
        print(f"✅ Key created with TTL: {ttl} seconds")
        print()
        
        # Test 4: Delete
        print("Test 4: DELETE")
        await client.delete("test_key", "temp_key")
        print(f"✅ Keys deleted")
        print()
        
        # Test 5: OTP simulation
        print("Test 5: OTP Simulation (like auth service)")
        test_email = "test@example.com"
        test_otp = "123456"
        await client.setex(f"otp:email:{test_email}", 600, test_otp)
        stored_otp = await client.get(f"otp:email:{test_email}")
        print(f"✅ OTP stored for {test_email}: {stored_otp}")
        await client.delete(f"otp:email:{test_email}")
        print(f"✅ OTP deleted")
        print()
        
        await client.close()
        
        print("=" * 80)
        print("🎉 ALL TESTS PASSED - Redis is working correctly!")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Update .env with: REDIS_URL=redis://localhost:6379")
        print("2. Restart Auth Service")
        print("3. Test registration with OTP")
        
    except redis.ConnectionError as e:
        print(f"❌ Connection Error: {e}")
        print()
        print("Redis is not running or not accessible.")
        print()
        print("Solutions:")
        print("1. Install Redis locally (see REDIS_SETUP_GUIDE.md)")
        print("2. Start Redis service:")
        print("   - Memurai: net start Memurai")
        print("   - WSL2: wsl sudo service redis-server start")
        print("   - Docker: docker start redis-signalixai")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Check REDIS_SETUP_GUIDE.md for troubleshooting steps")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_redis())
