"""
Test simple registration (email + password only)
"""
import httpx
import json

# Simple registration data (like frontend sends)
registration_data = {
    "email": "frontend@example.com",
    "password": "SecurePass123!"
}

def test_simple_registration():
    """Test registration with minimal data"""
    url = "http://localhost:8000/api/v1/auth/register"
    
    print("=" * 80)
    print("Testing Simple Registration (Frontend Compatible)")
    print("=" * 80)
    print()
    print("URL:", url)
    print("Data:", json.dumps(registration_data, indent=2))
    print()
    
    try:
        response = httpx.post(
            url,
            json=registration_data,
            timeout=10.0,
            follow_redirects=True
        )
        
        print("Status Code:", response.status_code)
        print()
        print("Response Body:")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)
        print()
        
        if response.status_code == 201:
            print("✅ Registration successful!")
        elif response.status_code == 400:
            print("⚠️ Bad request - check validation errors")
        elif response.status_code == 422:
            print("⚠️ Validation error - check required fields")
        elif response.status_code == 500:
            print("❌ Server error - check backend logs")
        else:
            print(f"⚠️ Unexpected status code: {response.status_code}")
            
    except httpx.ConnectError as e:
        print("❌ Connection Error:", str(e))
        print("Make sure auth service is running on port 8000")
    except Exception as e:
        print("❌ Error:", str(e))
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    test_simple_registration()
