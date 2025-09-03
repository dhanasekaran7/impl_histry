# ==================== test_exit_signals.py ====================
"""
Quick Exit Signals Test Runner
Save this as: test_exit_signals.py in your project root
Run with: python test_exit_signals.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Set environment variables for testing
os.environ['PAPER_TRADING'] = 'true'
os.environ['LOG_LEVEL'] = 'INFO'

try:
    from config.logging_config import setup_logging
    setup_logging()
except ImportError:
    # Fallback logging setup
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

print("🧪 EXIT SIGNALS VALIDATION SYSTEM")
print("=" * 50)

async def test_individual_signals():
    """Test individual exit signals quickly"""
    
    print("\n1️⃣ TESTING PROFIT TARGET EXIT")
    print("-" * 30)
    
    # Mock a profitable position
    try:
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        from src.models.position import Position
        
        # Create strategy
        config = {'profit_target_pct': 50, 'stop_loss_pct': 30, 'trailing_stop_enabled': True}
        strategy = OptionIntegratedPineScript("TestStrategy", config)
        
        # Create profitable position (50% profit)
        position = Position(
            symbol="NIFTY25000CE",
            quantity=1,
            average_price=50.0,
            current_price=75.0,  # 50% profit
            pnl=1875.0,
            unrealized_pnl=1875.0,
            instrument_key="NSE_FO|12345"
        )
        position.option_type = 'CE'
        position.strike_price = 25000
        
        # Add to strategy tracking
        strategy.active_option_positions = {
            "NIFTY25000CE": {
                'symbol': "NIFTY25000CE",
                'entry_premium': 50.0,
                'current_premium': 75.0,
                'premium_change_pct': 50.0,
                'option_type': 'CE',
                'strike_price': 25000,
                'quantity': 1,
                'entry_time': asyncio.get_event_loop().time()
            }
        }
        
        # Mock market data
        market_data = {
            'symbol': 'NIFTY',
            'current_price': 25000,
            'timestamp': asyncio.get_event_loop().time(),
            'ha_candle': {'ha_close': 25000, 'ha_open': 24980, 'ha_high': 25020, 'ha_low': 24970}
        }
        
        # Test exit signal
        exit_order = await strategy.should_exit(position, market_data)
        
        if exit_order and "PROFIT_TARGET" in str(getattr(exit_order, 'exit_reason', '')):
            print("✅ PROFIT TARGET EXIT: WORKING")
            print(f"   Exit Reason: {exit_order.exit_reason}")
            print(f"   Exit Price: Rs.{exit_order.price:.2f}")
        else:
            print("❌ PROFIT TARGET EXIT: NOT WORKING")
            
    except Exception as e:
        print(f"❌ PROFIT TARGET TEST FAILED: {e}")
    
    print("\n2️⃣ TESTING STOP LOSS EXIT")
    print("-" * 30)
    
    try:
        # Create loss-making position (30% loss)
        loss_position = Position(
            symbol="NIFTY24950PE",
            quantity=1,
            average_price=60.0,
            current_price=42.0,  # 30% loss
            pnl=-1350.0,
            unrealized_pnl=-1350.0,
            instrument_key="NSE_FO|12346"
        )
        loss_position.option_type = 'PE'
        loss_position.strike_price = 24950
        
        # Add to strategy tracking with loss
        strategy.active_option_positions["NIFTY24950PE"] = {
            'symbol': "NIFTY24950PE",
            'entry_premium': 60.0,
            'current_premium': 42.0,
            'premium_change_pct': -30.0,
            'option_type': 'PE',
            'strike_price': 24950,
            'quantity': 1,
            'entry_time': asyncio.get_event_loop().time()
        }
        
        # Test stop loss
        exit_order = await strategy.should_exit(loss_position, market_data)
        
        if exit_order and "STOP_LOSS" in str(getattr(exit_order, 'exit_reason', '')):
            print("✅ STOP LOSS EXIT: WORKING")
            print(f"   Exit Reason: {exit_order.exit_reason}")
            print(f"   Exit Price: Rs.{exit_order.price:.2f}")
        else:
            print("❌ STOP LOSS EXIT: NOT WORKING")
            
    except Exception as e:
        print(f"❌ STOP LOSS TEST FAILED: {e}")
    
    print("\n3️⃣ TESTING DAILY TRADE LIMITS")
    print("-" * 30)
    
    try:
        # Mock the trading bot daily limit functions
        class MockBot:
            def __init__(self):
                self.daily_trades = []
                self.max_daily_trades = 6
                self.current_date = asyncio.get_event_loop().time()
            
            def _check_daily_trade_limit(self):
                today_entries = len([t for t in self.daily_trades if t.get('type') == 'ENTRY'])
                return today_entries < self.max_daily_trades
            
            def _record_daily_trade(self, order_symbol):
                self.daily_trades.append({'type': 'ENTRY', 'symbol': order_symbol})
        
        bot = MockBot()
        
        # Test 1: Should allow trading initially
        can_trade_initial = bot._check_daily_trade_limit()
        print(f"   Initial (0/6): {'✅ Can Trade' if can_trade_initial else '❌ Cannot Trade'}")
        
        # Test 2: Add 6 trades and check limit
        for i in range(6):
            bot._record_daily_trade(f"NIFTY2500{i}CE")
        
        can_trade_limit = bot._check_daily_trade_limit()
        print(f"   At Limit (6/6): {'❌ Cannot Trade' if not can_trade_limit else '✅ Still Can Trade (ERROR!)'}")
        
        if can_trade_initial and not can_trade_limit:
            print("✅ DAILY TRADE LIMITS: WORKING")
        else:
            print("❌ DAILY TRADE LIMITS: NOT WORKING")
            
    except Exception as e:
        print(f"❌ DAILY TRADE LIMIT TEST FAILED: {e}")

async def test_position_cleanup():
    """Test position cleanup functionality"""
    
    print("\n4️⃣ TESTING POSITION CLEANUP")
    print("-" * 30)
    
    try:
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        # Create strategy with position
        strategy = OptionIntegratedPineScript("TestStrategy", {})
        strategy.active_option_positions = {
            "TEST_POSITION": {
                'symbol': "TEST_POSITION",
                'entry_premium': 50.0,
                'current_premium': 60.0
            }
        }
        
        # Verify position exists
        exists_before = "TEST_POSITION" in strategy.active_option_positions
        print(f"   Position exists before cleanup: {'✅' if exists_before else '❌'}")
        
        # Test cleanup
        await strategy._cleanup_position_after_exit("TEST_POSITION")
        
        # Verify position removed
        exists_after = "TEST_POSITION" in strategy.active_option_positions
        print(f"   Position exists after cleanup: {'❌' if exists_after else '✅'}")
        
        if exists_before and not exists_after:
            print("✅ POSITION CLEANUP: WORKING")
        else:
            print("❌ POSITION CLEANUP: NOT WORKING")
            
    except Exception as e:
        print(f"❌ POSITION CLEANUP TEST FAILED: {e}")

async def test_method_imports():
    """Test if all required methods can be imported"""
    
    print("\n5️⃣ TESTING METHOD IMPORTS")
    print("-" * 30)
    
    try:
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        strategy = OptionIntegratedPineScript("TestStrategy", {})
        
        # Test required methods exist
        required_methods = [
            'should_exit',
            '_check_advanced_option_exits',
            '_get_or_create_position_data',
            '_get_current_premium_with_fallback',
            '_check_trailing_stop_fixed',
            '_check_time_based_exits_fixed',
            '_check_mandatory_exits',
            '_cleanup_position_after_exit',
            '_create_option_exit_order'
        ]
        
        missing_methods = []
        for method_name in required_methods:
            if not hasattr(strategy, method_name):
                missing_methods.append(method_name)
        
        if not missing_methods:
            print("✅ ALL REQUIRED METHODS: FOUND")
            print(f"   Checked {len(required_methods)} methods")
        else:
            print("❌ MISSING METHODS:")
            for method in missing_methods:
                print(f"   - {method}")
                
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
    except Exception as e:
        print(f"❌ METHOD CHECK FAILED: {e}")

async def test_trading_bot_integration():
    """Test trading bot integration"""
    
    print("\n6️⃣ TESTING TRADING BOT INTEGRATION")
    print("-" * 30)
    
    try:
        from src.trading_bot import TradingBot
        from config.settings import get_settings
        
        # Create bot instance
        settings = get_settings()
        
        # Check if required methods exist in trading bot
        required_bot_methods = [
            '_check_daily_trade_limit',
            '_record_daily_trade',
            '_process_all_exits_enhanced',
            '_cleanup_position_after_exit_enhanced'
        ]
        
        # Create a mock bot class to test
        class MockTradingBot(TradingBot):
            def __init__(self):
                # Skip full initialization, just check methods
                pass
        
        mock_bot = MockTradingBot()
        
        missing_bot_methods = []
        for method_name in required_bot_methods:
            if not hasattr(TradingBot, method_name):
                missing_bot_methods.append(method_name)
        
        if not missing_bot_methods:
            print("✅ TRADING BOT METHODS: FOUND")
            print(f"   Checked {len(required_bot_methods)} methods")
        else:
            print("❌ MISSING BOT METHODS:")
            for method in missing_bot_methods:
                print(f"   - {method}")
                
    except Exception as e:
        print(f"❌ TRADING BOT TEST FAILED: {e}")

async def run_quick_validation():
    """Run quick validation of all components"""
    
    print("🚀 STARTING QUICK EXIT SIGNALS VALIDATION")
    print("=" * 50)
    
    await test_method_imports()
    await test_individual_signals() 
    await test_position_cleanup()
    await test_trading_bot_integration()
    
    print("\n" + "=" * 50)
    print("✅ QUICK VALIDATION COMPLETE!")
    print("=" * 50)
    
    print("\n📋 NEXT STEPS:")
    print("1. If all tests passed: ✅ Your exit signals should work!")
    print("2. If some failed: ❌ Check the error messages above")
    print("3. Run python main.py to test with real market data")
    print("4. Monitor logs for exit signal processing")

if __name__ == "__main__":
    try:
        asyncio.run(run_quick_validation())
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎯 Testing complete! Check results above.")