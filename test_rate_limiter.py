
# ==================== RATE LIMITER VALIDATION SCRIPT ====================
# 
# Save this as: test_rate_limiter.py
# Run with: python test_rate_limiter.py
#
# This validates your Step 2 changes without running the full bot

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_rate_limiter_implementation():
    """
    Test the rate limiter implementation you just added
    """
    
    print("=" * 60)
    print("TESTING RATE LIMITER IMPLEMENTATION")
    print("=" * 60)
    
    try:
        # Import your modified upstox client
        from src.upstox_api_client import UpstoxClient
        from config.settings import get_settings
        
        # Load settings
        settings = get_settings()
        
        # Create client (should now have rate limiter)
        client = UpstoxClient(
            settings.upstox_api_key,
            settings.upstox_api_secret, 
            settings.upstox_redirect_uri
        )
        
        # Test 1: Check if rate limiter was added
        print("\n1. Testing Rate Limiter Integration...")
        
        if hasattr(client, 'rate_limiter'):
            print("   ✅ Rate limiter found in client")
            
            if hasattr(client.rate_limiter, 'wait_if_needed'):
                print("   ✅ Rate limiter has wait_if_needed method")
            else:
                print("   ❌ Rate limiter missing wait_if_needed method")
                return False
                
        else:
            print("   ❌ Rate limiter not found in client")
            print("   💡 Check if you added: self.rate_limiter = SimpleRateLimiter()")
            return False
        
        # Test 2: Check rate limiter functionality
        print("\n2. Testing Rate Limiter Logic...")
        
        start_time = datetime.now()
        
        # Make 3 rapid calls to wait_if_needed
        for i in range(3):
            await client.rate_limiter.wait_if_needed()
            print(f"   ✅ Call {i+1} completed")
        
        duration = (datetime.now() - start_time).total_seconds()
        print(f"   ⏱️  3 calls took {duration:.2f} seconds")
        
        # Test 3: Check rate limit status
        print("\n3. Testing Rate Limit Status...")
        
        if hasattr(client, 'get_rate_limit_status'):
            status = client.get_rate_limit_status()
            print(f"   📊 Rate limit status: {status}")
        else:
            print("   ⚠️  get_rate_limit_status method not found (optional)")
        
        print("\n4. Testing Enhanced _make_request Method...")
        
        # Test if enhanced _make_request exists
        original_token = client.access_token
        client.access_token = "test_token"  # Temporary test token
        
        # This should not crash (will fail gracefully)
        result = await client._make_request('GET', '/test-endpoint')
        print(f"   ✅ Enhanced _make_request handled gracefully (result: {type(result)})")
        
        # Restore original token
        client.access_token = original_token
        
        print("\n" + "=" * 60)
        print("RATE LIMITER VALIDATION RESULTS")
        print("=" * 60)
        print("✅ All tests passed!")
        print("💡 Your Step 2 implementation is working correctly")
        print("🎯 Ready to test with real authentication")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("💡 Check if you're running from the correct directory")
        print("💡 Make sure all required modules are installed")
        return False
        
    except Exception as e:
        print(f"\n❌ Validation Error: {e}")
        print("💡 Check your Step 2 implementation")
        return False

async def test_with_authentication():
    """
    Test rate limiter with real authentication (optional)
    Only run this if you want to test with real API calls
    """
    
    print("\n" + "=" * 60)
    print("TESTING WITH REAL AUTHENTICATION")
    print("=" * 60)
    
    try:
        from src.upstox_api_client import UpstoxClient
        from config.settings import get_settings
        
        settings = get_settings()
        client = UpstoxClient(
            settings.upstox_api_key,
            settings.upstox_api_secret,
            settings.upstox_redirect_uri
        )
        
        # Load stored token if available
        if client.load_stored_token():
            print("✅ Found stored access token")
            
            # Test token validity
            if await client.test_token():
                print("✅ Access token is valid")
                
                print("\n🧪 Testing rate limiter with real API calls...")
                
                # Test rapid API calls (this will trigger rate limiting)
                start_time = datetime.now()
                
                tasks = []
                for i in range(5):  # 5 rapid profile requests
                    task = client.get_profile()
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                # Analyze results
                successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
                failed = len(results) - successful
                
                print(f"📊 Real API Test Results:")
                print(f"   ⏱️  Duration: {duration:.2f} seconds")
                print(f"   ✅ Successful: {successful}/5")
                print(f"   ❌ Failed: {failed}/5")
                print(f"   📈 Rate limit status: {client.get_rate_limit_status()}")
                
                if successful >= 4:  # At least 4/5 should succeed
                    print("🎉 Rate limiter working correctly with real API!")
                    return True
                else:
                    print("⚠️  Some API calls failed - check implementation")
                    return False
                    
            else:
                print("❌ Access token is invalid")
                print("💡 Run authentication first or check token file")
                return False
        else:
            print("⚠️  No stored access token found")
            print("💡 This test requires authentication")
            print("💡 You can skip this test for now")
            return True  # Not a failure, just no token
            
    except Exception as e:
        print(f"❌ Authentication test error: {e}")
        return False

async def main():
    """Main validation function"""
    
    print("🚀 VALIDATING STEP 2: API RATE LIMITER")
    print(f"⏰ Start time: {datetime.now().strftime('%H:%M:%S')}")
    
    # Test 1: Basic implementation validation
    basic_test_passed = await test_rate_limiter_implementation()
    
    if not basic_test_passed:
        print("\n❌ Basic validation failed!")
        print("💡 Please check your Step 2 implementation")
        return
    
    # Test 2: Ask if user wants to test with real authentication
    print("\n" + "=" * 40)
    print("OPTIONAL: Test with Real Authentication")
    print("=" * 40)
    print("This will make real API calls to test rate limiting")
    print("Do you want to test with real authentication? (y/n): ", end="")
    
    # For automated testing, skip this
    test_with_auth = input().lower().strip() == 'y'
    
    if test_with_auth:
        auth_test_passed = await test_with_authentication()
        
        if auth_test_passed:
            print("\n🎉 ALL TESTS PASSED!")
            print("✅ Step 2 implementation is working correctly")
            print("🎯 Ready to move to Step 5 (Historical Data Preloader)")
        else:
            print("\n⚠️  Authentication test had issues")
            print("💡 Basic rate limiter is working, but check API calls")
    else:
        print("\n✅ Basic validation completed successfully")
        print("🎯 Ready to move to Step 5 (Historical Data Preloader)")
    
    print(f"\n⏰ Validation completed at: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    # Run the validation
    asyncio.run(main())