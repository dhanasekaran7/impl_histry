import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
from src.models.position import Position
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

async def test_exit_logic():
    """Fixed exit logic test with detailed debugging"""
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
    strategy._create_simple_exit_order = Mock(side_effect=create_mock_exit_order)
    
    # Test 0: Check if method exists
    print("0. Checking if exit method exists...")
    if hasattr(strategy, '_check_mandatory_exits_corrected'):
        print("   ✓ Method _check_mandatory_exits_corrected exists")
    else:
        print("   ✗ Method _check_mandatory_exits_corrected MISSING!")
        print("   Available methods:", [m for m in dir(strategy) if 'exit' in m.lower()])
        return
    
    # Test 1: 30% Stop Loss
    print("1. Testing 30% Stop Loss...")
    position = create_test_position(entry_price=50.0)
    
    try:
        result = await strategy._check_mandatory_exits_corrected(position, 35.0)  # 30% loss
        print(f"   Result: {result}")
        
        if result and result.exit_reason == "STOP_LOSS_30%":
            print("   ✓ 30% stop loss test PASSED")
        else:
            print("   ✗ 30% stop loss test FAILED")
    except Exception as e:
        print(f"   ✗ 30% stop loss test ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: No Exit Scenario (should return None)
    print("\n2. Testing No Exit (25% loss)...")
    try:
        result = await strategy._check_mandatory_exits_corrected(position, 37.5)  # 25% loss
        print(f"   Result: {result}")
        
        if result is None:
            print("   ✓ No exit test PASSED")
        else:
            print("   ✗ No exit test FAILED - Should not exit")
    except Exception as e:
        print(f"   ✗ No exit test ERROR: {e}")
    
    # Test 3: Market Close (patched time)
    print("\n3. Testing Market Close...")
    try:
        mock_now = datetime(2025, 8, 29, 15, 20, 0)  # 3:20 PM fixed datetime
        
        with patch.object(strategy, '_get_current_time', return_value=mock_now):
            result = await strategy._check_mandatory_exits_corrected(position, 45.0)
            print(f"   Result: {result}")
            
            if result and result.exit_reason == "MARKET_CLOSE":
                print("   ✓ Market close test PASSED")
            else:
                print("   ✗ Market close test FAILED")
    
    except Exception as e:
        print(f"   ✗ Market close test ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "-" * 40)
    print("Exit logic testing completed!")

def create_mock_exit_order(position, price, reason):
    """Create a mock exit order"""
    mock_order = Mock()
    mock_order.exit_reason = reason
    mock_order.price = price
    mock_order.symbol = position.symbol
    mock_order.quantity = position.quantity
    return mock_order

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

# Alternative simple test function
async def simple_debug_test():
    """Simple test to debug the actual issue"""
    print("Simple Debug Test")
    print("-" * 20)
    
    config = {'total_capital': 50000, 'risk_per_trade': 15000}
    strategy = OptionIntegratedPineScript("test", config)
    
    # Check what methods exist
    exit_methods = [m for m in dir(strategy) if 'exit' in m.lower()]
    print(f"Available exit methods: {exit_methods}")
    
    # Create simple position
    position = create_test_position(50.0)
    
    # Manual check
    entry_price = position.average_price
    current_price = 35.0  # 30% loss
    loss_pct = ((entry_price - current_price) / entry_price) * 100
    print(f"Manual calculation: Loss={loss_pct:.2f}%")
    
    # Call method
    result = await strategy._check_mandatory_exits_corrected(position, 35.0)
    print(f"Method result: {result}")

if __name__ == "__main__":
    # Run both tests
    print("Running simple debug test first...\n")
    asyncio.run(simple_debug_test())
    
    print("\n" + "="*50)
    print("Running full test...\n")
    asyncio.run(test_exit_logic())
