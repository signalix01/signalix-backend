"""
Test script for email service
Run this to verify SendGrid integration is working
"""
import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.email_service import email_service
from app.config import settings


async def test_welcome_email():
    """Test welcome email"""
    print("Testing welcome email...")
    try:
        result = await email_service.send_transactional(
            template_name="welcome",
            to_email="test@example.com",  # Replace with your email
            dynamic_data={
                "first_name": "Test User",
                "dashboard_url": settings.DASHBOARD_URL,
                "help_url": settings.HELP_URL,
                "unsubscribe_url": f"{settings.UNSUBSCRIBE_BASE_URL}?email=test@example.com",
                "preferences_url": f"{settings.PREFERENCES_BASE_URL}?email=test@example.com",
            }
        )
        print(f"✅ Welcome email sent successfully: {result}")
        return True
    except Exception as e:
        print(f"❌ Welcome email failed: {str(e)}")
        return False


async def test_verification_email():
    """Test verification email"""
    print("\nTesting verification email...")
    try:
        result = await email_service.send_transactional(
            template_name="verify_email",
            to_email="test@example.com",  # Replace with your email
            dynamic_data={
                "verification_code": "123456",
            }
        )
        print(f"✅ Verification email sent successfully: {result}")
        return True
    except Exception as e:
        print(f"❌ Verification email failed: {str(e)}")
        return False


async def test_password_reset_email():
    """Test password reset email"""
    print("\nTesting password reset email...")
    try:
        result = await email_service.send_transactional(
            template_name="password_reset",
            to_email="test@example.com",  # Replace with your email
            dynamic_data={
                "first_name": "Test User",
                "reset_url": f"{settings.DASHBOARD_URL}/reset-password?token=test123",
                "reset_token": "test123",
            }
        )
        print(f"✅ Password reset email sent successfully: {result}")
        return True
    except Exception as e:
        print(f"❌ Password reset email failed: {str(e)}")
        return False


async def test_subscription_confirmation_email():
    """Test subscription confirmation email"""
    print("\nTesting subscription confirmation email...")
    try:
        result = await email_service.send_transactional(
            template_name="subscription_confirmation",
            to_email="test@example.com",  # Replace with your email
            dynamic_data={
                "first_name": "Test User",
                "plan_name": "Pro",
                "plan_price": "₹1,999.00",
                "billing_period": "monthly",
                "next_billing_date": "February 15, 2024",
                "dashboard_url": settings.DASHBOARD_URL,
                "manage_subscription_url": f"{settings.DASHBOARD_URL}/settings/subscription",
            }
        )
        print(f"✅ Subscription confirmation email sent successfully: {result}")
        return True
    except Exception as e:
        print(f"❌ Subscription confirmation email failed: {str(e)}")
        return False


async def test_payment_receipt_email():
    """Test payment receipt email"""
    print("\nTesting payment receipt email...")
    try:
        result = await email_service.send_transactional(
            template_name="payment_receipt",
            to_email="test@example.com",  # Replace with your email
            dynamic_data={
                "first_name": "Test User",
                "invoice_number": "INV-2024-001",
                "payment_date": "January 15, 2024",
                "amount_paid": "₹1,999.00",
                "plan_name": "Pro",
                "billing_period": "monthly",
                "payment_method": "Visa ending in 4242",
                "dashboard_url": settings.DASHBOARD_URL,
                "invoice_url": f"{settings.DASHBOARD_URL}/invoices/INV-2024-001",
            }
        )
        print(f"✅ Payment receipt email sent successfully: {result}")
        return True
    except Exception as e:
        print(f"❌ Payment receipt email failed: {str(e)}")
        return False


async def run_all_tests():
    """Run all email tests"""
    print("=" * 60)
    print("Email Service Test Suite")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  FROM_EMAIL: {settings.FROM_EMAIL}")
    print(f"  FROM_NAME: {settings.FROM_NAME}")
    print(f"  SENDGRID_API_KEY: {'*' * 20}{settings.SENDGRID_API_KEY[-4:]}")
    print("\n" + "=" * 60)
    
    results = []
    
    # Run tests
    results.append(await test_welcome_email())
    results.append(await test_verification_email())
    results.append(await test_password_reset_email())
    results.append(await test_subscription_confirmation_email())
    results.append(await test_payment_receipt_email())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ All tests passed!")
    else:
        print(f"❌ {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    print("\n⚠️  IMPORTANT: Replace 'test@example.com' with your actual email address in this script!\n")
    
    # Run tests
    success = asyncio.run(run_all_tests())
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
