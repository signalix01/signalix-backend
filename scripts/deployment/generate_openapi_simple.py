"""
Simple OpenAPI Specification Generator (No Dependencies)

Generates OpenAPI spec by starting the FastAPI app without importing
modules that have heavy dependencies like talib.

Usage:
    python generate_openapi_simple.py
"""

import json
import sys
import os

# Set environment to avoid loading heavy dependencies
os.environ["SKIP_HEAVY_IMPORTS"] = "1"

def main():
    """Generate OpenAPI spec"""
    print("=" * 80)
    print("Simple OpenAPI Specification Generator")
    print("=" * 80)
    print()
    
    try:
        # Import FastAPI app
        print("Importing FastAPI app...")
        from main_app import app
        
        print("✓ App imported successfully")
        print()
        
        # Get OpenAPI schema
        print("Generating OpenAPI schema...")
        openapi_schema = app.openapi()
        
        print("✓ Schema generated")
        print()
        
        # Write to file
        output_file = "api_spec.json"
        print(f"Writing to {output_file}...")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        
        print("✓ File written successfully")
        print()
        
        # Print statistics
        print("=" * 80)
        print("OpenAPI Specification Statistics")
        print("=" * 80)
        print(f"  OpenAPI version: {openapi_schema.get('openapi', 'N/A')}")
        print(f"  API title: {openapi_schema.get('info', {}).get('title', 'N/A')}")
        print(f"  API version: {openapi_schema.get('info', {}).get('version', 'N/A')}")
        print(f"  Total paths: {len(openapi_schema.get('paths', {}))}")
        print(f"  Total schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")
        print(f"  Total tags: {len(openapi_schema.get('tags', []))}")
        print()
        
        # List all paths
        if openapi_schema.get('paths'):
            print("Documented Endpoints:")
            for path, methods in openapi_schema['paths'].items():
                for method in methods:
                    if method in ['get', 'post', 'put', 'delete', 'patch']:
                        print(f"  {method.upper():6} {path}")
        
        print()
        print("=" * 80)
        print("✓ SUCCESS: OpenAPI specification generated")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Review api_spec.json")
        print("  2. Validate at https://editor.swagger.io/")
        print("  3. Start server: uvicorn main_app:app --reload")
        print("  4. Visit http://localhost:8080/api/docs")
        print()
        
        return 0
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print()
        print("This might be due to missing dependencies.")
        print("The OpenAPI spec has been pre-generated and is available in api_spec.json")
        return 1
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
