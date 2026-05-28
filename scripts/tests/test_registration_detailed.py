"""
Test registration endpoint with detailed error reporting
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
    print("Testing Auth Service Registration - Detailed")
    print("=" * 80)
    print()
    print("URL:", url)
    print("Data:", json.dumps(registration_data, indent=2))
    print()
    
    try:
        response = httpx.post(
            url,
            json=registration_data,
            timeout=10.0
        )
        
        print("Status Code:", response.status_code)
        print()
        
        if response.status_code == 422:
            print("⚠️ Validation Error - Field validation failed")
            print()
            print("Error Details:")
            try:
                error_data = response.json()
                print(json.dumps(error_data, indent=2))
            except:
                print(response.text)
        elif response.status_code == 500:
            print("❌ Server Error")
            print()
            print("Response:")
            print(response.text)
        elif response.status_code == 201:
            print("✅ Registration successful!")
            print()
            print("Response:")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"Status: {response.status_code}")
            print()
            print("Response:")
            try:
                print(json.dumps(response.json(), indent=2))
            except:
                print(response.text)
            
    except httpx.ConnectError as e:
        print("❌ Connection Error:", str(e))
        print("Make sure auth service is running on port 8000")
    except Exception as e:
        print("❌ Error:", str(e))
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    test_registration()
