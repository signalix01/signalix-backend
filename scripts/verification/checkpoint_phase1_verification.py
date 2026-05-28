"""
Phase 1 Checkpoint Verification Script
Verifies all Phase 1 tasks are complete before proceeding to Phase 2
"""
import os
import sys

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_section(text):
    """Print a formatted section"""
    print(f"\n--- {text} ---")

def check_migration_files():
    """Check that all required migration files exist"""
    print_section("Checking Migration Files")
    
    required_migrations = [
        "alembic/versions/004_algo_builder_schema.py",
        "alembic/versions/005_screening_snapshot_view.py",
        "alembic/versions/006_strategy_templates.py"
    ]
    
    all_exist = True
    for migration in required_migrations:
        if os.path.exists(migration):
            print(f"✓ {migration}")
        else:
            print(f"✗ {migration} NOT FOUND")
            all_exist = False
    
    return all_exist

def check_test_files():
    """Check that test files exist"""
    print_section("Checking Test Files")
    
    test_files = [
        "test_migration_004.py",
        "tests/test_screening_snapshot.py",
        "test_strategy_templates_validation.py"
    ]
    
    all_exist = True
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"✓ {test_file}")
        else:
            print(f"✗ {test_file} NOT FOUND")
            all_exist = False
    
    return all_exist

def check_documentation():
    """Check that documentation files exist"""
    print_section("Checking Documentation")
    
    doc_files = [
        "alembic/versions/README_004.md",
        "alembic/versions/README_005.md",
        "alembic/versions/README_006.md"
    ]
    
    all_exist = True
    for doc_file in doc_files:
        if os.path.exists(doc_file):
            print(f"✓ {doc_file}")
        else:
            print(f"✗ {doc_file} NOT FOUND")
            all_exist = False
    
    return all_exist

def check_models():
    """Check that SQLAlchemy models were created"""
    print_section("Checking SQLAlchemy Models")
    
    models_file = "shared/database/models.py"
    
    if not os.path.exists(models_file):
        print(f"✗ {models_file} NOT FOUND")
        return False
    
    with open(models_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_models = [
        "class Strategy",
        "class BacktestResult",
        "class ScreeningCriteria",
        "class ScreeningResult",
        "class AnomalyEvent",
        "class AlertRule",
        "class AlertDeliveryLog"
    ]
    
    all_exist = True
    for model in required_models:
        if model in content:
            print(f"✓ {model}")
        else:
            print(f"✗ {model} NOT FOUND in models.py")
            all_exist = False
    
    return all_exist

def check_pydantic_models():
    """Check that Pydantic models for strategy templates exist"""
    print_section("Checking Pydantic Models")
    
    models_file = "services/algo_builder/models.py"
    
    if not os.path.exists(models_file):
        print(f"✗ {models_file} NOT FOUND")
        return False
    
    with open(models_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_models = [
        "class IndicatorType",
        "class CompareOperator",
        "class ConditionBlock",
        "class EntryRule",
        "class ExitRule",
        "class PositionSizing",
        "class StrategySpec"
    ]
    
    all_exist = True
    for model in required_models:
        if model in content:
            print(f"✓ {model}")
        else:
            print(f"✗ {model} NOT FOUND in algo_builder/models.py")
            all_exist = False
    
    return all_exist

def main():
    """Run all checkpoint verifications"""
    print_header("Phase 1 Checkpoint Verification")
    print("\nThis script verifies that all Phase 1 tasks are complete:")
    print("  Task 1: TimescaleDB schema extensions")
    print("  Task 2: screening_snapshot materialized view")
    print("  Task 3: Strategy templates seed data")
    
    results = []
    
    # Check migration files
    results.append(("Migration Files", check_migration_files()))
    
    # Check test files
    results.append(("Test Files", check_test_files()))
    
    # Check documentation
    results.append(("Documentation", check_documentation()))
    
    # Check SQLAlchemy models
    results.append(("SQLAlchemy Models", check_models()))
    
    # Check Pydantic models
    results.append(("Pydantic Models", check_pydantic_models()))
    
    # Print summary
    print_header("Verification Summary")
    
    all_passed = True
    for check_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:10} {check_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    
    if all_passed:
        print("\n✓ ALL CHECKS PASSED")
        print("\nPhase 1 is complete! All required files and models are in place.")
        print("\nNext steps:")
        print("  1. Run database migrations: python -m alembic upgrade head")
        print("  2. Run test scripts to verify database setup")
        print("  3. Proceed to Phase 2: Strategy Specification & Validation")
        return 0
    else:
        print("\n✗ SOME CHECKS FAILED")
        print("\nPlease review the failed checks above and ensure all files are created.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
