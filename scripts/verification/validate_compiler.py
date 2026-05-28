"""Quick validation script for StrategyCompiler"""
import sys
import os

# Add to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    print("Importing compiler...")
    from services.algo_builder.compiler import StrategyCompiler
    print("✓ Compiler imported successfully")
    
    print("\nImporting models...")
    from services.algo_builder.models import StrategySpec
    print("✓ Models imported successfully")
    
    print("\nCreating compiler instance...")
    compiler = StrategyCompiler()
    print("✓ Compiler instantiated successfully")
    
    print("\n" + "="*60)
    print("SUCCESS: All imports and instantiation working correctly")
    print("="*60)
    print("\nThe StrategyCompiler is ready to use.")
    print("Run 'python services/algo_builder/run_compiler_tests.py' for full tests.")
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
