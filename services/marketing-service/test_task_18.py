"""
Test script for Task 18 implementation
Tests sequence enrollment and trigger firing
"""
import sys
import asyncio
from datetime import datetime, timedelta

# Add app to path
sys.path.insert(0, '.')

from app.data.sequences.onboarding import get_onboarding_sequence, get_sequence_metadata
from app.services.trigger_service import trigger_service, TriggerType


def test_sequence_configuration():
    """Test onboarding sequence configuration"""
    print("=" * 60)
    print("TEST 1: Onboarding Sequence Configuration")
    print("=" * 60)
    
    sequence = get_onboarding_sequence()
    print(f"\n✓ Sequence loaded: {len(sequence)} emails")
    
    for step in sequence:
        print(f"  Day {step.day}: {step.template_name}")
        print(f"    Subject: {step.subject}")
        print(f"    Delay: {step.delay_hours}h")
        print(f"    Description: {step.description}")
        print()
    
    metadata = get_sequence_metadata()
    print(f"✓ Metadata: {metadata['name']}")
    print(f"  Total emails: {metadata['total_emails']}")
    print(f"  Duration: {metadata['duration_days']} days")
    print()


def test_trigger_service():
    """Test trigger service logic"""
    print("=" * 60)
    print("TEST 2: Trigger Service")
    print("=" * 60)
    
    # Test incomplete onboarding trigger
    print("\n1. Testing incomplete_onboarding trigger:")
    
    # Too early (less than 24h)
    result = trigger_service.fire_incomplete_onboarding_trigger(
        user_id="test-user-1",
        email="test1@example.com",
        first_name="Test",
        onboarding_progress=40,
        next_step="Add watchlist",
        signup_time=datetime.utcnow() - timedelta(hours=12)
    )
    print(f"  Too early (12h): {result['success']} - {result['message']}")
    
    # Valid (24h+)
    result = trigger_service.fire_incomplete_onboarding_trigger(
        user_id="test-user-2",
        email="test2@example.com",
        first_name="Test",
        onboarding_progress=40,
        next_step="Add watchlist",
        signup_time=datetime.utcnow() - timedelta(hours=25)
    )
    print(f"  Valid (25h): {result['success']} - {result['message']}")
    if result['success']:
        print(f"    Job ID: {result.get('job_id')}")
    
    # Test inactive user trigger
    print("\n2. Testing inactive_user trigger:")
    
    # Too early (less than 7 days)
    result = trigger_service.fire_inactive_user_trigger(
        user_id="test-user-3",
        email="test3@example.com",
        first_name="Test",
        last_login=datetime.utcnow() - timedelta(days=5),
        days_inactive=5
    )
    print(f"  Too early (5 days): {result['success']} - {result['message']}")
    
    # Valid (7+ days)
    result = trigger_service.fire_inactive_user_trigger(
        user_id="test-user-4",
        email="test4@example.com",
        first_name="Test",
        last_login=datetime.utcnow() - timedelta(days=8),
        days_inactive=8
    )
    print(f"  Valid (8 days): {result['success']} - {result['message']}")
    if result['success']:
        print(f"    Job ID: {result.get('job_id')}")
    
    # Test upgrade prompt trigger
    print("\n3. Testing upgrade_prompt trigger:")
    
    # Wrong tier (not free)
    result = trigger_service.fire_upgrade_prompt_trigger(
        user_id="test-user-5",
        email="test5@example.com",
        first_name="Test",
        current_tier="pro",
        usage_percentage=85,
        analyses_used=77,
        analyses_limit=90
    )
    print(f"  Wrong tier (pro): {result['success']} - {result['message']}")
    
    # Low usage (<80%)
    result = trigger_service.fire_upgrade_prompt_trigger(
        user_id="test-user-6",
        email="test6@example.com",
        first_name="Test",
        current_tier="free",
        usage_percentage=70,
        analyses_used=63,
        analyses_limit=90
    )
    print(f"  Low usage (70%): {result['success']} - {result['message']}")
    
    # Valid (free tier, high usage)
    result = trigger_service.fire_upgrade_prompt_trigger(
        user_id="test-user-7",
        email="test7@example.com",
        first_name="Test",
        current_tier="free",
        usage_percentage=85,
        analyses_used=77,
        analyses_limit=90
    )
    print(f"  Valid (free, 85%): {result['success']} - {result['message']}")
    if result['success']:
        print(f"    Job ID: {result.get('job_id')}")
    
    # Test feature unused trigger
    print("\n4. Testing feature_unused trigger:")
    
    result = trigger_service.fire_feature_unused_trigger(
        user_id="test-user-8",
        email="test8@example.com",
        first_name="Test",
        feature_name="Options Intelligence",
        feature_description="AI-powered options analysis",
        days_since_signup=5
    )
    print(f"  Feature unused: {result['success']} - {result['message']}")
    if result['success']:
        print(f"    Job ID: {result.get('job_id')}")
    
    print()


def test_trigger_types():
    """Test trigger type constants"""
    print("=" * 60)
    print("TEST 3: Trigger Types")
    print("=" * 60)
    
    print(f"\n✓ Trigger types defined:")
    print(f"  - {TriggerType.INCOMPLETE_ONBOARDING}")
    print(f"  - {TriggerType.INACTIVE_USER}")
    print(f"  - {TriggerType.FEATURE_UNUSED}")
    print(f"  - {TriggerType.UPGRADE_PROMPT}")
    print()


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TASK 18 IMPLEMENTATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        # Test 1: Sequence configuration
        test_sequence_configuration()
        
        # Test 2: Trigger service
        test_trigger_service()
        
        # Test 3: Trigger types
        test_trigger_types()
        
        print("=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nNote: Email jobs are queued but not sent in test mode.")
        print("To actually send emails, ensure:")
        print("  1. Redis is running")
        print("  2. rq worker is running: rq worker emails")
        print("  3. SENDGRID_API_KEY is configured in .env")
        print()
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
