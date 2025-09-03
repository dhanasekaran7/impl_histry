# ==================== scripts/test_option_chain_fix.py ====================
"""
Fixed test script for option chain manager
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

def get_token():
    """Get token from bot data"""
    try:
        token_file = project_root / "data" / "access_token.json"
        with open(token_file, 'r') as f:
            data = json.load(f)
            return data.get('access_token')
    except Exception as e:
        print(f"Error loading token: {e}")
        return None

class MockUpstoxClient:
    """Mock upstox client for testing"""
    def __init__(self, token):
        self.access_token = token

async def test_fixed_option_manager():
    """Test the fixed option chain manager"""
    print("🔧 Testing Fixed Option Chain Manager")
    print("=" * 50)
    
    token = get_token()
    if not token:
        print("❌ No token found in data/access_token.json!")
        print("Make sure your bot has been authenticated first.")
        return False
    
    try:
        # Import the fixed option manager
        from src.options.option_chain_manager import OptionChainManager
        
        # Create mock client
        mock_client = MockUpstoxClient(token)
        
        # Test the fixed manager
        manager = OptionChainManager(mock_client)
        
        print("📈 Testing spot price fetching...")
        spot_price = await manager.get_spot_price("NIFTY")
        
        if spot_price:
            print(f"✅ Spot price: Rs.{spot_price:.2f}")
            
            print("\n📋 Testing option chain...")
            option_chain = await manager.get_option_chain("NIFTY", 3)
            
            if option_chain and 'strikes' in option_chain:
                print(f"✅ Option chain loaded: {len(option_chain['strikes'])} strikes")
                print(f"   ATM Strike: {option_chain.get('atm_strike')}")
                print(f"   Expiry: {option_chain.get('expiry_date')}")
                
                # Test a few strikes
                print("\n📊 Sample option prices:")
                for strike, data in list(option_chain['strikes'].items())[:3]:
                    ce_ltp = data['ce'].get('ltp')
                    pe_ltp = data['pe'].get('ltp')
                    print(f"   {strike}: CE=Rs.{ce_ltp if ce_ltp else 'N/A'}, PE=Rs.{pe_ltp if pe_ltp else 'N/A'}")
                
                print("\n🎉 SUCCESS! The option chain manager fix works!")
                print("✅ Your bot should now be able to fetch option prices")
                return True
            else:
                print("❌ Option chain failed - check if market is open")
                return False
        else:
            print("❌ Spot price failed - check your token or market hours")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you've replaced the option_chain_manager.py file")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_main_bot_integration():
    """Test integration with main bot structure"""
    print("\n🔗 Testing Main Bot Integration")
    print("=" * 50)
    
    try:
        # Test importing main bot components
        from src.trading_bot import TradingBot
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        print("✅ Main bot imports successful")
        print("✅ Option strategy import successful")
        print("✅ Integration should work with your main.py")
        
        return True
        
    except ImportError as e:
        print(f"❌ Integration test failed: {e}")
        return False

if __name__ == "__main__":
    async def run_all_tests():
        print("🚀 Running Option Chain Fix Tests")
        print("=" * 60)
        
        # Test 1: Option chain manager
        test1_success = await test_fixed_option_manager()
        
        # Test 2: Integration test
        test2_success = await test_main_bot_integration()
        
        print("\n" + "=" * 60)
        print("📋 TEST RESULTS:")
        print("=" * 60)
        print(f"✅ Option Manager: {'PASS' if test1_success else 'FAIL'}")
        print(f"✅ Bot Integration: {'PASS' if test2_success else 'FAIL'}")
        
        if test1_success and test2_success:
            print("\n🎉 ALL TESTS PASSED!")
            print("Your bot is ready to run with option trading.")
            print("\nNext steps:")
            print("1. Run your main.py")
            print("2. Check for 'Got NIFTY spot price' messages")
            print("3. Monitor option order creation")
        else:
            print("\n⚠️  Some tests failed. Check the errors above.")
    
    asyncio.run(run_all_tests())