# ==================== simple_exit_test.py ====================
"""
Simple Exit Signals Test - Fixed for Your Project Structure
Save this as: simple_exit_test.py in project root (D:\cla_trailbot-main\)
Run with: python simple_exit_test.py
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# FIXED: Add your project structure to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"

print(f"🔍 Project Root: {project_root}")
print(f"🔍 Src Path: {src_path}")
print(f"🔍 Src Exists: {src_path.exists()}")

# Add paths
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))

# Set environment for testing
os.environ['PAPER_TRADING'] = 'true'
os.environ['LOG_LEVEL'] = 'INFO'

print("\n🧪 SIMPLE EXIT SIGNALS TEST")
print("=" * 50)

async def test_basic_imports():
    """Test if we can import the basic modules"""
    print("\n1️⃣ TESTING BASIC IMPORTS")
    print("-" * 30)
    
    try:
        # Test Position model import
        from models.position import Position
        print("✅ Position model: IMPORTED")
        
        # Test Order model import  
        from models.order import Order, OrderType, TransactionType
        print("✅ Order model: IMPORTED")
        
        return True
        
    except ImportError as e:
        print(f"❌ Basic imports failed: {e}")
        return False

async def test_strategy_import():
    """Test strategy import"""
    print("\n2️⃣ TESTING STRATEGY IMPORT")
    print("-" * 30)
    
    try:
        from strategy.option_integrated_pine_script import OptionIntegratedPineScript
        print("✅ OptionIntegratedPineScript: IMPORTED")
        
        # Test strategy creation
        config = {
            'profit_target_pct': 50,
            'stop_loss_pct': 30,
            'trailing_stop_enabled': True
        }
        strategy = OptionIntegratedPineScript("TestStrategy", config)
        print("✅ Strategy instance: CREATED")
        
        return strategy
        
    except ImportError as e:
        print(f"❌ Strategy import failed: {e}")
        return None

async def test_strategy_methods(strategy):
    """Test if strategy has required methods"""
    print("\n3️⃣ TESTING STRATEGY METHODS")
    print("-" * 30)
    
    if not strategy:
        print("❌ No strategy to test")
        return False
    
    # List of required methods
    required_methods = [
        'should_exit',
        '_check_advanced_option_exits',
        '_get_or_create_position_data', 
        '_get_current_premium_with_fallback',
        '_cleanup_position_after_exit',
        '_create_option_exit_order'
    ]
    
    missing_methods = []
    found_methods = []
    
    for method_name in required_methods:
        if hasattr(strategy, method_name):
            found_methods.append(method_name)
            print(f"✅ {method_name}: FOUND")
        else:
            missing_methods.append(method_name)
            print(f"❌ {method_name}: MISSING")
    
    print(f"\n📊 Methods Status: {len(found_methods)}/{len(required_methods)} found")
    
    if missing_methods:
        print("\n🚨 MISSING METHODS - You need to add these:")
        for method in missing_methods:
            print(f"   - {method}")
        return False
    else:
        print("✅ ALL REQUIRED METHODS: FOUND")
        return True

async def test_mock_exit_signal(strategy):
    """Test a simple exit signal"""
    print("\n4️⃣ TESTING MOCK EXIT SIGNAL")
    print("-" * 30)
    
    if not strategy:
        print("❌ No strategy to test")
        return False
    
    try:
        # Import Position here after we know imports work
        from models.position import Position
        
        # Create a mock profitable position
        position = Position(
            symbol="NIFTY25000CE",
            quantity=1,
            average_price=50.0,  # Entry price
            current_price=75.0,  # Current price (50% profit)
            pnl=1875.0,
            unrealized_pnl=1875.0,
            instrument_key="NSE_FO|12345"
        )
        
        # Add option attributes
        position.option_type = 'CE'
        position.strike_price = 25000
        position.entry_time = datetime.now() - timedelta(hours=2)
        
        print(f"📊 Mock Position: {position.symbol}")
        print(f"   Entry: Rs.{position.average_price}")
        print(f"   Current: Rs.{position.current_price}")
        print(f"   Profit: {((position.current_price - position.average_price) / position.average_price) * 100:.1f}%")
        
        # Add position to strategy tracking (simulate active position)
        if not hasattr(strategy, 'active_option_positions'):
            strategy.active_option_positions = {}
        
        strategy.active_option_positions[position.symbol] = {
            'symbol': position.symbol,
            'entry_premium': position.average_price,
            'current_premium': position.current_price,
            'premium_change_pct': 50.0,  # 50% profit
            'option_type': 'CE',
            'strike_price': 25000,
            'quantity': 1,
            'entry_time': position.entry_time
        }
        
        # Create mock market data
        market_data = {
            'symbol': 'NIFTY',
            'current_price': 25000,
            'timestamp': datetime.now(),
            'ha_candle': {
                'ha_open': 24980,
                'ha_high': 25020, 
                'ha_low': 24970,
                'ha_close': 25000
            }
        }
        
        print("📈 Testing exit signal...")
        
        # Test the exit signal
        exit_order = await strategy.should_exit(position, market_data)
        
        if exit_order:
            exit_reason = getattr(exit_order, 'exit_reason', 'UNKNOWN')
            exit_price = getattr(exit_order, 'price', 0)
            print(f"✅ EXIT SIGNAL TRIGGERED!")
            print(f"   Reason: {exit_reason}")
            print(f"   Exit Price: Rs.{exit_price:.2f}")
            return True
        else:
            print("❌ NO EXIT SIGNAL (This might be normal if methods aren't fully implemented)")
            return False
            
    except Exception as e:
        print(f"❌ Exit signal test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_trading_bot():
    """Test trading bot import"""
    print("\n5️⃣ TESTING TRADING BOT")
    print("-" * 30)
    
    try:
        from trading_bot import TradingBot
        print("✅ TradingBot: IMPORTED")
        
        # Check if daily limit methods exist
        bot_methods = [
            '_check_daily_trade_limit',
            '_record_daily_trade',
            '_process_all_exits_enhanced'
        ]
        
        missing_bot_methods = []
        for method_name in bot_methods:
            if hasattr(TradingBot, method_name):
                print(f"✅ {method_name}: FOUND")
            else:
                missing_bot_methods.append(method_name)
                print(f"❌ {method_name}: MISSING")
        
        if missing_bot_methods:
            print("\n🚨 MISSING BOT METHODS:")
            for method in missing_bot_methods:
                print(f"   - {method}")
            return False
        else:
            print("✅ ALL BOT METHODS: FOUND")
            return True
            
    except ImportError as e:
        print(f"❌ TradingBot import failed: {e}")
        return False

async def run_simple_test():
    """Run simple validation test"""
    
    print("🚀 STARTING SIMPLE EXIT SIGNALS TEST")
    
    # Track test results
    results = {}
    
    # Test 1: Basic imports
    results['imports'] = await test_basic_imports()
    
    # Test 2: Strategy import
    strategy = await test_strategy_import()
    results['strategy_import'] = strategy is not None
    
    # Test 3: Strategy methods
    results['strategy_methods'] = await test_strategy_methods(strategy)
    
    # Test 4: Mock exit signal
    results['exit_signal'] = await test_mock_exit_signal(strategy)
    
    # Test 5: Trading bot
    results['trading_bot'] = await test_trading_bot()
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name.replace('_', ' ').title()}: {'PASSED' if result else 'FAILED'}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Your exit signals should work!")
    elif passed >= 3:
        print("👍 MOSTLY WORKING! Fix the failing tests and you're good!")
    else:
        print("⚠️  NEEDS WORK! Several issues to fix before exit signals will work.")
    
    print("\n📋 NEXT STEPS:")
    if not results['imports']:
        print("1. ❌ Fix import issues - check your project structure")
    if not results['strategy_methods']:
        print("2. ❌ Add missing strategy methods to option_integrated_pine_script.py")
    if not results['trading_bot']:
        print("3. ❌ Add missing methods to trading_bot.py")
    if passed == total:
        print("1. ✅ Run python main.py to test with real data")
        print("2. ✅ Monitor logs for exit signal processing")

if __name__ == "__main__":
    try:
        asyncio.run(run_simple_test())
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎯 Testing complete!")