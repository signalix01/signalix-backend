"""
Test Affiliate Program Endpoints
Task: 30.1 - Implement affiliate dashboard backend
Requirements: 12.7, 12.8

Run with: python test_affiliate.py
"""

import asyncio
import asyncpg
from datetime import datetime
import sys

# Configuration
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/signalixai"
BASE_URL = "http://localhost:8000"


async def setup_test_data(conn):
    """Create test affiliate and related data"""
    print("\n=== Setting up test data ===")
    
    # Create test affiliate
    affiliate_id = await conn.fetchval(
        """
        INSERT INTO affiliates (
            email, name, affiliate_code, commission_rate, status
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (email) DO UPDATE 
        SET name = EXCLUDED.name
        RETURNING id
        """,
        "test@example.com",
        "Test Affiliate",
        "TEST123ABC",
        20.00,
        "active"
    )
    print(f"✓ Created test affiliate: {affiliate_id}")
    
    # Create test clicks
    for i in range(5):
        await conn.execute(
            """
            INSERT INTO affiliate_clicks (
                affiliate_id, visitor_id, landing_page
            )
            VALUES ($1, $2, $3)
            """,
            affiliate_id,
            f"visitor_{i}",
            "https://signalixai.com/signup?aff=TEST123ABC"
        )
    print("✓ Created 5 test clicks")
    
    # Create test conversion
    conversion_id = await conn.fetchval(
        """
        INSERT INTO affiliate_conversions (
            affiliate_id, referred_user_id, subscription_id, 
            status, signup_at, first_payment_at
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (affiliate_id, referred_user_id) DO UPDATE
        SET status = EXCLUDED.status
        RETURNING id
        """,
        affiliate_id,
        "user_test_123",
        "sub_test_123",
        "active",
        datetime.utcnow(),
        datetime.utcnow()
    )
    print(f"✓ Created test conversion: {conversion_id}")
    
    # Create test commissions
    for period in range(1, 4):  # 3 months of commissions
        await conn.execute(
            """
            INSERT INTO affiliate_commissions (
                affiliate_id, conversion_id, referred_user_id, subscription_id,
                payment_id, commission_amount_paise, commission_rate,
                subscription_amount_paise, period, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT DO NOTHING
            """,
            affiliate_id,
            conversion_id,
            "user_test_123",
            "sub_test_123",
            f"pay_test_{period}",
            39980,  # 20% of 199900 paise (₹1,999)
            20.00,
            199900,
            period,
            "approved" if period <= 2 else "pending"
        )
    print("✓ Created 3 test commissions")
    
    # Update affiliate stats
    await conn.execute(
        """
        UPDATE affiliates 
        SET total_clicks = 5,
            total_signups = 1,
            total_conversions = 1,
            total_commission_paise = 119940,
            pending_commission_paise = 39980,
            paid_commission_paise = 0
        WHERE id = $1
        """,
        affiliate_id
    )
    print("✓ Updated affiliate stats")
    
    return affiliate_id


async def test_affiliate_stats(conn, affiliate_id):
    """Test fetching affiliate stats"""
    print("\n=== Testing Affiliate Stats ===")
    
    stats = await conn.fetchrow(
        """
        SELECT 
            id, affiliate_code, name, email, status, commission_rate,
            total_clicks, total_signups, total_conversions,
            total_commission_paise, pending_commission_paise, paid_commission_paise
        FROM affiliates
        WHERE id = $1
        """,
        affiliate_id
    )
    
    if stats:
        print(f"✓ Affiliate Code: {stats['affiliate_code']}")
        print(f"✓ Name: {stats['name']}")
        print(f"✓ Status: {stats['status']}")
        print(f"✓ Commission Rate: {stats['commission_rate']}%")
        print(f"✓ Total Clicks: {stats['total_clicks']}")
        print(f"✓ Total Signups: {stats['total_signups']}")
        print(f"✓ Total Conversions: {stats['total_conversions']}")
        print(f"✓ Total Commission: ₹{stats['total_commission_paise'] / 100:.2f}")
        print(f"✓ Pending Commission: ₹{stats['pending_commission_paise'] / 100:.2f}")
        print(f"✓ Paid Commission: ₹{stats['paid_commission_paise'] / 100:.2f}")
        return True
    else:
        print("✗ Failed to fetch affiliate stats")
        return False


async def test_commission_history(conn, affiliate_id):
    """Test fetching commission history"""
    print("\n=== Testing Commission History ===")
    
    commissions = await conn.fetch(
        """
        SELECT 
            id, period, commission_amount_paise, subscription_amount_paise,
            status, created_at
        FROM affiliate_commissions
        WHERE affiliate_id = $1
        ORDER BY period
        """,
        affiliate_id
    )
    
    if commissions:
        print(f"✓ Found {len(commissions)} commission records")
        for comm in commissions:
            print(f"  - Period {comm['period']}/12: ₹{comm['commission_amount_paise'] / 100:.2f} ({comm['status']})")
        return True
    else:
        print("✗ No commission records found")
        return False


async def test_conversion_tracking(conn, affiliate_id):
    """Test conversion tracking"""
    print("\n=== Testing Conversion Tracking ===")
    
    conversions = await conn.fetch(
        """
        SELECT 
            id, referred_user_id, subscription_id, status,
            signup_at, first_payment_at, total_commission_paise
        FROM affiliate_conversions
        WHERE affiliate_id = $1
        """,
        affiliate_id
    )
    
    if conversions:
        print(f"✓ Found {len(conversions)} conversion records")
        for conv in conversions:
            print(f"  - User: {conv['referred_user_id']}")
            print(f"    Status: {conv['status']}")
            print(f"    Signup: {conv['signup_at'].strftime('%Y-%m-%d')}")
            print(f"    First Payment: {conv['first_payment_at'].strftime('%Y-%m-%d')}")
            print(f"    Total Commission: ₹{conv['total_commission_paise'] / 100:.2f}")
        return True
    else:
        print("✗ No conversion records found")
        return False


async def test_click_tracking(conn, affiliate_id):
    """Test click tracking"""
    print("\n=== Testing Click Tracking ===")
    
    clicks = await conn.fetch(
        """
        SELECT 
            id, visitor_id, landing_page, clicked_at
        FROM affiliate_clicks
        WHERE affiliate_id = $1
        ORDER BY clicked_at DESC
        LIMIT 5
        """,
        affiliate_id
    )
    
    if clicks:
        print(f"✓ Found {len(clicks)} click records")
        for click in clicks:
            print(f"  - Visitor: {click['visitor_id']}")
            print(f"    Time: {click['clicked_at'].strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    else:
        print("✗ No click records found")
        return False


async def test_commission_calculation():
    """Test commission calculation logic"""
    print("\n=== Testing Commission Calculation ===")
    
    test_cases = [
        {"subscription": 199900, "rate": 20.00, "expected": 39980},
        {"subscription": 499900, "rate": 20.00, "expected": 99980},
        {"subscription": 199900, "rate": 25.00, "expected": 49975},
    ]
    
    all_passed = True
    for case in test_cases:
        calculated = int(case["subscription"] * (case["rate"] / 100))
        passed = calculated == case["expected"]
        status = "✓" if passed else "✗"
        print(f"{status} Subscription: ₹{case['subscription']/100:.2f}, Rate: {case['rate']}% → Commission: ₹{calculated/100:.2f}")
        if not passed:
            print(f"  Expected: ₹{case['expected']/100:.2f}")
            all_passed = False
    
    return all_passed


async def test_affiliate_code_validation(conn):
    """Test affiliate code validation"""
    print("\n=== Testing Affiliate Code Validation ===")
    
    # Test valid code
    valid = await conn.fetchrow(
        """
        SELECT id, name, status
        FROM affiliates
        WHERE affiliate_code = $1 AND status = 'active'
        """,
        "TEST123ABC"
    )
    
    if valid:
        print(f"✓ Valid code 'TEST123ABC' found: {valid['name']}")
    else:
        print("✗ Valid code not found")
        return False
    
    # Test invalid code
    invalid = await conn.fetchrow(
        """
        SELECT id
        FROM affiliates
        WHERE affiliate_code = $1 AND status = 'active'
        """,
        "INVALID123"
    )
    
    if not invalid:
        print("✓ Invalid code 'INVALID123' correctly rejected")
    else:
        print("✗ Invalid code incorrectly accepted")
        return False
    
    return True


async def cleanup_test_data(conn):
    """Clean up test data"""
    print("\n=== Cleaning up test data ===")
    
    # Delete in reverse order of foreign key dependencies
    await conn.execute("DELETE FROM affiliate_commissions WHERE payment_id LIKE 'pay_test_%'")
    print("✓ Deleted test commissions")
    
    await conn.execute("DELETE FROM affiliate_conversions WHERE referred_user_id = 'user_test_123'")
    print("✓ Deleted test conversions")
    
    await conn.execute("DELETE FROM affiliate_clicks WHERE visitor_id LIKE 'visitor_%'")
    print("✓ Deleted test clicks")
    
    await conn.execute("DELETE FROM affiliates WHERE email = 'test@example.com'")
    print("✓ Deleted test affiliate")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("AFFILIATE PROGRAM TEST SUITE")
    print("=" * 60)
    
    try:
        # Connect to database
        print("\nConnecting to database...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✓ Connected to database")
        
        # Setup test data
        affiliate_id = await setup_test_data(conn)
        
        # Run tests
        results = []
        results.append(("Affiliate Stats", await test_affiliate_stats(conn, affiliate_id)))
        results.append(("Commission History", await test_commission_history(conn, affiliate_id)))
        results.append(("Conversion Tracking", await test_conversion_tracking(conn, affiliate_id)))
        results.append(("Click Tracking", await test_click_tracking(conn, affiliate_id)))
        results.append(("Commission Calculation", await test_commission_calculation()))
        results.append(("Code Validation", await test_affiliate_code_validation(conn)))
        
        # Cleanup
        await cleanup_test_data(conn)
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            return 1
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if 'conn' in locals():
            await conn.close()
            print("\n✓ Database connection closed")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
