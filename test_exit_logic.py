# ==================== Exit Logic Testing Framework ====================
import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Optional
from unittest.mock import Mock, AsyncMock
from src.models.order import Order, OrderType, TransactionType
from src.models.position import Position

class ExitLogicTester:
    """Test framework to validate exit logic without live trading"""
    
    def __init__(self, strategy):
        self.strategy = strategy
        self.test_results = []
        self.logger = logging.getLogger(__name__)
        
    async def run_all_tests(self):
        """Run comprehensive exit logic tests"""
        print("=" * 60)
        print("TESTING EXIT LOGIC - AstraRise Trading Bot")
        print("=" * 60)
        
        # Test 1: 30% Stop Loss
        await self.test_stop_loss_exit()
        
        # Test 2: Market Close (Square Off)
        await self.test_market_close_exit()
        
        # Test 3: Pine Script Exit
        await self.test_pine_script_exit()
        
        # Test 4: No Exit Scenarios
        await self.test_no_exit_scenarios()
        
        # Test 5: Error Handling
        await self.test_error_handling()
        
        # Print summary
        self.print_test_summary()
    
    async def test_stop_loss_exit(self):
        """Test 30% stop loss exit logic"""
        print("\n1. TESTING 30% STOP LOSS EXIT")
        print("-" * 40)
        
        # Test Case 1: Exactly 30% loss
        position = self.create_mock_position(entry_price=50.0, current_price=35.0)  # 30% loss
        result = await self.strategy._check_mandatory_exits_corrected(position, 35.0)
        
        if result and result.exit_reason == "STOP_LOSS_30%":
            print("✅ 30% stop loss triggered correctly")
            self.test_results.append(("Stop Loss 30%", "PASS"))
        else:
            print("❌ 30% stop loss failed to trigger")
            self.test_results.append(("Stop Loss 30%", "FAIL"))
        
        # Test Case 2: 35% loss (should trigger)
        position = self.create_mock_position(entry_price=50.0, current_price=32.5)  # 35% loss
        result = await self.strategy._check_mandatory_exits_corrected(position, 32.5)
        
        if result and result.exit_reason == "STOP_LOSS_30%":
            print("✅ 35% loss triggered stop loss correctly")
            self.test_results.append(("Stop Loss 35%", "PASS"))
        else:
            print("❌ 35% loss failed to trigger")
            self.test_results.append(("Stop Loss 35%", "FAIL"))
        
        # Test Case 3: 25% loss (should NOT trigger)
        position = self.create_mock_position(entry_price=50.0, current_price=37.5)  # 25% loss
        result = await self.strategy._check_mandatory_exits_corrected(position, 37.5)
        
        if result is None:
            print("✅ 25% loss correctly did NOT trigger")
            self.test_results.append(("Stop Loss 25% (no trigger)", "PASS"))
        else:
            print("❌ 25% loss incorrectly triggered")
            self.test_results.append(("Stop Loss 25% (no trigger)", "FAIL"))
    
    async def test_market_close_exit(self):
        """Test market close (square off) exit logic"""
        print("\n2. TESTING MARKET CLOSE (SQUARE OFF) EXIT")
        print("-" * 40)
        
        # Mock current time to 3:20 PM
        original_datetime = datetime
        
        class MockDateTime(datetime):
            @classmethod
            def now(cls):
                mock_time = original_datetime.now().replace(hour=15, minute=20, second=0)
                return mock_time
        
        # Temporarily replace datetime
        import builtins
        builtins.datetime = MockDateTime
        
        position = self.create_mock_position(entry_price=50.0, current_price=55.0)
        result = await self.strategy._check_mandatory_exits_corrected(position, 55.0)
        
        # Restore original datetime
        builtins.datetime = original_datetime
        
        if result and result.exit_reason == "MARKET_CLOSE":
            print("✅ Market close (3:20 PM) triggered correctly")
            self.test_results.append(("Market Close", "PASS"))
        else:
            print("❌ Market close failed to trigger")
            self.test_results.append(("Market Close", "FAIL"))
    
    async def test_pine_script_exit(self):
        """Test Pine Script exit logic"""
        print("\n3. TESTING PINE SCRIPT EXIT LOGIC")
        print("-" * 40)
        
        # Mock the parent strategy's should_exit method
        mock_pine_exit = Order(
            symbol="NIFTY25AUG24550CE",
            quantity=3,
            price=45.0,
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.SELL,
            strategy_name="test"
        )
        mock_pine_exit.exit_reason = "STRONG_RED_CANDLE"
        
        # Mock super().should_exit to return pine script exit
        async def mock_super_should_exit(position, market_data):
            return mock_pine_exit
        
        # Temporarily replace the parent method
        original_method = self.strategy.__class__.__bases__[0].should_exit
        self.strategy.__class__.__bases__[0].should_exit = mock_super_should_exit
        
        position = self.create_mock_position(entry_price=50.0, current_price=45.0)
        market_data = {"ha_candle": {"ha_close": 24500}}
        
        # Mock fetch_option_ltp to return current price
        self.strategy.fetch_option_ltp = AsyncMock(return_value=45.0)
        
        result = await self.strategy.should_exit(position, market_data)
        
        # Restore original method
        self.strategy.__class__.__bases__[0].should_exit = original_method
        
        if result and hasattr(result, 'exit_reason') and result.exit_reason == "STRONG_RED_CANDLE":
            print("✅ Pine Script exit triggered correctly")
            self.test_results.append(("Pine Script Exit", "PASS"))
        else:
            print("❌ Pine Script exit failed")
            self.test_results.append(("Pine Script Exit", "FAIL"))
    
    async def test_no_exit_scenarios(self):
        """Test scenarios where no exit should be triggered"""
        print("\n4. TESTING NO EXIT SCENARIOS")
        print("-" * 40)
        
        # Test Case 1: Profitable position, no Pine Script signal
        position = self.create_mock_position(entry_price=50.0, current_price=55.0)  # 10% profit
        market_data = {"ha_candle": {"ha_close": 24500}}
        
        # Mock no Pine Script exit
        async def mock_no_exit(position, market_data):
            return None
        
        original_method = self.strategy.__class__.__bases__[0].should_exit
        self.strategy.__class__.__bases__[0].should_exit = mock_no_exit
        
        result = await self.strategy.should_exit(position, market_data)
        
        # Restore original method
        self.strategy.__class__.__bases__[0].should_exit = original_method
        
        if result is None:
            print("✅ No exit correctly when profitable and no Pine Script signal")
            self.test_results.append(("No Exit (Profitable)", "PASS"))
        else:
            print("❌ Incorrect exit when should continue")
            self.test_results.append(("No Exit (Profitable)", "FAIL"))
    
    async def test_error_handling(self):
        """Test error handling in exit logic"""
        print("\n5. TESTING ERROR HANDLING")
        print("-" * 40)
        
        # Test with invalid position data
        try:
            position = Position(
                symbol="INVALID",
                quantity=0,
                average_price=0,  # Invalid price
                current_price=0,
                pnl=0,
                unrealized_pnl=0
            )
            
            result = await self.strategy._check_mandatory_exits_corrected(position, 0)
            
            print("✅ Error handling works - no crash with invalid data")
            self.test_results.append(("Error Handling", "PASS"))
            
        except Exception as e:
            print(f"❌ Error handling failed: {e}")
            self.test_results.append(("Error Handling", "FAIL"))
    
    def create_mock_position(self, entry_price: float, current_price: float) -> Position:
        """Create mock position for testing"""
        position = Position(
            symbol="NIFTY25AUG24550CE",
            quantity=3,
            average_price=entry_price,
            current_price=current_price,
            pnl=0,
            unrealized_pnl=0,
            instrument_key="NSE_FO|TEST"
        )
        
        # Add option-specific attributes
        position.strike_price = 24550
        position.option_type = "CE"
        position.entry_time = datetime.now()
        
        return position
    
    def print_test_summary(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 60)
        print("EXIT LOGIC TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, result in self.test_results if result == "PASS")
        failed = sum(1 for _, result in self.test_results if result == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        print("\nDetailed Results:")
        print("-" * 40)
        for test_name, result in self.test_results:
            status = "✅" if result == "PASS" else "❌"
            print(f"{status} {test_name}: {result}")
        
        if failed == 0:
            print("\n🎉 ALL TESTS PASSED! Your exit logic is working correctly.")
        else:
            print(f"\n⚠️  {failed} tests failed. Review the implementation.")

# Usage function
async def test_exit_logic(strategy):
    """Run exit logic tests on your strategy"""
    tester = ExitLogicTester(strategy)
    await tester.run_all_tests()

# Integration with your bot - add this to your main.py for testing
async def run_exit_tests():
    """Test function to run before market hours"""
    try:
        # Import your strategy
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        # Create test config
        test_config = {
            'strategy_id': 'ExitLogicTest',
            'adx_length': 14,
            'adx_threshold': 20,
            'total_capital': 50000,
            'risk_per_trade': 15000
        }
        
        # Create strategy instance
        strategy = OptionIntegratedPineScript("exit_test", test_config)
        
        # Mock required methods
        strategy.fetch_option_ltp = AsyncMock(return_value=45.0)
        strategy._cleanup_position_after_exit = AsyncMock()
        strategy._create_simple_exit_order = Mock(side_effect=lambda pos, price, reason: Mock(exit_reason=reason))
        
        # Run tests
        await test_exit_logic(strategy)
        
    except Exception as e:
        print(f"Test setup error: {e}")

if __name__ == "__main__":
    # Run tests
    asyncio.run(run_exit_tests())