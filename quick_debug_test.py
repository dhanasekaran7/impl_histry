# quick_debug_test.py
import asyncio
from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
from src.models.position import Position

async def debug_test():
    config = {'total_capital': 50000, 'risk_per_trade': 15000}
    strategy = OptionIntegratedPineScript("test", config)
    
    # Create position with correct arguments
    position = Position(
        symbol="TEST",
        quantity=2,
        average_price=50.0,
        current_price=34.0,
        pnl=0,
        unrealized_pnl=0,
        instrument_key="TEST_KEY"
    )
    
    # Test 1: 32% loss (should trigger stop loss)
    result = await strategy._check_mandatory_exits_corrected(position, 34.0)
    print(f"32% loss test: {result.exit_reason if result else 'No exit'}")
    if result:
        print(f"  P&L: Rs.{result.total_pnl:.2f} ({result.pnl_pct:.1f}%)")
    
    # Test 2: 25% loss (should NOT trigger)
    result = await strategy._check_mandatory_exits_corrected(position, 37.5)
    print(f"25% loss test: {result.exit_reason if result else 'No exit'}")
    
    # Test 3: Profit scenario (should NOT trigger stop loss)
    result = await strategy._check_mandatory_exits_corrected(position, 65.0)
    print(f"Profit test: {result.exit_reason if result else 'No exit'}")

asyncio.run(debug_test())