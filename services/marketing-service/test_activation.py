"""
Test Activation Tracking System

Tests the activation event tracking endpoints and status computation.

Requirements: 10.1, 10.8
Task: 22
"""

import requests
import json
from datetime import datetime, timezone
import time

# Configuration
BASE_URL = "http://localhost:8006"
TEST_USER_ID = "test_user_activation_123"


def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_track_activation_event():
    """Test tracking activation events"""
    print_section("Test 1: Track Activation Events")
    
    # Reset user events first
    response = requests.delete(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}")
    print(f"Reset events: {response.json()}")
    
    # Track risk profile saved
    print("\n1. Tracking risk_profile_saved...")
    response = requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "risk_profile_saved",
            "user_id": TEST_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "experience": "intermediate",
                "markets": ["nse_fo", "crypto"],
                "capital": 500000
            }
        }
    )
    result = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(result, indent=2)}")
    assert result["success"] == True
    assert result["activation_status"]["is_activated"] == False
    assert "risk_profile_saved" in result["activation_status"]["completed_events"]
    print("✓ Risk profile event tracked successfully")
    
    time.sleep(1)
    
    # Track watchlist added
    print("\n2. Tracking watchlist_added...")
    response = requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "watchlist_added",
            "user_id": TEST_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "instrument_count": 3
            }
        }
    )
    result = response.json()
    print(f"Status: {response.status_code}")
    print(f"Completed events: {result['activation_status']['completed_events']}")
    assert result["activation_status"]["is_activated"] == False
    assert "watchlist_added" in result["activation_status"]["completed_events"]
    print("✓ Watchlist event tracked successfully")
    
    time.sleep(1)
    
    # Track first analysis run
    print("\n3. Tracking first_analysis_run...")
    response = requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "first_analysis_run",
            "user_id": TEST_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "instrument": "NIFTY",
                "analysisType": "technical"
            }
        }
    )
    result = response.json()
    print(f"Status: {response.status_code}")
    print(f"Completed events: {result['activation_status']['completed_events']}")
    assert result["activation_status"]["is_activated"] == False
    assert "first_analysis_run" in result["activation_status"]["completed_events"]
    print("✓ First analysis event tracked successfully")
    
    time.sleep(1)
    
    # Track first signal viewed (should complete activation)
    print("\n4. Tracking first_signal_viewed (should complete activation)...")
    response = requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "first_signal_viewed",
            "user_id": TEST_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "signalId": "sig_123",
                "instrument": "NIFTY",
                "recommendation": "BUY"
            }
        }
    )
    result = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(result, indent=2)}")
    assert result["success"] == True
    assert result["activation_status"]["is_activated"] == True
    assert "activation_completed" in result["activation_status"]["completed_events"]
    assert result["activation_status"]["time_to_activation"] is not None
    print(f"✓ Activation completed! Time to activation: {result['activation_status']['time_to_activation']}s")


def test_get_activation_status():
    """Test getting activation status"""
    print_section("Test 2: Get Activation Status")
    
    response = requests.get(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}")
    result = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(result, indent=2)}")
    
    assert result["is_activated"] == True
    assert len(result["completed_events"]) == 5  # 4 required + activation_completed
    assert len(result["pending_events"]) == 0
    assert result["activated_at"] is not None
    assert result["time_to_activation"] is not None
    
    print("✓ Activation status retrieved successfully")


def test_get_activation_events():
    """Test getting all activation events"""
    print_section("Test 3: Get Activation Events")
    
    response = requests.get(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}/events")
    result = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Total events: {result['total_events']}")
    print(f"\nEvents:")
    for event in result["events"]:
        print(f"  - {event['event_type']} at {event['timestamp']}")
    
    assert result["total_events"] == 5
    assert result["user_id"] == TEST_USER_ID
    
    print("\n✓ Activation events retrieved successfully")


def test_duplicate_event_prevention():
    """Test that duplicate events are prevented"""
    print_section("Test 4: Duplicate Event Prevention")
    
    # Try to track risk_profile_saved again
    print("Attempting to track duplicate risk_profile_saved event...")
    response = requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "risk_profile_saved",
            "user_id": TEST_USER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "experience": "advanced"  # Different metadata
            }
        }
    )
    result = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Message: {result['message']}")
    
    # Get events to verify no duplicate
    response = requests.get(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}/events")
    events = response.json()
    
    risk_profile_events = [e for e in events["events"] if e["event_type"] == "risk_profile_saved"]
    print(f"Risk profile events count: {len(risk_profile_events)}")
    
    assert len(risk_profile_events) == 1
    print("✓ Duplicate event prevented successfully")


def test_partial_activation():
    """Test user with partial activation"""
    print_section("Test 5: Partial Activation")
    
    partial_user_id = "test_user_partial_123"
    
    # Reset
    requests.delete(f"{BASE_URL}/api/v1/tracking/activation/{partial_user_id}")
    
    # Track only 2 events
    print("Tracking only 2 out of 4 required events...")
    requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "risk_profile_saved",
            "user_id": partial_user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )
    
    requests.post(
        f"{BASE_URL}/api/v1/tracking/activation",
        json={
            "event_type": "watchlist_added",
            "user_id": partial_user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )
    
    # Check status
    response = requests.get(f"{BASE_URL}/api/v1/tracking/activation/{partial_user_id}")
    result = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Is activated: {result['is_activated']}")
    print(f"Completed events: {result['completed_events']}")
    print(f"Pending events: {result['pending_events']}")
    
    assert result["is_activated"] == False
    assert len(result["completed_events"]) == 2
    assert len(result["pending_events"]) == 2
    assert "first_analysis_run" in result["pending_events"]
    assert "first_signal_viewed" in result["pending_events"]
    
    print("✓ Partial activation status correct")
    
    # Cleanup
    requests.delete(f"{BASE_URL}/api/v1/tracking/activation/{partial_user_id}")


def test_reset_activation():
    """Test resetting activation events"""
    print_section("Test 6: Reset Activation Events")
    
    # Reset the test user
    response = requests.delete(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}")
    result = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(result, indent=2)}")
    
    assert result["success"] == True
    
    # Verify events are cleared
    response = requests.get(f"{BASE_URL}/api/v1/tracking/activation/{TEST_USER_ID}/events")
    events = response.json()
    
    print(f"Events after reset: {events['total_events']}")
    assert events["total_events"] == 0
    
    print("✓ Activation events reset successfully")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("  ACTIVATION TRACKING SYSTEM TESTS")
    print("="*60)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Test User ID: {TEST_USER_ID}")
    
    try:
        # Check if service is running
        response = requests.get(f"{BASE_URL}/health")
        print(f"\n✓ Marketing service is running")
        print(f"  Service: {response.json()['service']}")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ ERROR: Cannot connect to marketing service at {BASE_URL}")
        print("  Please start the service with:")
        print("  cd signalixai-backend/services/marketing-service")
        print("  python -m uvicorn app.main:app --reload --port 8006")
        return
    
    try:
        test_track_activation_event()
        test_get_activation_status()
        test_get_activation_events()
        test_duplicate_event_prevention()
        test_partial_activation()
        test_reset_activation()
        
        print_section("ALL TESTS PASSED ✓")
        print("Activation tracking system is working correctly!")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        raise
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        raise


if __name__ == "__main__":
    run_all_tests()
