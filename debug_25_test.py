# debug_25_test.py
import asyncio
from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
from src.models.position import Position
from datetime import datetime

async def debug_25_loss():
    config = {'total_capital': 50000}
    strategy = OptionIntegratedPineScript("test", config)
    
    position = Position(
        symbol="TEST",
        quantity=3,
        average_price=50.0,
        current_price=50.0,
        pnl=0.0,
        unrealized_pnl=0.0,
        instrument_key="TEST_KEY"
    )
    
    print("Testing 25% loss scenario...")
    # Test using a public interface (add this method to OptionIntegratedPineScript if not present)
    result = await strategy.check_mandatory_exits(position, 37.5)
    print(f"Method result: {result}")
    print(f"Result type: {type(result)}")
    loss_pct = ((50.0 - 37.5) / 50.0) * 100
    print(f"Loss percentage: {loss_pct}%")
    print(f"Should trigger (>=30%): {loss_pct >= 30}")
    
    # Test the actual method
    result = await strategy._check_mandatory_exits_corrected(position, 37.5)
    print(f"Method result: {result}")
    print(f"Result type: {type(result)}")
asyncio.run(debug_25_loss())

async def check_mandatory_exits(self, position, exit_price):
        return await self._check_mandatory_exits_corrected(position, exit_price)

async def _check_mandatory_exits_corrected(self, position, exit_price):
        # implementation
        pass