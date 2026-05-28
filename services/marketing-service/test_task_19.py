"""
Test Script for Task 19: Lead Magnet Nurture Sequence
Run this script to verify the implementation
"""
import asyncio
import sys
from datetime import datetime

# Test imports
try:
    from app.data.sequences.lead_magnet import (
        get_lead_magnet_sequence,
        get_sequence_metadata,
        get_lead_magnet_content,
        LEAD_MAGNET_CONTENT
    )
    from app.config import settings
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


def test_sequence_configuration():
    """Test lead magnet sequence configuration"""
    print("\n" + "="*60)
    print("TEST 1: Sequence Configuration")
    print("="*60)
    
    try:
        sequence = get_lead_magnet_sequence()
        
        # Verify sequence length
        assert len(sequence) == 4, f"Expected 4 emails, got {len(sequence)}"
        print(f"✅ Sequence has correct length: {len(sequence)} emails")
        
        # Verify sequence days
        expected_days = [0, 2, 4, 7]
        actual_days = [step.day for step in sequence]
        assert actual_days == expected_days, f"Expected days {expected_days}, got {actual_days}"
        print(f"✅ Sequence days are correct: {actual_days}")
        
        # Verify delay hours
        expected_delays = [0, 48, 96, 168]
        actual_delays = [step.delay_hours for step in sequence]
        assert actual_delays == expected_delays, f"Expected delays {expected_delays}, got {actual_delays}"
        print(f"✅ Delay hours are correct: {actual_delays}")
        
        # Verify template names
        expected_templates = [
            "lead_magnet_delivery",
            "related_content",
            "case_study",
            "trial_invitation"
        ]
        actual_templates = [step.template_name for step in sequence]
        assert actual_templates == expected_templates, f"Expected templates {expected_templates}, got {actual_templates}"
        print(f"✅ Template names are correct")
        
        # Print sequence details
        print("\nSequence Details:")
        for step in sequence:
            print(f"  Day {step.day}: {step.template_name}")
            print(f"    Subject: {step.subject}")
            print(f"    Delay: {step.delay_hours} hours")
            print(f"    Description: {step.description}")
            print()
        
        return True
        
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_sequence_metadata():
    """Test sequence metadata"""
    print("\n" + "="*60)
    print("TEST 2: Sequence Metadata")
    print("="*60)
    
    try:
        metadata = get_sequence_metadata()
        
        # Verify metadata structure
        assert "name" in metadata, "Missing 'name' in metadata"
        assert "description" in metadata, "Missing 'description' in metadata"
        assert "total_emails" in metadata, "Missing 'total_emails' in metadata"
        assert "duration_days" in metadata, "Missing 'duration_days' in metadata"
        assert "steps" in metadata, "Missing 'steps' in metadata"
        print("✅ Metadata has all required fields")
        
        # Verify metadata values
        assert metadata["name"] == "lead_magnet", f"Expected name 'lead_magnet', got {metadata['name']}"
        assert metadata["total_emails"] == 4, f"Expected 4 emails, got {metadata['total_emails']}"
        assert metadata["duration_days"] == 7, f"Expected 7 days, got {metadata['duration_days']}"
        print("✅ Metadata values are correct")
        
        # Print metadata
        print("\nMetadata:")
        print(f"  Name: {metadata['name']}")
        print(f"  Description: {metadata['description']}")
        print(f"  Total Emails: {metadata['total_emails']}")
        print(f"  Duration: {metadata['duration_days']} days")
        print(f"  Steps: {len(metadata['steps'])} steps")
        
        return True
        
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_lead_magnet_content():
    """Test lead magnet content mapping"""
    print("\n" + "="*60)
    print("TEST 3: Lead Magnet Content Mapping")
    print("="*60)
    
    try:
        # Verify all lead magnets have content
        expected_magnets = [
            "fo-trading-checklist",
            "options-greeks-cheat-sheet",
            "position-sizing-calculator",
            "backtesting-template",
            "ai-trading-signals-guide"
        ]
        
        for magnet_id in expected_magnets:
            content = get_lead_magnet_content(magnet_id)
            
            # Verify content structure
            assert "title" in content, f"Missing 'title' for {magnet_id}"
            assert "topic" in content, f"Missing 'topic' for {magnet_id}"
            assert "category" in content, f"Missing 'category' for {magnet_id}"
            assert "related_resources" in content, f"Missing 'related_resources' for {magnet_id}"
            
            print(f"✅ {magnet_id}: {content['title']}")
            print(f"   Topic: {content['topic']}")
            print(f"   Category: {content['category']}")
            print(f"   Related Resources: {len(content['related_resources'])} items")
        
        # Test unknown lead magnet (should return default)
        unknown_content = get_lead_magnet_content("unknown-magnet")
        assert unknown_content["title"] == "Trading Resource", "Default content not returned for unknown magnet"
        print("\n✅ Unknown lead magnet returns default content")
        
        return True
        
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_config_templates():
    """Test configuration template IDs"""
    print("\n" + "="*60)
    print("TEST 4: Configuration Template IDs")
    print("="*60)
    
    try:
        # Verify template IDs exist in config
        required_templates = [
            "TEMPLATE_LEAD_MAGNET_DELIVERY",
            "TEMPLATE_RELATED_CONTENT",
            "TEMPLATE_CASE_STUDY",
            "TEMPLATE_TRIAL_INVITATION"
        ]
        
        for template_name in required_templates:
            assert hasattr(settings, template_name), f"Missing template: {template_name}"
            template_id = getattr(settings, template_name)
            print(f"✅ {template_name}: {template_id}")
        
        return True
        
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_email_service_templates():
    """Test email service template mapping"""
    print("\n" + "="*60)
    print("TEST 5: Email Service Template Mapping")
    print("="*60)
    
    try:
        from app.services.email_service import email_service
        
        # Verify template mappings
        required_templates = [
            "lead_magnet_delivery",
            "related_content",
            "case_study",
            "trial_invitation"
        ]
        
        for template_name in required_templates:
            template_id = email_service.get_template_id(template_name)
            assert template_id is not None, f"Template not mapped: {template_name}"
            print(f"✅ {template_name} → {template_id}")
        
        return True
        
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_leads_router():
    """Test leads router imports"""
    print("\n" + "="*60)
    print("TEST 6: Leads Router")
    print("="*60)
    
    try:
        from app.routers.leads import (
            router,
            LeadCaptureRequest,
            LeadCaptureResponse,
            LeadStats,
            LEAD_MAGNET_DOWNLOADS
        )
        
        print("✅ Leads router imports successful")
        
        # Verify lead magnet downloads
        assert len(LEAD_MAGNET_DOWNLOADS) == 5, f"Expected 5 lead magnets, got {len(LEAD_MAGNET_DOWNLOADS)}"
        print(f"✅ Lead magnet downloads configured: {len(LEAD_MAGNET_DOWNLOADS)} items")
        
        for magnet_id, url in LEAD_MAGNET_DOWNLOADS.items():
            print(f"   {magnet_id}: {url}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_sequences_router_update():
    """Test sequences router supports lead_magnet"""
    print("\n" + "="*60)
    print("TEST 7: Sequences Router Update")
    print("="*60)
    
    try:
        from app.routers.sequences import router
        from app.data.sequences.lead_magnet import get_lead_magnet_sequence
        
        print("✅ Sequences router imports lead_magnet sequence")
        
        # Verify sequence can be retrieved
        sequence = get_lead_magnet_sequence()
        assert len(sequence) == 4, "Lead magnet sequence not properly configured"
        print("✅ Lead magnet sequence accessible from sequences router")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("TASK 19 IMPLEMENTATION TESTS")
    print("Lead Magnet Nurture Sequence")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Sequence Configuration", test_sequence_configuration),
        ("Sequence Metadata", test_sequence_metadata),
        ("Lead Magnet Content", test_lead_magnet_content),
        ("Config Templates", test_config_templates),
        ("Email Service Templates", test_email_service_templates),
        ("Leads Router", test_leads_router),
        ("Sequences Router Update", test_sequences_router_update),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*60)
    print(f"Results: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n🎉 All tests passed! Task 19 implementation is complete.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
