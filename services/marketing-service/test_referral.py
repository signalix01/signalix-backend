"""
Test script for referral program functionality
Run with: python test_referral.py
"""
import asyncio
import asyncpg
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
MARKETING_SERVICE_URL = os.getenv('MARKETING_SERVICE_URL', 'http://localhost:8010')
DATABASE_URL = os.getenv('DATABASE_URL')

# Test user IDs (use UUIDs from your test database)
TEST_REFERRER_USER_ID = "123e4567-e89b-12d3-a456-426614174000"
TEST_REFERRED_USER_ID = "223e4567-e89b-12d3-a456-426614174001"


async def test_generate_referral_link():
    """Test referral link generation"""
    print("\n=== Test 1: Generate Referral Link ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/generate",
            json={"user_id": TEST_REFERRER_USER_ID}
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Referral code: {data['referral_code']}")
            print(f"✓ Referral link: {data['referral_link']}")
            return data['referral_code']
        else:
            print(f"✗ Error: {response.text}")
            return None


async def test_validate_referral_code(code: str):
    """Test referral code validation"""
    print(f"\n=== Test 2: Validate Referral Code ({code}) ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/code/{code}"
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Valid: {data['valid']}")
            print(f"✓ Referrer user ID: {data['referrer_user_id']}")
        else:
            print(f"✗ Error: {response.text}")


async def test_track_referral_signup(code: str):
    """Test tracking referral signup event"""
    print(f"\n=== Test 3: Track Referral Signup ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/track",
            json={
                "referral_code": code,
                "referred_user_id": TEST_REFERRED_USER_ID,
                "event": "signup"
            }
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Success: {data['message']}")
        else:
            print(f"✗ Error: {response.text}")


async def test_track_referral_activation(code: str):
    """Test tracking referral activation event"""
    print(f"\n=== Test 4: Track Referral Activation ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/track",
            json={
                "referral_code": code,
                "referred_user_id": TEST_REFERRED_USER_ID,
                "event": "activation"
            }
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Success: {data['message']}")
        else:
            print(f"✗ Error: {response.text}")


async def test_track_referral_conversion(code: str):
    """Test tracking referral conversion event (triggers rewards)"""
    print(f"\n=== Test 5: Track Referral Conversion ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/track",
            json={
                "referral_code": code,
                "referred_user_id": TEST_REFERRED_USER_ID,
                "event": "conversion"
            }
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Success: {data['message']}")
            print("  Note: Rewards should be granted (check referral_rewards table)")
        else:
            print(f"✗ Error: {response.text}")


async def test_get_referral_stats():
    """Test fetching referral stats"""
    print(f"\n=== Test 6: Get Referral Stats ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{MARKETING_SERVICE_URL}/api/v1/referrals/stats/{TEST_REFERRER_USER_ID}"
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Referral code: {data['referral_code']}")
            print(f"✓ Referrals sent: {data['referrals_sent']}")
            print(f"✓ Referrals signed up: {data['referrals_signed_up']}")
            print(f"✓ Referrals converted: {data['referrals_converted']}")
            print(f"✓ Rewards earned: ₹{data['rewards_earned_paise'] / 100:.2f}")
            print(f"✓ Rewards pending: ₹{data['rewards_pending_paise'] / 100:.2f}")
        else:
            print(f"✗ Error: {response.text}")


async def test_database_state():
    """Check database state"""
    print(f"\n=== Test 7: Database State ===")
    
    if not DATABASE_URL:
        print("✗ DATABASE_URL not set, skipping database check")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Check referrers table
        referrer = await conn.fetchrow(
            "SELECT * FROM referrers WHERE user_id = $1",
            TEST_REFERRER_USER_ID
        )
        
        if referrer:
            print(f"✓ Referrer record found:")
            print(f"  - Code: {referrer['referral_code']}")
            print(f"  - Total referrals: {referrer['total_referrals']}")
            print(f"  - Successful referrals: {referrer['successful_referrals']}")
            print(f"  - Total rewards: ₹{referrer['total_rewards_paise'] / 100:.2f}")
        else:
            print("✗ No referrer record found")
        
        # Check referrals table
        referrals = await conn.fetch(
            """
            SELECT r.*, ref.referral_code
            FROM referrals r
            JOIN referrers ref ON r.referrer_id = ref.id
            WHERE ref.user_id = $1
            """,
            TEST_REFERRER_USER_ID
        )
        
        print(f"\n✓ Found {len(referrals)} referral(s):")
        for ref in referrals:
            print(f"  - Referred user: {ref['referred_user_id']}")
            print(f"    Status: {ref['status']}")
            print(f"    Signup: {ref['signup_at']}")
            print(f"    Activated: {ref['activated_at']}")
            print(f"    Converted: {ref['converted_at']}")
        
        # Check rewards table
        rewards = await conn.fetch(
            """
            SELECT rr.*
            FROM referral_rewards rr
            WHERE rr.user_id = $1
            """,
            TEST_REFERRER_USER_ID
        )
        
        print(f"\n✓ Found {len(rewards)} reward(s):")
        for reward in rewards:
            print(f"  - Type: {reward['reward_type']}")
            print(f"    Value: ₹{reward['reward_value_paise'] / 100:.2f}")
            print(f"    Status: {reward['status']}")
            print(f"    Granted: {reward['granted_at']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"✗ Database error: {str(e)}")


async def cleanup_test_data():
    """Clean up test data"""
    print(f"\n=== Cleanup Test Data ===")
    
    if not DATABASE_URL:
        print("✗ DATABASE_URL not set, skipping cleanup")
        return
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Delete test referrals and rewards (cascade will handle related records)
        await conn.execute(
            "DELETE FROM referrers WHERE user_id = $1",
            TEST_REFERRER_USER_ID
        )
        
        print("✓ Test data cleaned up")
        
        await conn.close()
        
    except Exception as e:
        print(f"✗ Cleanup error: {str(e)}")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Referral Program Test Suite")
    print("=" * 60)
    
    try:
        # Test 1: Generate referral link
        referral_code = await test_generate_referral_link()
        
        if not referral_code:
            print("\n✗ Failed to generate referral code, stopping tests")
            return
        
        # Test 2: Validate referral code
        await test_validate_referral_code(referral_code)
        
        # Test 3: Track signup
        await test_track_referral_signup(referral_code)
        
        # Test 4: Track activation
        await test_track_referral_activation(referral_code)
        
        # Test 5: Track conversion (triggers rewards)
        await test_track_referral_conversion(referral_code)
        
        # Test 6: Get stats
        await test_get_referral_stats()
        
        # Test 7: Check database state
        await test_database_state()
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
        # Ask if user wants to cleanup
        cleanup = input("\nCleanup test data? (y/n): ")
        if cleanup.lower() == 'y':
            await cleanup_test_data()
        
    except Exception as e:
        print(f"\n✗ Test suite error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
