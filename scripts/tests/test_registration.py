"""
Test registration endpoint
"""
import httpx
import json

# Test registration data
registration_data = {
    "email": "test@example.com",
    "phone": "+919876543210",
    "password": "SecurePass123!",
    "full_name": "Test User",
    "country_of_residence": "IN",
    "declared_trading_capital_inr": 10000000,  # 1 lakh in paise
    "risk_tolerance_score": 7,
    "investment_horizon": "swing",
    "sebi_declaration_acknowledged": True
}

def test_registration():
    """Test registration endpoint"""
    url = "http://localhost:8000/api/v1/auth/register"
    
    print("=" * 80)
    print("Testing Auth Service Registration")
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
        print("Response Headers:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
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
    test_registration()
