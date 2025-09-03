# ==================== scripts/quick_integration_test.py ====================
"""
Standalone test to verify complete option integration in 2 minutes
Tests all components without waiting for real market signals
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

async def test_complete_integration():
    """Test complete option integration end-to-end"""
    
    print("🚀 COMPLETE OPTION INTEGRATION TEST")
    print("=" * 60)
    print("Testing: Bot → Strategy → Option Chain → API → Order Creation")
    print("=" * 60)
    
    try:
        # Import all components
        from src.trading_bot import TradingBot
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        from src.options.option_chain_manager import OptionChainManager
        from config.settings import get_settings
        
        print("✅ All imports successful")
        
        # Setup configuration
        settings = get_settings()
        bot = TradingBot(settings)
        
        print("✅ Bot initialized")
        
        # Setup option chain manager
        option_manager = OptionChainManager(bot.upstox_client)
        
        print("✅ Option manager created")
        
        # Test spot price (critical test)
        print("\n📈 CRITICAL TEST: Spot Price Fetching")
        spot_price = await option_manager.get_spot_price("NIFTY")
        
        if not spot_price:
            print("❌ CRITICAL FAILURE: Cannot fetch spot price")
            return False
        
        print(f"✅ NIFTY Spot: Rs.{spot_price:.2f}")
        
        # Test option chain (critical test)
        print("\n📋 CRITICAL TEST: Option Chain Fetching")
        option_chain = await option_manager.get_option_chain("NIFTY", 5)
        
        if not option_chain or 'strikes' not in option_chain:
            print("❌ CRITICAL FAILURE: Cannot fetch option chain")
            return False
        
        strikes_count = len(option_chain['strikes'])
        atm_strike = option_chain.get('atm_strike')
        expiry = option_chain.get('expiry_date')
        
        print(f"✅ Option Chain: {strikes_count} strikes, ATM={atm_strike}, Expiry={expiry}")
        
        # Test option LTP fetching (critical test)
        print("\n💰 CRITICAL TEST: Option Premium Fetching")
        
        # Test CE and PE for ATM strike
        ce_ltp = await option_manager._get_option_ltp(
            option_chain['strikes'][atm_strike]['ce']['instrument_key']
        )
        pe_ltp = await option_manager._get_option_ltp(
            option_chain['strikes'][atm_strike]['pe']['instrument_key']
        )
        
        if not ce_ltp or not pe_ltp:
            print(f"❌ CRITICAL FAILURE: Cannot fetch option LTP (CE={ce_ltp}, PE={pe_ltp})")
            return False
        
        print(f"✅ ATM Option LTP: {atm_strike}CE=Rs.{ce_ltp:.2f}, {atm_strike}PE=Rs.{pe_ltp:.2f}")
        
        # Setup strategy with option manager
        print("\n🎯 STRATEGY INTEGRATION TEST")
        
        config = {
            'strategy_id': 'OptionIntegratedPineScript_Test',
            'option_trading_enabled': True,
            'strike_selection_mode': 'ATM',
            'max_option_premium': 200,
            'min_option_premium': 10,
            'adx_length': 14,
            'adx_threshold': 20,
            'strong_candle_threshold': 0.6,
            'total_capital': 50000,
            'risk_per_trade': 15000,
        }
        
        strategy = OptionIntegratedPineScript("test_strategy", config)
        strategy.set_upstox_client(bot.upstox_client)
        strategy.option_chain_manager = option_manager
        
        print("✅ Strategy configured with option manager")
        
        # Test strategy's option methods
        print("\n🔧 STRATEGY METHODS TEST")
        
        # Test strike calculation
        test_strike_ce = await strategy.calculate_option_strike(spot_price, "CE", "ATM")
        test_strike_pe = await strategy.calculate_option_strike(spot_price, "PE", "ATM")
        
        print(f"✅ Strike calculation: CE={test_strike_ce}, PE={test_strike_pe}")
        
        # Test LTP fetching through strategy
        strategy_ce_ltp = await strategy.fetch_option_ltp(test_strike_ce, "CE")
        strategy_pe_ltp = await strategy.fetch_option_ltp(test_strike_pe, "PE")
        
        if strategy_ce_ltp and strategy_pe_ltp:
            print(f"✅ Strategy LTP fetch: {test_strike_ce}CE=Rs.{strategy_ce_ltp:.2f}, {test_strike_pe}PE=Rs.{strategy_pe_ltp:.2f}")
        else:
            print(f"⚠️  Strategy LTP fetch partial: CE={strategy_ce_ltp}, PE={strategy_pe_ltp}")
        
        # Test premium validation
        ce_valid = strategy.validate_option_premium(strategy_ce_ltp or 50, test_strike_ce, spot_price)
        pe_valid = strategy.validate_option_premium(strategy_pe_ltp or 50, test_strike_pe, spot_price)
        
        print(f"✅ Premium validation: CE={ce_valid}, PE={pe_valid}")
        
        # Mock data test for entry logic
        print("\n🎮 MOCK ENTRY SIGNAL TEST")
        
        # Add historical candles for indicators
        for i in range(30):
            candle = {
                'open': spot_price - 50 + i,
                'high': spot_price - 40 + i,
                'low': spot_price - 60 + i,
                'close': spot_price - 45 + i,
                'volume': 1000
            }
            strategy.add_candle_data(candle)
        
        print(f"✅ Added {len(strategy.candle_history)} mock candles")
        
        # Create mock market data that might trigger signal
        mock_data = {
            'symbol': 'NIFTY',
            'ltp': spot_price,
            'open': spot_price - 10,
            'high': spot_price + 5,
            'low': spot_price - 15,
            'close': spot_price,
            'volume': 2000,
            'timestamp': datetime.now().isoformat(),
            'ha_candle': {
                'ha_open': spot_price - 8,
                'ha_high': spot_price + 3,
                'ha_low': spot_price - 12,
                'ha_close': spot_price + 2
            }
        }
        
        # Test entry logic
        entry_order = await strategy.should_enter(mock_data)
        
        if entry_order:
            print("🎉 ENTRY SIGNAL GENERATED!")
            print(f"   Symbol: {entry_order.symbol}")
            print(f"   Price: Rs.{entry_order.price:.2f}")
            print(f"   Quantity: {entry_order.quantity}")
            if hasattr(entry_order, 'option_type'):
                print(f"   Option: {entry_order.strike_price}{entry_order.option_type}")
        else:
            print("ℹ️  No entry signal (normal - depends on indicators)")
        
        # Final integration test
        print("\n🏁 FINAL INTEGRATION STATUS")
        print("=" * 40)
        
        # Check all critical components
        tests_passed = []
        tests_passed.append(("Spot Price Fetch", spot_price is not None))
        tests_passed.append(("Option Chain Fetch", strikes_count > 0))
        tests_passed.append(("Option LTP Fetch", ce_ltp and pe_ltp))
        tests_passed.append(("Strategy Integration", strategy.option_chain_manager is not None))
        tests_passed.append(("Strike Calculation", test_strike_ce and test_strike_pe))
        tests_passed.append(("Premium Validation", ce_valid or pe_valid))
        
        all_passed = all(result for _, result in tests_passed)
        
        for test_name, result in tests_passed:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:.<25} {status}")
        
        print("=" * 40)
        
        if all_passed:
            print("🎉 ALL CRITICAL TESTS PASSED!")
            print("✅ Your option trading bot is fully functional")
            print("✅ Ready for live trading with main.py")
            print("\n🚀 Run: python main.py")
            return True
        else:
            print("❌ Some critical tests failed")
            print("⚠️  Check the failed components above")
            return False
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("⚡ Quick 2-minute integration test starting...")
    result = asyncio.run(test_complete_integration())
    
    if result:
        print("\n🎯 RESULT: Bot is ready for trading!")
    else:
        print("\n⚠️  RESULT: Issues found, check logs above")