# test_exits.py
import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
from src.models.position import Position
from datetime import datetime
from unittest.mock import AsyncMock, Mock

async def test_exit_logic():
    """Standalone exit logic test"""
    print("Testing Exit Logic - AstraRise Bot")
    print("-" * 40)
    
    # Create strategy instance
    config = {
        'total_capital': 50000,
        'risk_per_trade': 15000,
        'adx_length': 14,
        'adx_threshold': 20
    }
    
    strategy = OptionIntegratedPineScript("test", config)
    
    # Mock required methods
    strategy.fetch_option_ltp = AsyncMock(return_value=35.0)
    strategy._cleanup_position_after_exit = AsyncMock()
    
    # Test 1: 30% Stop Loss
    print("1. Testing 30% Stop Loss...")
    position = create_test_position(entry_price=50.0)
    result = await strategy._check_mandatory_exits_corrected(position, 35.0)  # 30% loss
    
    if result and result.exit_reason == "STOP_LOSS_30%":
        print("   ✓ 30% stop loss test PASSED")
    else:
        print("   ✗ 30% stop loss test FAILED")
    
    # Test 2: No Exit Scenario
    print("2. Testing No Exit (25% loss)...")
    result = await strategy._check_mandatory_exits_corrected(position, 37.5)  # 25% loss
    
    if result is None:
        print("   ✓ No exit test PASSED")
    else:
        print("   ✗ No exit test FAILED")
    
    # Test 3: Market Close
    print("3. Testing Market Close...")
    # Mock time to 3:20 PM
    import builtins
    original_datetime = builtins.datetime
    
    class MockDateTime(datetime):
        @classmethod
        def now(cls):
            return original_datetime.now().replace(hour=15, minute=20, second=0)
    
    builtins.datetime = MockDateTime
    
    result = await strategy._check_mandatory_exits_corrected(position, 45.0)
    
    builtins.datetime = original_datetime  # Restore
    
    if result and result.exit_reason == "MARKET_CLOSE":
        print("   ✓ Market close test PASSED")
    else:
        print("   ✗ Market close test FAILED")
    
    print("-" * 40)
    print("Exit logic testing completed!")

def create_test_position(entry_price=50.0):
    """Create test position"""
    position = Position(
        symbol="NIFTY25AUG24550CE",
        quantity=3,
        average_price=entry_price,
        current_price=entry_price,
        pnl=0,
        unrealized_pnl=0,
        instrument_key="TEST"
    )
    position.strike_price = 24550
    position.option_type = "CE"
    return position

if __name__ == "__main__":
    asyncio.run(test_exit_logic())