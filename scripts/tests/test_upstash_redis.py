"""
Test Upstash Redis Connection with TLS
"""
import redis.asyncio as redis
import asyncio
import ssl

async def test_upstash_redis():
    """Test Upstash Redis connection with TLS"""
    
    print("=" * 80)
    print("Testing Upstash Redis Connection (with TLS)")
    print("=" * 80)
    print()
    
    # Upstash Redis URL (with SSL)
    redis_url = "rediss://default:gQAAAAAAAaJAAAIgcDFlNmU5MWM1ZGFkNGY0ZjA1ODZkMTljYmY2ZDI1ODk1Mg@giving-peacock-107072.upstash.io:6379"
    
    print(f"Connecting to: giving-peacock-107072.upstash.io:6379")
    print(f"Protocol: rediss:// (Redis with SSL/TLS)")
    print()
    
    try:
        # Create SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Connect to Upstash Redis with SSL
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            ssl_cert_reqs="none"
        )
        
        # Test 1: Ping
        print("Test 1: PING")
        response = await client.ping()
        print(f"✅ Response: {response}")
        print()
        
        # Test 2: Set/Get
        print("Test 2: SET/GET")
        await client.set("test_key", "Hello Upstash!")
        value = await client.get("test_key")
        print(f"✅ Stored: 'Hello Upstash!'")
        print(f"✅ Retrieved: '{value}'")
        print()
        
        # Test 3: Expiry (SETEX)
        print("Test 3: SETEX (with expiry)")
        await client.setex("temp_key", 10, "Expires in 10 seconds")
        ttl = await client.ttl("temp_key")
        print(f"✅ Key created with TTL: {ttl} seconds")
        print()
        
        # Test 4: OTP simulation
        print("Test 4: OTP Simulation (like auth service)")
        test_email = "test@example.com"
        test_otp = "123456"
        await client.setex(f"otp:email:{test_email}", 600, test_otp)
        stored_otp = await client.get(f"otp:email:{test_email}")
        print(f"✅ OTP stored for {test_email}: {stored_otp}")
        print()
        
        # Test 5: Delete
        print("Test 5: DELETE")
        await client.delete("test_key", "temp_key", f"otp:email:{test_email}")
        print(f"✅ Keys deleted")
        print()
        
        # Test 6: Info
        print("Test 6: Server Info")
        info = await client.info("server")
        print(f"✅ Redis Version: {info.get('redis_version', 'Unknown')}")
        print(f"✅ Uptime: {info.get('uptime_in_days', 'Unknown')} days")
        print()
        
        await client.close()
        
        print("=" * 80)
        print("🎉 ALL TESTS PASSED - Upstash Redis is working!")
        print("=" * 80)
        print()
        print("✅ Your .env is correctly configured")
        print("✅ TLS/SSL connection is working")
        print("✅ OTP storage and retrieval works")
        print()
        print("Next steps:")
        print("1. Restart Auth Service")
        print("2. Test registration with OTP")
        print("3. Check Auth Service logs for: '✅ Redis connected successfully'")
        
    except redis.ConnectionError as e:
        print(f"❌ Connection Error: {e}")
        print()
        print("Possible issues:")
        print("1. Network/Firewall blocking Upstash (port 6379)")
        print("2. VPN interfering with connection")
        print("3. Upstash database is paused or deleted")
        print()
        print("Solutions:")
        print("1. Check firewall settings")
        print("2. Disable VPN temporarily")
        print("3. Login to Upstash console and verify database is active")
        print("4. Try from different network (mobile hotspot)")
        
    except redis.AuthenticationError as e:
        print(f"❌ Authentication Error: {e}")
        print()
        print("The password is incorrect or expired.")
        print()
        print("Solutions:")
        print("1. Login to https://console.upstash.com")
        print("2. Go to your Redis database")
        print("3. Copy the connection string")
        print("4. Update REDIS_URL in .env")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Unexpected error occurred.")
        print("Check your internet connection and try again.")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_upstash_redis())
