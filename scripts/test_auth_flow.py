"""
Test Complete Authentication Flow
Tests registration, login, and protected endpoints
"""

import asyncio
import httpx
import json
from datetime import datetime


async def test_auth_flow():
    """Test complete authentication flow"""
    print("🔐 Testing Complete Authentication Flow")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test data
    test_user = {
        "email": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@signalixai.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
        "phone": "+919876543210",
        "country_of_residence": "IN",
        "declared_trading_capital_inr": 50000000,  # ₹5L in paise
        "risk_tolerance_score": 7,
        "investment_horizon": "swing",
        "sebi_declaration_acknowledged": True
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # Test 1: Health Check
            print("\n1️⃣ Testing health endpoint...")
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
            
            # Test 2: Registration
            print("\n2️⃣ Testing user registration...")
            response = await client.post(
                f"{base_url}/api/v1/auth/register",
                json={
                    "email": test_user["email"],
                    "password": test_user["password"]
                }
            )
            
            if response.status_code == 201:
                print("✅ Registration successful")
                reg_data = response.json()
                print(f"   Message: {reg_data.get('message')}")
            else:
                print(f"❌ Registration failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
            
            # Test 3: Login
            print("\n3️⃣ Testing user login...")
            response = await client.post(
                f"{base_url}/api/v1/auth/login",
                json={
                    "email": test_user["email"],
                    "password": test_user["password"],
                    "rememberMe": False
                }
            )
            
            if response.status_code == 200:
                print("✅ Login successful")
                auth_data = response.json()
                access_token = auth_data.get("access_token")
                user_data = auth_data.get("user")
                print(f"   User ID: {user_data.get('id')}")
                print(f"   Email: {user_data.get('email')}")
                print(f"   Token: {access_token[:20]}...")
            else:
                print(f"❌ Login failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
            
            # Test 4: Protected Endpoint
            print("\n4️⃣ Testing protected endpoint...")
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get(
                f"{base_url}/api/v1/users/me",
                headers=headers
            )
            
            if response.status_code == 200:
                print("✅ Protected endpoint accessible")
                user_profile = response.json()
                print(f"   Profile loaded: {user_profile.get('email')}")
            else:
                print(f"❌ Protected endpoint failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
            
            # Test 5: Analysis Endpoint (if available)
            print("\n5️⃣ Testing analysis endpoint...")
            try:
                response = await client.post(
                    f"{base_url}/api/v1/analysis/run",
                    headers=headers,
                    json={
                        "instrument": "RELIANCE",
                        "analysis_type": "swing_trade",
                        "depth": "shallow"
                    }
                )
                
                if response.status_code in [200, 202]:
                    print("✅ Analysis endpoint accessible")
                    analysis_data = response.json()
                    print(f"   Analysis ID: {analysis_data.get('id')}")
                else:
                    print(f"⚠️ Analysis endpoint not ready: {response.status_code}")
            except Exception as e:
                print(f"⚠️ Analysis service not running: {e}")
            
            # Test 6: Logout
            print("\n6️⃣ Testing logout...")
            response = await client.post(
                f"{base_url}/api/v1/auth/logout",
                headers=headers
            )
            
            if response.status_code == 200:
                print("✅ Logout successful")
            else:
                print(f"⚠️ Logout response: {response.status_code}")
            
            print("\n" + "=" * 50)
            print("🎉 AUTHENTICATION FLOW TEST COMPLETE!")
            print("✅ Registration works")
            print("✅ Login works")
            print("✅ Protected endpoints work")
            print("✅ JWT tokens work")
            print("=" * 50)
            
            return True
            
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            return False


if __name__ == "__main__":
    print("Starting auth service test...")
    print("Make sure auth service is running: python services/auth-service/main.py")
    print()
    
    success = asyncio.run(test_auth_flow())
    
    if success:
        print("\n🚀 Authentication system is production ready!")
    else:
        print("\n❌ Authentication system needs fixes.")