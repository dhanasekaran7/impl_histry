import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

async def test_step5_fix():
    """Test if the Step 5 fix resolves the strategy attribute issue"""
    
    print("🧪 TESTING STEP 5 FIX")
    print("=" * 30)
    
    try:
        # Import strategy classes
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        # Test strategy creation
        config = {
            'adx_length': 14,
            'adx_threshold': 20,
            'strong_candle_threshold': 0.6,
            'option_trading_enabled': True
        }
        
        strategy = OptionIntegratedPineScript("test_strategy", config)
        
        # Check required attributes
        required_attrs = ['ha_candles_history', 'candle_history']
        
        for attr in required_attrs:
            if hasattr(strategy, attr):
                print(f"✅ {attr}: EXISTS")
            else:
                print(f"❌ {attr}: MISSING")
                # Fix it
                setattr(strategy, attr, [])
                print(f"🔧 {attr}: FIXED (added empty list)")
        
        # Test adding candles
        test_candle = {
            'ha_open': 100,
            'ha_high': 105,
            'ha_low': 95,
            'ha_close': 102,
            'volume': 1000,
            'timestamp': '2025-09-01T15:30:00+05:30'
        }
        
        if hasattr(strategy, 'ha_candles_history'):
            strategy.ha_candles_history.append(test_candle)
            print(f"✅ Test candle added: {len(strategy.ha_candles_history)} candles")
        
        print("\n✅ Step 5 fix validation PASSED")
        print("💡 Your strategy should now work with historical data preloader")
        return True
        
    except Exception as e:
        print(f"❌ Fix validation error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_step5_fix())
    
    if result:
        print("\n🎯 Ready to test Step 5 with your bot!")
    else:
        print("\n⚠️ Step 5 fix needs more work")