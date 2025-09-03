# test_pnl_fix.py
import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
from src.models.position import Position
from src.models.order import Order, OrderType, TransactionType
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

class PnLTestValidator:
    """Test P&L calculations after Pine Script fix"""
    
    def __init__(self):
        self.test_results = []
        self.strategy = None
        
    async def run_all_tests(self):
        """Run comprehensive P&L validation tests"""
        print("=" * 60)
        print("P&L CALCULATION VALIDATION - After Pine Script Fix")
        print("=" * 60)
        
        await self.setup_strategy()
        
        # Test scenarios
        await self.test_profitable_exit()
        await self.test_loss_exit()  
        await self.test_pine_script_exit_pnl()
        await self.test_mandatory_exit_pnl()
        await self.test_realistic_scenarios()
        
        self.print_results()
    
    async def setup_strategy(self):
        """Setup strategy with mocks"""
        config = {
            'total_capital': 50000,
            'risk_per_trade': 15000,
            'adx_length': 14,
            'adx_threshold': 20
        }
        
        self.strategy = OptionIntegratedPineScript("test", config)
        
        # Mock methods
        self.strategy.fetch_option_ltp = AsyncMock()
        self.strategy._cleanup_position_after_exit = AsyncMock()
        
    async def test_profitable_exit(self):
        """Test profitable option trade P&L"""
        print("\n1. TESTING PROFITABLE EXIT P&L")
        print("-" * 40)
        
        # Create position: Buy at Rs.50, Exit at Rs.65 (30% profit)
        position = self.create_test_position(
            entry_price=50.0,
            current_price=65.0,
            quantity=2,  # 2 lots = 150 shares
            symbol="NIFTY25SEP24550CE"
        )
        
        # Mock fetch_option_ltp to return exit premium
        self.strategy.fetch_option_ltp.return_value = 65.0
        
        # Test mandatory exit P&L calculation
        result = await self.strategy._check_mandatory_exits_corrected(position, 65.0)
        
        if result:
            # Verify P&L calculations
            expected_pnl_per_share = 65.0 - 50.0  # Rs.15 profit per share
            expected_total_pnl = 15.0 * 2 * 75    # Rs.2,250 total profit
            expected_pnl_pct = 30.0                # 30% profit
            
            actual_pnl = getattr(result, 'total_pnl', 0)
            actual_pct = getattr(result, 'pnl_pct', 0)
            
            print(f"Entry: Rs.50.00 | Exit: Rs.65.00")
            print(f"Expected P&L: Rs.{expected_total_pnl:.2f} ({expected_pnl_pct:.1f}%)")
            print(f"Actual P&L: Rs.{actual_pnl:.2f} ({actual_pct:.1f}%)")
            
            if abs(actual_pnl - expected_total_pnl) < 1 and abs(actual_pct - expected_pnl_pct) < 1:
                print("✓ Profitable P&L calculation CORRECT")
                self.test_results.append(("Profitable P&L", "PASS"))
            else:
                print("✗ Profitable P&L calculation WRONG")
                self.test_results.append(("Profitable P&L", "FAIL"))
        else:
            print("✗ No exit result - test failed")
            self.test_results.append(("Profitable P&L", "FAIL"))
    
    async def test_loss_exit(self):
        """Test loss scenario P&L"""
        print("\n2. TESTING LOSS EXIT P&L")
        print("-" * 40)
        
        # Create position: Buy at Rs.100, Exit at Rs.70 (30% loss)
        position = self.create_test_position(
            entry_price=100.0,
            current_price=70.0,
            quantity=3,  # 3 lots = 225 shares
            symbol="NIFTY25SEP24550PE"
        )
        
        self.strategy.fetch_option_ltp.return_value = 70.0
        
        # This should trigger 30% stop loss
        result = await self.strategy._check_mandatory_exits_corrected(position, 70.0)
        
        if result and result.exit_reason == "STOP_LOSS_30%":
            expected_pnl_per_share = 70.0 - 100.0  # Rs.-30 loss per share
            expected_total_pnl = -30.0 * 3 * 75    # Rs.-6,750 total loss
            expected_pnl_pct = -30.0               # 30% loss
            
            actual_pnl = getattr(result, 'total_pnl', 0)
            actual_pct = getattr(result, 'pnl_pct', 0)
            
            print(f"Entry: Rs.100.00 | Exit: Rs.70.00")
            print(f"Expected P&L: Rs.{expected_total_pnl:.2f} ({expected_pnl_pct:.1f}%)")
            print(f"Actual P&L: Rs.{actual_pnl:.2f} ({actual_pct:.1f}%)")
            
            if abs(actual_pnl - expected_total_pnl) < 1 and abs(actual_pct - expected_pnl_pct) < 1:
                print("✓ Loss P&L calculation CORRECT")
                self.test_results.append(("Loss P&L", "PASS"))
            else:
                print("✗ Loss P&L calculation WRONG")
                self.test_results.append(("Loss P&L", "FAIL"))
        else:
            print("✗ 30% stop loss not triggered or wrong exit reason")
            self.test_results.append(("Loss P&L", "FAIL"))
    
    async def test_pine_script_exit_pnl(self):
        """Test Pine Script exit with correct P&L"""
        print("\n3. TESTING PINE SCRIPT EXIT P&L")
        print("-" * 40)
        
        # Create position
        position = self.create_test_position(
            entry_price=75.0,
            current_price=80.0,
            quantity=2,
            symbol="NIFTY25SEP24550CE"
        )
        
        # Mock Pine Script exit
        mock_pine_exit = Order(
            symbol="NIFTY25SEP24550CE",
            quantity=2,
            price=24500.0,  # This is NIFTY spot price (wrong)
            order_type=OrderType.MARKET,
            transaction_type=TransactionType.SELL,
            strategy_name="test"
        )
        mock_pine_exit.exit_reason = "STRONG_RED_CANDLE"
        
        # Mock the parent strategy exit method
        async def mock_super_exit(position, market_data):
            return mock_pine_exit
        
        original_method = self.strategy.__class__.__bases__[0].should_exit
        self.strategy.__class__.__bases__[0].should_exit = mock_super_exit
        
        self.strategy.fetch_option_ltp.return_value = 80.0  # Correct option premium
        
        market_data = {"ha_candle": {"ha_close": 24500}}
        result = await self.strategy.should_exit(position, market_data)
        
        # Restore original method
        self.strategy.__class__.__bases__[0].should_exit = original_method
        
        if result:
            # The key test: Pine Script should use option premium, not spot price
            actual_price = result.price
            expected_price = 80.0  # Should be option premium, not NIFTY spot
            
            print(f"Pine Script returned price: Rs.{mock_pine_exit.price:.2f} (NIFTY spot)")
            print(f"Corrected exit price: Rs.{actual_price:.2f} (Option premium)")
            print(f"Expected exit price: Rs.{expected_price:.2f}")
            
            if abs(actual_price - expected_price) < 0.01:
                print("✓ Pine Script exit uses correct option premium")
                self.test_results.append(("Pine Script P&L", "PASS"))
            else:
                print("✗ Pine Script exit still using wrong price")
                self.test_results.append(("Pine Script P&L", "FAIL"))
        else:
            print("✗ Pine Script exit not triggered")
            self.test_results.append(("Pine Script P&L", "FAIL"))
    
    async def test_mandatory_exit_pnl(self):
        """Test all mandatory exit scenarios"""
        print("\n4. TESTING MANDATORY EXIT SCENARIOS")
        print("-" * 40)
        
        # Test market close
        position = self.create_test_position(55.0, 60.0, 1, "TEST_CE")
        
        with patch('datetime.datetime') as mock_datetime:
            mock_now = datetime.now().replace(hour=15, minute=20, second=0)
            mock_datetime.now.return_value = mock_now
            
            result = await self.strategy._check_mandatory_exits_corrected(position, 60.0)
            
            if result and result.exit_reason == "MARKET_CLOSE":
                expected_pnl = (60.0 - 55.0) * 1 * 75  # Rs.375 profit
                actual_pnl = getattr(result, 'total_pnl', 0)
                
                print(f"Market Close P&L: Expected Rs.{expected_pnl:.2f}, Actual Rs.{actual_pnl:.2f}")
                
                if abs(actual_pnl - expected_pnl) < 1:
                    print("✓ Market close P&L correct")
                    self.test_results.append(("Market Close P&L", "PASS"))
                else:
                    print("✗ Market close P&L wrong")
                    self.test_results.append(("Market Close P&L", "FAIL"))
            else:
                print("✗ Market close not triggered")
                self.test_results.append(("Market Close P&L", "FAIL"))
    
    async def test_realistic_scenarios(self):
        """Test with realistic option trading scenarios"""
        print("\n5. TESTING REALISTIC SCENARIOS")
        print("-" * 40)
        
        test_cases = [
            {
                "name": "Small Profit",
                "entry": 45.0, "exit": 48.0, "lots": 2,
                "expected_pnl": (48.0 - 45.0) * 2 * 75,  # Rs.450
                "expected_pct": ((48.0 - 45.0) / 45.0) * 100  # 6.67%
            },
            {
                "name": "Small Loss", 
                "entry": 60.0, "exit": 55.0, "lots": 1,
                "expected_pnl": (55.0 - 60.0) * 1 * 75,  # Rs.-375
                "expected_pct": ((55.0 - 60.0) / 60.0) * 100  # -8.33%
            },
            {
                "name": "Break Even",
                "entry": 50.0, "exit": 50.5, "lots": 3,
                "expected_pnl": (50.5 - 50.0) * 3 * 75,  # Rs.112.50
                "expected_pct": ((50.5 - 50.0) / 50.0) * 100  # 1%
            }
        ]
        
        for case in test_cases:
            position = self.create_test_position(
                case["entry"], case["exit"], case["lots"], f"TEST_{case['name']}"
            )
            
            # Force market close to test P&L
            with patch('datetime.datetime') as mock_datetime:
                mock_now = datetime.now().replace(hour=15, minute=20)
                mock_datetime.now.return_value = mock_now
                
                result = await self.strategy._check_mandatory_exits_corrected(position, case["exit"])
                
                if result:
                    actual_pnl = getattr(result, 'total_pnl', 0)
                    actual_pct = getattr(result, 'pnl_pct', 0)
                    
                    pnl_ok = abs(actual_pnl - case["expected_pnl"]) < 1
                    pct_ok = abs(actual_pct - case["expected_pct"]) < 0.1
                    
                    print(f"{case['name']}: Expected Rs.{case['expected_pnl']:.2f} ({case['expected_pct']:.1f}%)")
                    print(f"              Actual Rs.{actual_pnl:.2f} ({actual_pct:.1f}%) {'✓' if pnl_ok and pct_ok else '✗'}")
                    
                    if pnl_ok and pct_ok:
                        self.test_results.append((f"Realistic {case['name']}", "PASS"))
                    else:
                        self.test_results.append((f"Realistic {case['name']}", "FAIL"))
    
    def create_test_position(self, entry_price: float, current_price: float, 
                           quantity: int, symbol: str) -> Position:
        """Create test position"""
        position = Position(
            symbol=symbol,
            quantity=quantity,
            average_price=entry_price,
            current_price=current_price,
            pnl=0,
            unrealized_pnl=0,
            instrument_key="TEST"
        )
        
        position.strike_price = 24550
        position.option_type = "CE" if "CE" in symbol else "PE"
        position.entry_time = datetime.now()
        
        return position
    
    def print_results(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("P&L VALIDATION TEST RESULTS")
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
            status = "✓" if result == "PASS" else "✗"
            print(f"{status} {test_name}: {result}")
        
        if failed == 0:
            print("\n🎉 ALL P&L CALCULATIONS ARE CORRECT!")
            print("Your Pine Script fix is working properly.")
        else:
            print(f"\n⚠️ {failed} tests failed. Review P&L calculations.")

async def test_pnl_calculations():
    """Main test function"""
    validator = PnLTestValidator()
    await validator.run_all_tests()

if __name__ == "__main__":
    asyncio.run(test_pnl_calculations())