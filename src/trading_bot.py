#trading bot 
# ==================== src/trading_bot.py (COMPLETELY FIXED) ====================
import asyncio
import logging
from datetime import datetime, time
from typing import Dict, List, Optional
from config.settings import Settings
from src.upstox_api_client import UpstoxClient
from src.utils.notification import TelegramNotifier
from src.strategy.base_strategy import BaseStrategy
from src.models.order import Order, OrderStatus, OrderType, TransactionType
from src.models.position import Position
from src.utils.market_utils import MarketUtils
from src.options.option_chain_manager import OptionChainManager
from src.options.greeks_calculator import GreeksCalculator
from src.backtesting.results import BacktestResultsManager, integrate_backtest_results_into_strategy
from datetime import time

class RealtimeSignalProcessor:
    """
    Process signals on every tick instead of waiting for candle completion
    This fixes the 3-4 minute delay issue
    """
    
    def __init__(self, trading_bot):
        self.trading_bot = trading_bot
        self.logger = logging.getLogger(__name__)
        self.price_buffer = {}
        self.last_signal_time = {}
        self.signal_cooldown = 30  # 30 seconds between signals (reduced from 60)
        
        # Track current incomplete candle for each symbol
        self.current_candles = {}
        
    async def process_tick_for_immediate_signals(self, symbol: str, tick_data: Dict):
        """
        MAIN FIX: Process signals immediately on price ticks
        Don't wait for candle completion
        """
        try:
            price = float(tick_data.get('ltp', 0))
            if price <= 0:
                return
            
            timestamp = datetime.now()
            
            # Update current incomplete candle
            self._update_current_candle(symbol, price, timestamp)
            
            # Check signal cooldown
            if not self._can_process_signal(symbol, timestamp):
                return
            
            # Get strategy for signal checking
            if not self.trading_bot.strategies:
                return
                
            strategy = self.trading_bot.strategies[0]  # Get main strategy
            
            # Check if strategy has enough historical data
            if not hasattr(strategy, 'ha_candles_history'):
                return
                
            candle_count = len(strategy.ha_candles_history)
            if candle_count < 15:  # Reduced from 23 for faster start
                self.logger.info(f"Building data: {candle_count}/15 candles")
                return
            
            # Create market data with current incomplete candle
            market_data = self._create_realtime_market_data(symbol, price, timestamp, strategy)
            
            # Check for immediate entry signals
            if not strategy.in_trade and len(self.trading_bot.positions) == 0:
                entry_signal = await self._check_immediate_entry_signal(strategy, market_data)
                if entry_signal:
                    await self._execute_immediate_signal(entry_signal)
                    
            # Check for exit signals on existing positions
            await self._check_immediate_exit_signals(strategy, market_data)
            
        except Exception as e:
            self.logger.error(f"Error in realtime signal processing: {e}")
    
    def _update_current_candle(self, symbol: str, price: float, timestamp: datetime):
        """Update current incomplete candle with each tick"""
        if symbol not in self.current_candles:
            self.current_candles[symbol] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'start_time': timestamp,
                'tick_count': 1
            }
        else:
            candle = self.current_candles[symbol]
            candle['high'] = max(candle['high'], price)
            candle['low'] = min(candle['low'], price)
            candle['close'] = price
            candle['tick_count'] += 1
    
    def _can_process_signal(self, symbol: str, timestamp: datetime) -> bool:
        """Check if enough time has passed since last signal"""
        if symbol not in self.last_signal_time:
            return True
            
        time_diff = (timestamp - self.last_signal_time[symbol]).total_seconds()
        return time_diff >= self.signal_cooldown
    
    def _create_realtime_market_data(self, symbol: str, price: float, timestamp: datetime, strategy) -> Dict:
        """Create market data using current incomplete candle + historical candles"""
        # Get current incomplete candle
        current_candle = self.current_candles.get(symbol, {})
        
        # Convert to HA candle format
        ha_candle = {
            'ha_open': current_candle.get('open', price),
            'ha_high': current_candle.get('high', price),
            'ha_low': current_candle.get('low', price),
            'ha_close': current_candle.get('close', price),
            'volume': 0,
            'timestamp': timestamp
        }
        
        # Get historical candles from strategy
        ha_candles_history = getattr(strategy, 'ha_candles_history', [])
        
        return {
            'symbol': symbol,
            'ha_candle': ha_candle,
            'ha_candles_history': ha_candles_history + [ha_candle],  # Add current candle
            'current_price': price,
            'timestamp': timestamp,
            'price': price,
            'high': ha_candle['ha_high'],
            'low': ha_candle['ha_low'],
            'open': ha_candle['ha_open'],
            'close': ha_candle['ha_close'],
            'instrument_key': 'NSE_INDEX|Nifty 50'
        }
    
    async def _check_immediate_entry_signal(self, strategy, market_data: Dict):
        """Check for entry signals using real-time data"""
        try:
            # Use the strategy's should_enter method with real-time data
            entry_order = await strategy.should_enter(market_data)
            
            if entry_order:
                self.logger.info(f"IMMEDIATE ENTRY SIGNAL: {getattr(entry_order, 'option_type', 'CE')}")
                return entry_order
                
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking immediate entry: {e}")
            return None
    
    async def _check_immediate_exit_signals(self, strategy, market_data: Dict):
        """Check for exit signals on existing positions"""
        try:
            positions_to_check = list(self.trading_bot.positions.values())
            
            for position in positions_to_check:
                exit_order = await strategy.should_exit(position, market_data)
                if exit_order:
                    await self._execute_immediate_signal(exit_order)
                    
        except Exception as e:
            self.logger.error(f"Error checking immediate exits: {e}")
    
    async def _execute_immediate_signal(self, order):
        """Execute signal immediately with rate limiting"""
        try:
            # Update last signal time
            symbol = getattr(order, 'symbol', 'UNKNOWN')
            if 'NIFTY' in symbol or 'UNKNOWN' in symbol:
                self.last_signal_time['NIFTY'] = datetime.now()
            
            # Place order with rate limiting
            success = await self.trading_bot.rate_limiter.execute_with_rate_limit(
                self.trading_bot.place_order, order
            )
            
            if success:
                self.trading_bot.orders.append(order)
                await self.trading_bot.send_trade_notification(order, "ENTRY" if order.transaction_type.name == "BUY" else "EXIT")
                self.logger.info(f"Immediate signal executed: {order.symbol}")
            else:
                self.logger.error(f"Failed to execute immediate signal due to rate limiting")
                
        except Exception as e:
            self.logger.error(f"Error executing immediate signal: {e}")

# Import websocket manager
try:
    from src.websocket.websocket_manager import WebSocketManager
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
class TradingBot:
    """Enhanced trading bot with comprehensive monitoring and auto-reconnection"""
    
    def __init__(self, settings: Settings):
        #super().__init__(settings)
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self.trading_logger = logging.getLogger('trading')
        
        self.last_signal_time = {}  # Track last signal time per symbol
        self.signal_cooldown = 60   # 60 seconds cooldown between signals
        self.processing_signal = False
    
        self.global_trade_counter = 0
        self.global_winning_trades = 0
        self.global_total_pnl = 0.0
        self.session_trades = []
        
        # Initialize clients
        self.upstox_client = UpstoxClient(
            settings.upstox_api_key,
            settings.upstox_api_secret,
            settings.upstox_redirect_uri
        )
        
        self.notifier = TelegramNotifier(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.enable_notifications
        )
        
        self.option_chain_manager = OptionChainManager(self.upstox_client)
        self.greeks_calculator = GreeksCalculator()
        self.backtest_manager = BacktestResultsManager()
        
        
        # Initialize WebSocket Manager
        self.websocket_manager: Optional[WebSocketManager] = None
        self.websocket_enabled = WEBSOCKET_AVAILABLE
        
        # Trading state
        self.strategies: List[BaseStrategy] = []
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.is_running = False
        self.paper_trading = settings.paper_trading
        
        # Real-time data
        self.latest_ticks: Dict[str, Dict] = {}
        self.latest_candles: Dict[str, Dict] = {}
        self.latest_ha_candles: Dict[str, Dict] = {}
        
        # Multi-strategy containers
        self.strategy_configs = {}
        self.strategy_performance = {}
        
        # Performance tracking
        # Initialize tracking for hourly reports
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.trades_today = []
        self.session_start_time = datetime.now()
        
        # Position tracking
        self.positions = {}
        self.orders = []
    
        # Latest market data
        self.latest_ticks = {}
        self.latest_candles = {}
        self.latest_ha_candles = {}
        
        # Enhanced monitoring - Fixed initialization
        self.last_price_update = datetime.now()  # Initialize to current time
        self.last_websocket_check = datetime.now()
        self.websocket_reconnect_attempts = 0
        self.last_signal_analysis_log = datetime.now()
        self.last_telegram_update = datetime.now()
        self.price_log_interval = 30  # Log price every 30 seconds
        self.signal_analysis_interval = 180  # Detailed analysis every 3 minutes
        self.telegram_update_interval = 3600  # Telegram update every hour
        
        # Default instruments to subscribe
        self.default_instruments = [
            'NSE_INDEX|Nifty 50',
            'NSE_INDEX|Nifty Bank', 
            'BSE_INDEX|SENSEX'
        ]
        
        # Enhanced performance tracking
        self.trade_performance = {
            'ce_trades': 0,
            'pe_trades': 0,
            'ce_wins': 0,
            'pe_wins': 0,
            'total_theta_decay': 0,
            'total_delta_pnl': 0,
            'greeks_validated_trades': 0
        }

        # 🆕 ADD DAILY TRADE LIMIT TRACKING
        if not hasattr(self, 'daily_trades'):
            self.daily_trades = []  # Track trades for current day
        if not hasattr(self, 'max_daily_trades'):
            self.max_daily_trades = 100  # Maximum trades per day
        if not hasattr(self, 'current_date'):
            self.current_date = datetime.now().date()  # Track current date
    
        self.logger.info(f"Daily trade limit set to {self.max_daily_trades} trades")

        from src.utils.api_rate_limiter import APIRateLimiter
        self.rate_limiter = APIRateLimiter(max_requests_per_minute=50)
        self.realtime_processor = RealtimeSignalProcessor(self)
        
        self.logger.info("Added rate limiting and real-time signal processing")
        
    async def on_ha_candle_received(self, ha_candle: Dict):
        """Process new Heikin Ashi candle - FIXED TO USE HISTORICAL DATA IMMEDIATELY"""
        try:
            symbol = ha_candle.get('symbol', 'UNKNOWN')
            if not symbol or symbol == 'UNKNOWN':
                return
            
            # PREVENT CONCURRENT PROCESSING
            if self.processing_signal:
                return
            
            # CHECK SIGNAL COOLDOWN
            current_time = datetime.now()
            last_signal = self.last_signal_time.get(symbol, datetime.min)
            
            if (current_time - last_signal).total_seconds() < self.signal_cooldown:
                return
            
            # SET PROCESSING FLAG
            self.processing_signal = True
            
            try:
                # Log the new candle
                self.logger.info(f"NEW HA CANDLE - {symbol}: O:{ha_candle.get('ha_open', 0):.2f} "
                            f"H:{ha_candle.get('ha_high', 0):.2f} L:{ha_candle.get('ha_low', 0):.2f} "
                            f"C:{ha_candle.get('ha_close', 0):.2f}")
                
                # CRITICAL FIX: Check if strategy already has historical data
                strategy_ready = False
                total_available = 0
                
                for strategy in self.strategies:
                    if hasattr(strategy, 'ha_candles_history') and len(strategy.ha_candles_history) >= 23:
                        # Strategy has historical data - use it immediately
                        self.logger.info("USING HISTORICAL DATA - IMMEDIATE EXECUTION")
                        # Combine historical + new candle
                        complete_candles = strategy.ha_candles_history + [ha_candle]
                        # Execute strategy immediately
                        await self._execute_strategies_on_ha_candle_fixed(symbol, ha_candle, complete_candles)
                        return
                    
                    if not strategy.is_active:
                        continue
                    
                    # Check historical data first (priority)
                    historical_count = len(getattr(strategy, 'ha_candles_history', []))
                    candle_history_count = len(getattr(strategy, 'candle_history', []))
                    
                    # Use whichever has more data
                    total_available = max(historical_count, candle_history_count)
                    
                    if total_available >= 23:  # Strategy ready with historical data
                        strategy_ready = True
                        
                        self.logger.info(f"USING HISTORICAL DATA: {total_available} candles available")
                        
                        # Add current WebSocket candle to existing data
                        if historical_count >= 23:
                            updated_candles = strategy.ha_candles_history + [ha_candle]
                        else:
                            updated_candles = strategy.candle_history + [ha_candle]
                        
                        # Keep last 50 candles
                        updated_candles = updated_candles[-50:]
                        
                        # Update both arrays
                        strategy.ha_candles_history = updated_candles
                        strategy.candle_history = updated_candles
                        
                        # Execute strategy with full historical + current data
                        await self._execute_strategies_on_ha_candle_fixed(symbol, ha_candle, updated_candles)
                        
                        # Update last signal time
                        self.last_signal_time[symbol] = current_time
                        
                        break
                    else:
                        self.logger.info(f"BUILDING DATA: Strategy has {total_available}/23 candles, WebSocket building...")
                
                # If no strategy is ready with historical data, use WebSocket data building
                if not strategy_ready:
                    # Get WebSocket candle count
                    ws_candles = []
                    if self.websocket_manager and hasattr(self.websocket_manager, 'persistent_ha_candles'):
                        ws_candles = self.websocket_manager.persistent_ha_candles.get(symbol, [])
                    
                    ws_count = len(ws_candles)
                    
                    if ws_count >= 15:  # Reduced from 23 to 15 for faster activation
                        self.logger.info(f"USING WEBSOCKET DATA: {ws_count} candles available")
                        
                        # Add current candle
                        complete_candles = ws_candles + [ha_candle]
                        
                        # Execute strategy
                        await self._execute_strategies_on_ha_candle_fixed(symbol, ha_candle, complete_candles)
                        
                        # Update strategy data
                        for strategy in self.strategies:
                            if strategy.is_active:
                                strategy.ha_candles_history = complete_candles[-50:]
                                strategy.candle_history = complete_candles[-50:]
                        
                        # Update last signal time
                        self.last_signal_time[symbol] = current_time
                    
                    else:
                        self.logger.info(f"STILL BUILDING: {ws_count}/15 WebSocket candles collected")
                    
            finally:
                # ALWAYS RESET PROCESSING FLAG
                self.processing_signal = False
                    
        except Exception as e:
            self.processing_signal = False  # Reset flag on error
            self.logger.error(f"Error processing HA candle: {e}")

    async def _execute_strategies_on_ha_candle_fixed(self, symbol: str, ha_candle: Dict, ha_candles: List[Dict]):
        """FIXED: Execute strategies with proper HA data format"""  
        try:
            self.logger.info(f"EXECUTING STRATEGIES for {symbol} with {len(ha_candles)} candles")

            # FIXED: Prepare comprehensive market data with HA format
            market_data = {
                'symbol': symbol,
                'ha_candle': ha_candle,
                'ha_candles_history': ha_candles,
                'instrument_key': 'NSE_INDEX|Nifty 50',
                'current_price': ha_candle.get('ha_close', 0),
                'timestamp': datetime.now(),
                
                # FIXED: Add both HA and regular format for compatibility
                'price': ha_candle.get('ha_close', 0),
                'high': ha_candle.get('ha_high', 0),
                'low': ha_candle.get('ha_low', 0),
                'volume': ha_candle.get('volume', 0),
                'open': ha_candle.get('ha_open', 0),
                'close': ha_candle.get('ha_close', 0),  # This maps HA close to regular close field
                
                # Keep HA fields as well
                'ha_open': ha_candle.get('ha_open', 0),
                'ha_high': ha_candle.get('ha_high', 0),
                'ha_low': ha_candle.get('ha_low', 0),
                'ha_close': ha_candle.get('ha_close', 0)
            }

            self.logger.info(f"Market Data: Price={market_data['current_price']:.2f}, Total Candles={len(ha_candles)}")

            # Process each strategy
            strategy_count = len(self.strategies)
            self.logger.info(f"Processing {strategy_count} strategies...")

            for i, strategy in enumerate(self.strategies):
                if not strategy.is_active:
                    self.logger.warning(f"Strategy {i+1}/{strategy_count} ({strategy.name}) is INACTIVE")
                    continue
            
                try:
                    self.logger.info(f"Analyzing strategy {i+1}/{strategy_count}: {strategy.name}")
                
                    # CRITICAL FIX: Ensure strategy has the complete HA data
                    if hasattr(strategy, 'ha_candles_history'):
                        # Update strategy's candle history with WebSocket + historical data
                        if len(ha_candles) > len(strategy.ha_candles_history):
                            strategy.ha_candles_history = ha_candles.copy()
                            # Also update candle_history for compatibility
                            strategy.candle_history = ha_candles.copy()
                            self.logger.info(f"Updated strategy data: {len(strategy.ha_candles_history)} HA candles")
                
                    # Check daily trade limit
                    can_trade = self._check_daily_trade_limit()
                
                    if can_trade:
                        # ENTRY SIGNAL CHECK
                        self.logger.info(f"Checking for ENTRY signals with {len(ha_candles)} candles...")
                        entry_order = await strategy.should_enter(market_data)
                        
                        if entry_order:
                            option_type = getattr(entry_order, 'option_type', 'CE')
                            self.logger.info(f"*** ENTRY SIGNAL FOUND *** {option_type} from {strategy.name}")
                            self.logger.info(f"    Price: Rs.{entry_order.price:.2f} | Quantity: {entry_order.quantity}")
                    
                            # Place order and record for daily limit
                            if await self.place_order(entry_order):
                                self.orders.append(entry_order)
                                await strategy.on_order_filled(entry_order)
                                await self.send_trade_notification(entry_order, "ENTRY")
                            
                                # Record trade for daily limit
                                self._record_daily_trade(entry_order)
                            
                                self.logger.info(f"Entry order executed successfully")
                                
                            else:
                                self.logger.error(f"Failed to place entry order")
                        else:
                            self.logger.debug(f"No entry signal from {strategy.name}")
                    else:
                        self.logger.info(f"Daily trade limit reached ({self.max_daily_trades} trades). Skipping new entries.")

                    # ENHANCED EXIT SIGNAL CHECK - ALWAYS PROCESS EXITS
                    await self._process_all_exits_enhanced(strategy, market_data, symbol)
            
                except Exception as strategy_error:
                    self.logger.error(f"Error in strategy {strategy.name}: {strategy_error}")
                    import traceback
                    self.logger.error(f"Strategy error details: {traceback.format_exc()}")

            self.logger.info(f"Strategy execution completed for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Critical error executing strategies: {e}")
            import traceback
            self.logger.error(f"Critical error details: {traceback.format_exc()}")
    
    def record_trade_entry(self, order: Order):
        """Record trade entry consistently"""
        
        trade_record = {
            'trade_id': self.global_trade_counter + 1,
            'symbol': getattr(order, 'strike_symbol', order.symbol),
            'option_type': getattr(order, 'option_type', 'CE'),
            'entry_time': datetime.now(),
            'entry_price': order.price,
            'quantity': order.quantity,
            'investment': getattr(order, 'total_investment', order.price * order.quantity * 75),
            'status': 'OPEN'
        }
        
        self.session_trades.append(trade_record)
        self.global_trade_counter += 1
        
        self.logger.info(f"Trade #{self.global_trade_counter} recorded: {trade_record['symbol']}")

    def record_trade_exit(self, position, exit_price: float, exit_reason: str) -> Dict:
        """Record trade exit and calculate final P&L"""
        
        # Find the corresponding entry trade
        symbol = getattr(position, 'strike_symbol', position.symbol)
        
        for trade in reversed(self.session_trades):
            if trade['symbol'] == symbol and trade['status'] == 'OPEN':
                # Update trade record
                trade['exit_time'] = datetime.now()
                trade['exit_price'] = exit_price
                trade['exit_reason'] = exit_reason
                trade['status'] = 'CLOSED'
                
                # Calculate P&L
                entry_value = trade['entry_price'] * trade['quantity'] * 75
                exit_value = exit_price * trade['quantity'] * 75
                pnl = exit_value - entry_value
                trade['pnl'] = pnl
                
                # Update global counters
                if pnl > 0:
                    self.global_winning_trades += 1
                
                self.global_total_pnl += pnl
                
                self.logger.info(f"Trade #{trade['trade_id']} closed: P&L Rs.{pnl:.2f}")
                
                return trade
        
        return None
            
    async def _execute_strategies_on_ha_candle(self, symbol: str, ha_candle: Dict, ha_candles: List[Dict]):
        """ENHANCED: Execute all strategies with daily trade limits and improved exit processing"""  
        try:
            self.logger.info(f"EXECUTING STRATEGIES for {symbol}")
    
            # Prepare comprehensive market data
            market_data = {
                'symbol': symbol,
                'ha_candle': ha_candle,
                'ha_candles_history': ha_candles,
                'instrument_key': 'NSE_INDEX|Nifty 50',
                'current_price': ha_candle.get('ha_close', 0),
                'timestamp': datetime.now(),
                # Add compatibility fields
                'price': ha_candle.get('ha_close', 0),
                'high': ha_candle.get('ha_high', 0),
                'low': ha_candle.get('ha_low', 0),
                'volume': ha_candle.get('volume', 0),
                'open': ha_candle.get('ha_open', 0),
                'close': ha_candle.get('ha_close', 0)
            }
    
            self.logger.info(f"Market Data: Price={market_data['current_price']:.2f}, Candles={len(ha_candles)}")
    
            # Process each strategy
            strategy_count = len(self.strategies)
            self.logger.info(f"Processing {strategy_count} strategies...")

            for i, strategy in enumerate(self.strategies):
                if not strategy.is_active:
                    self.logger.warning(f"Strategy {i+1}/{strategy_count} ({strategy.name}) is INACTIVE")
                    continue
            
                try:
                    self.logger.info(f"Analyzing strategy {i+1}/{strategy_count}: {strategy.name}")
                
                    # 🆕 CHECK DAILY TRADE LIMIT FIRST
                    can_trade = self._check_daily_trade_limit()
                
                    if can_trade:
                        # 🚨 ENTRY SIGNAL CHECK 🚨
                        entry_order = await strategy.should_enter(market_data)
                        if entry_order:
                            option_type = getattr(entry_order, 'option_type', 'CE')
                            self.logger.info(f"*** ENTRY SIGNAL *** {option_type} from {strategy.name}")
                            self.logger.info(f"    Price: Rs.{entry_order.price:.2f} | Quantity: {entry_order.quantity}")
                    
                            # Place order and record for daily limit
                            if await self.place_order(entry_order):
                                self.orders.append(entry_order)
                                await strategy.on_order_filled(entry_order)
                                await self.send_trade_notification(entry_order, "ENTRY")
                            
                                # 🆕 RECORD TRADE FOR DAILY LIMIT
                                self._record_daily_trade(entry_order)
                            
                                self.logger.info(f"Entry order executed successfully")
                                
                            # Check for RE-ENTRY opportunities (after regular entry check)
                            if not entry_order and hasattr(strategy, 'check_reentry_opportunity'):
                                reentry_order = await strategy.check_reentry_opportunity(market_data)
                                if reentry_order:
                                    self.logger.info(f"*** RE-ENTRY SIGNAL *** {reentry_order.option_type}")
                
                                    if await self.place_order(reentry_order):
                                        self.orders.append(reentry_order) 
                                        await strategy.on_order_filled(reentry_order)
                                        await self.send_trade_notification(reentry_order, "RE-ENTRY")
                    
                                        # Record for daily limit
                                        self._record_daily_trade(reentry_order)
                    
                                        self.logger.info(f"Re-entry order executed successfully")


                            else:
                                self.logger.error(f"Failed to place entry order")
                        else:
                            self.logger.info(f"No entry signal from {strategy.name}")
                    else:
                        self.logger.info(f"Daily trade limit reached ({self.max_daily_trades} trades). Skipping new entries.")

                    # 🚨 ENHANCED EXIT SIGNAL CHECK - ALWAYS PROCESS EXITS 🚨
                    await self._process_all_exits_enhanced(strategy, market_data, symbol)
            
                except Exception as strategy_error:
                    self.logger.error(f"Error in strategy {strategy.name}: {strategy_error}")
                    import traceback
                    self.logger.error(f"Strategy error details: {traceback.format_exc()}")
    
            self.logger.info(f"Strategy execution completed for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Critical error executing strategies: {e}")
            import traceback
            self.logger.error(f"Critical error details: {traceback.format_exc()}")
    
    async def process_pending_websocket_callbacks(self):
        """Process any pending WebSocket callbacks"""
        if hasattr(self.websocket_manager, 'pending_callbacks'):
            pending = getattr(self.websocket_manager, 'pending_callbacks', [])
        
            for symbol, ha_candle in pending:
                try:
                    await self.on_ha_candle_received(ha_candle)
                    self.logger.info(f"Processed pending callback for {symbol}")
                except Exception as e:
                    self.logger.error(f"Error processing pending callback: {e}")
        
            # Clear processed callbacks
            self.websocket_manager.pending_callbacks = []
        
        
            
    def add_strategy(self, strategy: BaseStrategy):
        """Enhanced strategy addition with options integration"""
        # Set option chain manager for the strategy
        if hasattr(strategy, 'set_option_chain_manager'):
            strategy.set_option_chain_manager(self.option_chain_manager)
        
        # Integrate backtesting results
        strategy = integrate_backtest_results_into_strategy(strategy)
        
        # Add to strategies list
        self.strategies.append(strategy)
        self.logger.info(f"Added enhanced strategy: {strategy.name}")
        
        # Log expected performance
        if hasattr(strategy, 'expected_metrics'):
            expected = strategy.expected_metrics
            self.logger.info(f"Expected Performance - Win Rate: {expected['expected_win_rate']:.1f}%, Monthly Return: {expected['expected_monthly_return']:.1f}%")

    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        return MarketUtils.is_market_open()
    
    async def setup_websockets(self):
        """Setup websocket connections for NIFTY only"""
        if not self.websocket_enabled:
            self.logger.warning("WebSocket not available")
            return False
        
        if not self.upstox_client.access_token:
            self.logger.error("No access token available")
            return False
        
        try:
            # Initialize WebSocket Manager
            self.websocket_manager = WebSocketManager(
                api_key=self.settings.upstox_api_key,
                access_token=self.upstox_client.access_token
            )
        
            # Set up callbacks
            self.websocket_manager.set_callbacks(
                on_tick=None,
                on_candle=None,
                on_ha_candle=self.on_ha_candle_received,
                on_order_update=self.on_order_update_received,
                on_error=self.on_websocket_error
            )
        
            # Subscribe to NIFTY only
            self.websocket_manager.subscribe_instruments(['NSE_INDEX|Nifty 50'])
        
            # Start streams
            self.websocket_manager.start_all_streams()
        
            self.logger.info("WebSocket connected for NIFTY")
            #await self.notifier.send_status_update("Connected", "Streaming NIFTY data")
            self.logger.info("WebSocket setup complete")    

            return True
        
        except Exception as e:
            self.logger.error(f"Failed to setup websockets: {e}")
            return False
    
    def setup_websocket_callbacks(self):
        """Setup WebSocket event callbacks"""
        self.websocket_manager.set_callbacks(
            on_tick=None,  # Disable to reduce noise
            on_candle=None,  # Disable to reduce noise
            on_ha_candle=self.on_ha_candle_received,  # ← ENABLE THIS
            on_order_update=self.on_order_update_received,
            on_error=self.on_websocket_error
        )
        self.logger.info("WebSocket callbacks configured for HA candle processing")


    async def on_tick_received(self, tick_data: Dict):
        """ENHANCED: Process ticks for immediate signals instead of waiting for candle completion"""
        try:
            instrument_key = tick_data.get('instrument_key', '')
            symbol = self._extract_symbol_from_key(instrument_key)
            
            # Add timestamp for monitoring
            tick_data['timestamp'] = datetime.now()
            tick_data['price'] = tick_data.get('ltp', 0)
            
            # Store latest tick
            self.latest_ticks[symbol] = tick_data
            
            # NEW: Process for immediate signals (don't wait for candle completion)
            if symbol == 'NIFTY' and self.is_market_open():
                await self._process_tick_for_immediate_signals(symbol, tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing tick data: {e}")
    
    async def on_candle_completed(self, candle_data: Dict):
        """Handle completed candle"""
        try:
            symbol = candle_data.get('symbol', '')
            
            # Store latest candle
            self.latest_candles[symbol] = candle_data
            
            self.trading_logger.info(
                f"3min Candle {symbol}: O:{candle_data['open']:.2f} H:{candle_data['high']:.2f} "
                f"L:{candle_data['low']:.2f} C:{candle_data['close']:.2f} V:{candle_data['volume']}"
            )
            
        except Exception as e:
            self.logger.error(f"Error processing candle data: {e}")
    
    async def on_ha_candle_completed(self, ha_candle_data: Dict):
        """Handle completed Heikin Ashi candle - KEY FOR STRATEGY"""
        try:
            symbol = ha_candle_data.get('symbol', '')
            
            # Store latest HA candle
            self.latest_ha_candles[symbol] = ha_candle_data
            
            self.trading_logger.info(
                f"HA Candle {symbol}: O:{ha_candle_data['ha_open']:.2f} H:{ha_candle_data['ha_high']:.2f} "
                f"L:{ha_candle_data['ha_low']:.2f} C:{ha_candle_data['ha_close']:.2f}"
            )
            
            # Trigger strategy evaluation on new HA candle
            await self.evaluate_strategies_on_new_candle(symbol, ha_candle_data)
            
        except Exception as e:
            self.logger.error(f"Error processing HA candle data: {e}")
    
    async def on_order_update_received(self, order_update: Dict):
        """Handle order status updates"""
        try:
            self.trading_logger.info(f"Order update: {order_update}")
        except Exception as e:
            self.logger.error(f"Error processing order update: {e}")
    
    async def on_websocket_error(self, error_message: str):
        """Enhanced WebSocket error handler with history preservation"""
        try:
            self.logger.error(f"WebSocket Error: {error_message}")
        
            # SAVE CANDLE HISTORY BEFORE ANY RECONNECTION
            saved_candles = {}
            saved_ha_candles = {}
        
            if self.websocket_manager:
                for symbol in ['NIFTY', 'BANKNIFTY', 'SENSEX']:
                    saved_candles[symbol] = self.websocket_manager.get_latest_candles(symbol, 100)
                    saved_ha_candles[symbol] = self.websocket_manager.get_latest_ha_candles(symbol, 100)
        
            # Send immediate Telegram alert
            #await self.notifier.send_error_alert(f"🚨 WebSocket Error: {error_message}")
            self.logger.info("Sent WebSocket error alert")
            # Attempt automatic reconnection
            self.logger.info("Attempting automatic WebSocket reconnection...")
            self.websocket_reconnect_attempts += 1
        
            # Small delay before reconnection attempt
            await asyncio.sleep(5)
        
            reconnect_success = await self.setup_websockets()
        
            if reconnect_success and saved_ha_candles:
                # Restore candle history
                for symbol, candles in saved_candles.items():
                    if candles and symbol in saved_ha_candles:
                        self.websocket_manager.restore_candle_history(
                            symbol, 
                            candles, 
                            saved_ha_candles[symbol]
                        )
            
                #await self.notifier.send_status_update("Auto-Reconnected", 
                #    f"✅ WebSocket reconnected with history preserved!")
                self.websocket_reconnect_attempts = 0
            else:
                #await self.notifier.send_error_alert(
                #    f"❌ Auto-reconnection failed. Manual restart may be required.")
                self.logger.error("WebSocket auto-reconnection failed")

        except Exception as e:
            self.logger.error(f"Error handling WebSocket error: {e}")
    
    async def check_websocket_health(self):
        """Monitor WebSocket health and auto-reconnect if needed"""
        try:
            current_time = datetime.now()
        
            # Check every 5 minutes
            if (current_time - self.last_websocket_check).total_seconds() < 300:
                return
            
            self.last_websocket_check = current_time
        
            if not self.websocket_manager:
                return
        
            # Check if we have recent data (within 2 minutes)
            data_age_limit = 120
            recent_data = False
        
            for symbol, tick_data in self.latest_ticks.items():
                if 'timestamp' in tick_data:
                    data_age = (current_time - tick_data['timestamp']).total_seconds()
                    if data_age < data_age_limit:
                        recent_data = True
                        break
        
            # If no recent data during market hours, attempt reconnection
            if not recent_data and self.is_market_open():
                self.logger.warning("No recent WebSocket data detected during market hours")
            
                # SAVE CANDLE HISTORY BEFORE RECONNECTION
                saved_candles = {}
                saved_ha_candles = {}
            
            if self.websocket_manager:
                for symbol in ['NIFTY', 'BANKNIFTY', 'SENSEX']:
                    saved_candles[symbol] = self.websocket_manager.get_latest_candles(symbol, 100)
                    saved_ha_candles[symbol] = self.websocket_manager.get_latest_ha_candles(symbol, 100)
                    
                    if saved_ha_candles[symbol]:
                        self.logger.info(f"Saving {len(saved_ha_candles[symbol])} HA candles for {symbol}")
            
            # Stop existing connections
            try:
                self.websocket_manager.stop_all_streams()
            except:
                pass
            
            # Small delay before reconnection
            await asyncio.sleep(2)
            
            # Attempt reconnection
            self.websocket_reconnect_attempts += 1
            reconnect_success = await self.setup_websockets()
            
            if reconnect_success and saved_ha_candles:
                # RESTORE CANDLE HISTORY AFTER RECONNECTION
                for symbol, candles in saved_candles.items():
                    if candles and symbol in saved_ha_candles:
                        self.websocket_manager.restore_candle_history(
                            symbol, 
                            candles, 
                            saved_ha_candles[symbol]
                        )
                
                #await self.notifier.send_status_update("WebSocket Reconnected", 
                #    f"✅ Reconnected with history preserved! Candles intact.")
                self.logger.info("WebSocket reconnected with candle history preserved")
            else:
                #await self.notifier.send_error_alert(
                #    f"❌ Health check reconnection failed (Attempt #{self.websocket_reconnect_attempts})")
                self.logger.error("WebSocket health check reconnection failed")
                
        except Exception as e:
            self.logger.error(f"Error checking WebSocket health: {e}")

    async def _process_tick_for_immediate_signals(self, symbol: str, tick_data: Dict):
        """
        CORE FIX: Process signals on every price tick instead of waiting for candle completion
        
        This reduces signal delay from 3-4 minutes to 30-60 seconds
        """
        try:
            price = float(tick_data.get('ltp', 0))
            if price <= 0:
                return
            
            timestamp = datetime.now()
            
            # Update current incomplete candle for strategy analysis
            self._update_current_incomplete_candle(symbol, price, timestamp)
            
            # Check if we can process signals (cooldown to prevent spam)
            if not self._can_process_immediate_signal(symbol, timestamp):
                return
            
            # Get strategy for signal checking
            if not self.strategies:
                return
                
            strategy = self.strategies[0]  # Main strategy
            
            # Check if strategy has enough historical data
            if not hasattr(strategy, 'ha_candles_history'):
                return
                
            candle_count = len(strategy.ha_candles_history)
            if candle_count < 25:  # Need minimum data
                return
            
            # Create real-time market data for strategy
            market_data = self._create_realtime_market_data(symbol, price, timestamp, strategy)
            
            # Check for immediate entry signals
            if not strategy.in_trade and len(self.positions) == 0:
                entry_signal = await strategy.should_enter(market_data)
                if entry_signal:
                    self.logger.info(f"IMMEDIATE ENTRY SIGNAL: {getattr(entry_signal, 'option_type', 'CE')} from real-time processing")
                    await self._execute_immediate_signal(entry_signal)
                    
            # Check for exit signals on existing positions
            await self._check_immediate_exit_signals(strategy, market_data)
            
        except Exception as e:
            self.logger.error(f"Error in immediate signal processing: {e}")

    # ADD this method to TradingBot class:

    def _update_current_incomplete_candle(self, symbol: str, price: float, timestamp: datetime):
        """Update current incomplete candle with each tick"""
        if not hasattr(self, 'current_incomplete_candles'):
            self.current_incomplete_candles = {}
        
        if symbol not in self.current_incomplete_candles:
            self.current_incomplete_candles[symbol] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'start_time': timestamp,
                'tick_count': 1
            }
        else:
            candle = self.current_incomplete_candles[symbol]
            candle['high'] = max(candle['high'], price)
            candle['low'] = min(candle['low'], price)
            candle['close'] = price
            candle['tick_count'] += 1

    # ADD this method to TradingBot class:

    def _can_process_immediate_signal(self, symbol: str, timestamp: datetime) -> bool:
        """Check signal processing cooldown to prevent spam"""
        if not hasattr(self, 'last_immediate_signal_time'):
            self.last_immediate_signal_time = {}
        
        cooldown_seconds = 45  # 45 seconds between signal checks (faster than before)
        
        if symbol not in self.last_immediate_signal_time:
            self.last_immediate_signal_time[symbol] = timestamp
            return True
        
        time_diff = (timestamp - self.last_immediate_signal_time[symbol]).total_seconds()
        
        if time_diff >= cooldown_seconds:
            self.last_immediate_signal_time[symbol] = timestamp
            return True
        
        return False

    # ADD this method to TradingBot class:

    def _create_realtime_market_data(self, symbol: str, price: float, timestamp: datetime, strategy) -> Dict:
        """Create market data using current incomplete candle + historical data"""
        try:
            # Get current incomplete candle
            incomplete_candle = self.current_incomplete_candles.get(symbol, {
                'open': price, 'high': price, 'low': price, 'close': price
            })
            
            # Create HA candle from incomplete data
            ha_candle = {
                'ha_open': incomplete_candle.get('open', price),
                'ha_high': incomplete_candle.get('high', price),
                'ha_low': incomplete_candle.get('low', price),
                'ha_close': incomplete_candle.get('close', price),
                'volume': 0,
                'timestamp': timestamp,
                'symbol': symbol
            }
            
            # Get historical candles from strategy
            ha_candles_history = getattr(strategy, 'ha_candles_history', [])
            
            # Combine historical + current incomplete candle for analysis
            combined_candles = ha_candles_history + [ha_candle]
            
            return {
                'symbol': symbol,
                'ha_candle': ha_candle,
                'ha_candles_history': combined_candles,
                'current_price': price,
                'timestamp': timestamp,
                'price': price,
                'high': ha_candle['ha_high'],
                'low': ha_candle['ha_low'],
                'open': ha_candle['ha_open'],
                'close': ha_candle['ha_close'],
                'instrument_key': 'NSE_INDEX|Nifty 50',
                'realtime_processing': True  # Flag to indicate this is real-time
            }
            
        except Exception as e:
            self.logger.error(f"Error creating real-time market data: {e}")
            return {}

    # ADD this method to TradingBot class:

    async def _check_immediate_exit_signals(self, strategy, market_data: Dict):
        """Check for exit signals on existing positions immediately"""
        try:
            positions_to_check = list(self.positions.values())
            
            for position in positions_to_check:
                exit_order = await strategy.should_exit(position, market_data)
                if exit_order:
                    self.logger.info(f"IMMEDIATE EXIT SIGNAL: {getattr(exit_order, 'exit_reason', 'EXIT')} from real-time processing")
                    await self._execute_immediate_signal(exit_order)
                    
        except Exception as e:
            self.logger.error(f"Error checking immediate exits: {e}")

    # ADD this method to TradingBot class:

    async def _execute_immediate_signal(self, order):
        """Execute signal immediately with rate limiting and notifications"""
        try:
            # Use the rate limiter we implemented in Step 2
            success = await self.upstox_client.rate_limiter.execute_with_rate_limit(
                self._place_order_with_logging, order
            )
            
            if success:
                self.orders.append(order)
                
                # Send notification
                action = "ENTRY" if order.transaction_type.name == "BUY" else "EXIT"
                await self.send_trade_notification(order, action)
                
                # Record trade
                if order.transaction_type.name == "BUY":
                    self.record_trade_entry(order)
                
                self.logger.info(f"IMMEDIATE signal executed: {order.symbol} {action}")
            else:
                self.logger.error(f"Failed to execute immediate signal due to rate limiting")
                
        except Exception as e:
            self.logger.error(f"Error executing immediate signal: {e}")

    # ADD this helper method to TradingBot class:

    async def _place_order_with_logging(self, order):
        """Helper method for rate-limited order placement"""
        try:
            result = await self.place_order(order)
            
            if result:
                option_type = getattr(order, 'option_type', 'UNKNOWN')
                strike_price = getattr(order, 'strike_price', 0)
                action = "BUY" if order.transaction_type.name == "BUY" else "SELL"
                
                self.logger.info(f"Order placed successfully: {action} {strike_price}{option_type} @ Rs.{order.price:.2f}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in order placement: {e}")
            return False

    async def log_market_status_with_analysis(self):
        """Enhanced market status logging with TOTAL candle count - FIXED VERSION"""
        try:
            current_time = datetime.now()

            # Log status every 30 seconds
            if (current_time - self.last_price_update).total_seconds() >= 30:
        
                # Get current NIFTY data
                nifty_symbol = "NIFTY"
                websocket_status = "Connected" if self.websocket_manager else "Disconnected"
        
                # FIXED: Get TOTAL candle count from ALL sources
                total_candles = 0
                data_sources = []
                
                # Source 1: WebSocket persistent candles
                if self.websocket_manager and hasattr(self.websocket_manager, 'persistent_ha_candles'):
                    ws_candles = len(self.websocket_manager.persistent_ha_candles.get(nifty_symbol, []))
                    if ws_candles > 0:
                        total_candles = max(total_candles, ws_candles)
                        data_sources.append(f"WebSocket:{ws_candles}")
                
                # Source 2: Strategy historical candles
                if self.strategies:
                    for strategy in self.strategies:
                        if hasattr(strategy, 'ha_candles_history'):
                            strategy_candles = len(strategy.ha_candles_history)
                            if strategy_candles > 0:
                                total_candles = max(total_candles, strategy_candles)
                                data_sources.append(f"Strategy:{strategy_candles}")
                            break
                
                # Source 3: WebSocket latest candles (fallback)
                if self.websocket_manager and hasattr(self.websocket_manager, 'latest_ha_candles'):
                    if nifty_symbol in self.websocket_manager.latest_ha_candles:
                        latest_candles = len(self.websocket_manager.latest_ha_candles[nifty_symbol])
                        if latest_candles > 0:
                            total_candles = max(total_candles, latest_candles)
                            data_sources.append(f"Latest:{latest_candles}")
        
                # Get current price - FIXED: Safe formatting
                nifty_price_str = "N/A"
                if nifty_symbol in self.latest_ticks:
                    price_value = self.latest_ticks[nifty_symbol].get('ltp')
                    if price_value is not None and isinstance(price_value, (int, float)) and price_value > 0:
                        nifty_price_str = f"Rs.{float(price_value):.2f}"
        
                # Calculate time to next candle - FIXED: Safe time calculation
                next_candle_str = ""
                try:
                    if self.websocket_manager and hasattr(self.websocket_manager, 'candle_aggregator'):
                        current_candle = self.websocket_manager.candle_aggregator.get_current_candle(nifty_symbol)
                        if current_candle and 'start_time' in current_candle:
                            time_elapsed = (current_time - current_candle['start_time']).total_seconds()
                            time_to_next = max(0, 60 - time_elapsed)  # 60 seconds for 1-minute candles
                        next_candle_str = f" | Next: {int(time_to_next)}s"
                except Exception:
                    next_candle_str = ""
        
                # FIXED: Status message based on TOTAL candles
                if total_candles >= 23:
                    status_msg = f"STRATEGY ACTIVE - NIFTY: {nifty_price_str} | Candles: {total_candles} (Ready!) | Sources: {', '.join(data_sources)}{next_candle_str}"
                elif total_candles >= 15:
                    status_msg = f"BUILDING DATA - NIFTY: {nifty_price_str} | Candles: {total_candles}/23 (Almost ready) | Sources: {', '.join(data_sources)}{next_candle_str}"
                else:
                    status_msg = f"COLLECTING DATA - NIFTY: {nifty_price_str} | Candles: {total_candles}/23 (Needs more) | Sources: {', '.join(data_sources)}{next_candle_str}"
        
                self.logger.info(status_msg)
                self.last_price_update = current_time
        
        except Exception as e:
            # FIXED: More detailed error handling but don't crash
            self.logger.debug(f"Market status logging error (non-critical): {e}")
            # Set a simple update time to prevent spam
            self.last_price_update = datetime.now()
            
    async def manual_strategy_execution(self):
        """ENHANCED: Manual execution with real-time conflict prevention"""
        try:
            # Skip if real-time processing is active
            if hasattr(self, 'last_immediate_signal_time'):
                current_time = datetime.now()
                for symbol, last_time in self.last_immediate_signal_time.items():
                    if (current_time - last_time).total_seconds() < 60:  # Skip if recent real-time activity
                        self.logger.debug("Skipping manual execution - real-time processing active")
                        return
            
            # Proceed with existing manual execution logic
            # ... (keep your existing manual_strategy_execution code here)
            
        except Exception as e:
            self.logger.error(f"Error in enhanced manual strategy execution: {e}")

    async def analyze_and_log_signal_conditions(self):
        """Analyze and log why signals are/aren't triggering"""
        try:
            for strategy in self.strategies:
                if not strategy.is_active:
                    continue
                
                # Import PineScriptStrategy locally to avoid circular imports
                from src.strategy.pine_script_strategy import PineScriptStrategy
                
                # Check if this is a Pine Script strategy
                if not isinstance(strategy, PineScriptStrategy):
                    continue
                
                candle_count = len(strategy.ha_candles_history)
                required_candles = strategy.adx_length + 1
                
                if candle_count < required_candles:
                    self.logger.info(f"Signal Check - Building data: {candle_count}/{required_candles} HA candles")
                    continue
                
                # Get latest data for analysis
                latest_candle = strategy.ha_candles_history[-1]
                trend_line = strategy.calculate_trend_line(strategy.ha_candles_history)
                current_price = latest_candle.get('ha_close', 0)
                
                if not trend_line:
                    continue
                
                # Analyze conditions
                strong_green, strong_red, body_pct = strategy.analyze_candle_strength(latest_candle)
                adx, plus_di, minus_di = strategy.calculate_adx(strategy.ha_candles_history)
                
                if not adx:
                    continue
                
                price_above = current_price > trend_line
                trend_ok = adx > strategy.adx_threshold
                price_diff = current_price - trend_line
                price_diff_pct = (price_diff / trend_line) * 100
                
                # Detailed analysis log
                self.logger.info(f"Pine Script Analysis:")
                self.logger.info(f"    Current Price: Rs.{current_price:.2f}")
                self.logger.info(f"    Trend Line: Rs.{trend_line:.2f} ({price_diff:+.2f} | {price_diff_pct:+.2f}%)")
                self.logger.info(f"    Candle: {' Strong Green' if strong_green else ' Weak'} ({body_pct:.1%})")
                self.logger.info(f"    ADX: {adx:.1f} ({'' if trend_ok else ''} > {strategy.adx_threshold})")
                self.logger.info(f"    Position: {' In Trade' if strategy.in_trade else ' Available'}")
                
                # Determine signal status
                buy_conditions = [
                    ("Price above trend", price_above),
                    ("Strong green candle", strong_green),
                    ("ADX > threshold", trend_ok),
                    ("Not in trade", not strategy.in_trade)
                ]
                
                met_conditions = [cond for cond, status in buy_conditions if status]
                missing_conditions = [cond for cond, status in buy_conditions if not status]
                
                if len(met_conditions) == len(buy_conditions):
                    self.logger.info(f"BUY SIGNAL CONDITIONS MET! Ready for next candle confirmation.")
                else:
                    self.logger.info(f"Waiting for: {', '.join(missing_conditions)}")
                    self.logger.info(f"Met: {', '.join(met_conditions)}")
                
        except Exception as e:
            self.logger.error(f"Error analyzing signal conditions: {e}")
    
    async def send_periodic_telegram_update(self):
        """Send periodic comprehensive status updates via Telegram"""
        try:
            current_time = datetime.now()
            
            # Send update every hour during market hours
            if (current_time - self.last_telegram_update).total_seconds() < self.telegram_update_interval:
                return
                
            # Calculate session stats
            session_duration = current_time - self.session_start_time
            hours = int(session_duration.total_seconds() / 3600)
            minutes = int((session_duration.total_seconds() % 3600) / 60)
            
            # Get current NIFTY price
            nifty_price = "N/A"
            nifty_change = ""
            if "NIFTY" in self.latest_ticks:
                price = self.latest_ticks['NIFTY'].get('ltp', 0)
                nifty_price = f"Rs.{price:.2f}"
                
                # Calculate change if we have reference price
                if hasattr(self, 'session_start_price'):
                    change = price - self.session_start_price
                    change_pct = (change / self.session_start_price) * 100
                    nifty_change = f" ({change:+.2f} | {change_pct:+.2f}%)"
            
            # WebSocket status
            ws_status = "✅ Connected"
            if not self.websocket_manager:
                ws_status = "❌ Disconnected"
            elif self.websocket_reconnect_attempts > 0:
                ws_status += f" (Reconnected {self.websocket_reconnect_attempts}x)"
            
            # Signal analysis - Fixed type checking
            signal_status = "🔍 Analyzing..."
            if self.strategies:
                from src.strategy.pine_script_strategy import PineScriptStrategy
                pine_strategy = None
                for strategy in self.strategies:
                    if isinstance(strategy, PineScriptStrategy):
                        pine_strategy = strategy
                        break
                
                if pine_strategy and len(pine_strategy.ha_candles_history) >= 15:
                    signal_status = "Ready for Signals"
                elif pine_strategy:
                    signal_status = f"Building Data ({len(pine_strategy.ha_candles_history)}/23)"
            
            message = f""" *Hourly Status Update*

🕐 *Session Time:* {hours}h {minutes}m
📈 *NIFTY:* {nifty_price}{nifty_change}
🔗 *WebSocket:* {ws_status}
🤖 *Strategy:* {signal_status}

📊 *Performance Today:*
🎯 *Trades:* {self.total_trades}
💵 *P&L:* Rs.{self.total_pnl:,.2f}
✅ *Win Rate:* {(self.winning_trades/max(1,self.total_trades))*100:.1f}%
🏆 *Best Trade:* Rs.{self.best_trade:,.2f}

🎯 *Pine Script Status:*
📊 *Target Accuracy:* 67%
🔍 *Monitoring:* Trend + Green Candle + ADX
⏳ *Waiting for:* Bullish Setup

💪 *Bot Status:* Active & Monitoring!"""
            
            await self.notifier.send_message(message)
            self.last_telegram_update = current_time
            
        except Exception as e:
            self.logger.error(f"Error sending periodic Telegram update: {e}")
    
    async def evaluate_strategies_on_new_candle(self, symbol: str, ha_candle: Dict):
        """Evaluate all strategies when a new HA candle is completed"""
        try:
            if not self.is_market_open():
                return
                
            for strategy in self.strategies:
                if not strategy.is_active:
                    continue
                    
                # Prepare market data with HA candle for Pine Script strategy
                market_data = self.prepare_market_data_for_strategy(symbol, ha_candle)
                
                # Check for entry signals
                entry_order = await strategy.should_enter(market_data)
                if entry_order:
                    if await self.place_order(entry_order):
                        self.orders.append(entry_order)
                        await strategy.on_order_filled(entry_order)
                
                # Check for exit signals on existing positions
                for position_key, position in list(self.positions.items()):
                    if position.symbol == symbol:
                        exit_order = await strategy.should_exit(position, market_data)
                        if exit_order:
                            if await self.place_order(exit_order):
                                self.orders.append(exit_order)
                                await strategy.on_order_filled(exit_order)
                                if exit_order.quantity >= position.quantity:
                                    del self.positions[position_key]
                                    
        except Exception as e:
            self.logger.error(f"Error evaluating strategies: {e}")
    
    # 🆕 ENHANCED: Send trade notification with daily count
    async def send_trade_notification(self, order: Order, action: str):
        """FIXED: Symbol formatting in notifications"""
        try:

            option_type = getattr(order, 'option_type', 'PE')
            strike_price = getattr(order, 'strike_price', 0)
            strike_symbol = getattr(order, 'strike_symbol', f"{strike_price}{option_type}")

            # Get daily trade count
            today_entries = len([t for t in self.daily_trades 
                               if t.get('date') == datetime.now().date() and t.get('type') == 'ENTRY'])
        
            # Calculate investment details
            lot_size = getattr(order, 'lot_size', 75)
            total_shares = order.quantity * lot_size
            total_investment = getattr(order, 'total_investment', order.price * total_shares)

            # Get option details
            option_type = getattr(order, 'option_type', 'CE')
            strike_price = getattr(order, 'strike_price', 0)
            strike_symbol = getattr(order, 'strike_symbol', f"{strike_price}{option_type}")
            #strike_symbol = getattr(order, 'strike_symbol', f"{int(order.price * 200)}{option_type}")
            lot_size = getattr(order, 'lot_size', 75)
            total_investment = getattr(order, 'total_investment', order.price * order.quantity * lot_size)

            # Get daily trade count
            today_entries = len([t for t in getattr(self, 'daily_trades', [])
                           if t.get('date') == datetime.now().date() and t.get('type') == 'ENTRY'])
        
            if action == "ENTRY":
                # Entry notification with daily status
                direction = "BULLISH 📈" if option_type == 'CE' else "BEARISH 📉"
            
                message = f"""🚀 *OPTION TRADE EXECUTED - AstraRise Bot*

📊 *SIGNAL:* {direction} {option_type} Option
🎯 *Strike:* {strike_symbol}
📈 *Symbol:* NIFTY {order.symbol}

💰 *TRADE DETAILS:*
🔹 *Action:* BUY {order.quantity} lot ({order.quantity * 75} shares)
🔹 *Premium:* Rs.{order.price:.2f} per share
🔹 *Investment:* Rs.{getattr(order, 'total_investment', order.price * order.quantity * 75):,.2f}

📊 *DAILY TRADE STATUS:*
🎯 *Today's Trades:* {len(self.daily_trades)}/{self.max_daily_trades}
🚦 *Status:* {'✅ Can Trade' if len(self.daily_trades) < self.max_daily_trades else '🛑 Limit Reached'}

⏰ *Entry Time:* {datetime.now().strftime('%I:%M:%S %p')}

Strategy: {order.strategy_name}"""
            
            else:  # EXIT
                # Exit notification
                exit_reason = getattr(order, 'exit_reason', 'EXIT_SIGNAL')
                pnl = getattr(order, 'total_pnl', 0)
                pnl_pct = getattr(order, 'pnl_pct', 0)
            
                status_emoji = "🟢" if pnl > 0 else "🔴"
                status_text = "PROFIT" if pnl > 0 else "LOSS"
            
                message = f"""📊 *TRADE CLOSED - AstraRise Bot*

{status_emoji} *{status_text}:* Rs.{abs(pnl):,.2f} ({pnl_pct:+.2f}%)

📈 *TRADE DETAILS:*
🔹 *Symbol:* {order.symbol}
🔹 *Strike:* {strike_symbol}
🔹 *Exit Reason:* {exit_reason}
🔹 *Exit Price:* Rs.{order.price:.2f}

📊 *Daily Status:* {len(self.daily_trades)}/{self.max_daily_trades} trades used
⏰ *Exit Time:* {datetime.now().strftime('%I:%M:%S %p')}"""
        
            await self.notifier.send_message(message)
        
        #    if hasattr(self, 'notifier') and self.notifier:
        #       await self.notifier.send_message(message)
        #    else:
        #        self.logger.info(f"NOTIFICATION: {message}")
        
        except Exception as e:
            self.logger.error(f"❌ Error sending trade notification: {e}")

    def prepare_market_data_for_strategy(self, symbol: str, ha_candle: Dict) -> Dict:
        """Prepare comprehensive market data for strategy evaluation"""
        
        # Get historical data if available
        historical_candles = []
        historical_ha_candles = []
        
        if self.websocket_manager:
            historical_candles = self.websocket_manager.get_latest_candles(symbol, 50)
            historical_ha_candles = self.websocket_manager.get_latest_ha_candles(symbol, 50)
        
        # Get current tick data
        current_tick = self.latest_ticks.get(symbol, {})
        
        market_data = {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'price': ha_candle.get('ha_close', 0),
            'ha_candle': ha_candle,
            'current_tick': current_tick,
            'historical_candles': historical_candles,
            'historical_ha_candles': historical_ha_candles,
            'instrument_key': current_tick.get('instrument_key', ''),
            
            # For backward compatibility
            'high': ha_candle.get('ha_high', 0),
            'low': ha_candle.get('ha_low', 0),
            'volume': ha_candle.get('volume', 0),
            'open': ha_candle.get('ha_open', 0),
            'close': ha_candle.get('ha_close', 0)
        }
        
        return market_data
    
    def _extract_symbol_from_key(self, instrument_key: str) -> str:
        """Extract symbol from instrument key"""
        key_to_symbol = {
            'NSE_INDEX|Nifty 50': 'NIFTY',
            'NSE_INDEX|Nifty Bank': 'BANKNIFTY',
            'BSE_INDEX|SENSEX': 'SENSEX',
            'NSE_FO|50201': 'NIFTY_FUT',
            'NSE_FO|26009': 'BANKNIFTY_FUT'
        }
        
        return key_to_symbol.get(instrument_key, instrument_key.split('|')[-1] if '|' in instrument_key else instrument_key)
    
    async def authenticate(self):
        """Authenticate with Upstox"""
        
        if self.upstox_client.access_token:
            self.logger.info("Found stored access token, testing...")
            
            if await self.upstox_client.test_token():
                self.logger.info("Stored token is valid, using it")
                await self.notifier.send_status_update("Authenticated", "Using stored access token")
                return True
            else:
                self.logger.info("Stored token is invalid, requesting new authentication")
        
        print(f"Please visit: {self.upstox_client.get_login_url()}")
        auth_code = input("Enter the authorization code: ")
        
        if await self.upstox_client.get_access_token(auth_code):
            self.logger.info("Successfully authenticated with Upstox")
            #await self.notifier.send_status_update("Authenticated", "Successfully connected to Upstox API")
            return True
        else:
            self.logger.error("Failed to authenticate with Upstox")
            #await self.notifier.send_error_alert("Failed to authenticate with Upstox")
            return False
    
    async def place_order(self, order: Order) -> bool:
        """Enhanced order placement with proper notifications"""
        try:
            
            self.logger.info(f"ATTEMPTING TO PLACE ORDER: {order.symbol}")
            self.logger.info(f"  Type: {order.transaction_type.value}")
            self.logger.info(f"  Quantity: {order.quantity}")
            self.logger.info(f"  Price: Rs.{order.price:.2f}")
            
            if self.paper_trading:
                # Enhanced paper trading simulation
                order.status = OrderStatus.FILLED
                order.filled_price = order.price
                order.filled_quantity = order.quantity
                order.order_id = f"PAPER_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                lot_size = getattr(order, 'lot_size', 75)
                total_investment = order.price * order.quantity * lot_size

                self.logger.info("=== PAPER TRADE EXECUTED ===")
                self.logger.info(f"Order ID: {order.order_id}")
                self.logger.info(f"Symbol: {order.symbol}")
                self.logger.info(f"Investment: Rs.{total_investment:,.2f}")
                self.logger.info("============================")

                
                # Extract option details
                #strike_price = getattr(order, 'strike_price', 0)
                #option_type = getattr(order, 'option_type', 'UNKNOWN')
                #greeks = getattr(order, 'greeks', {})
                
                # Calculate investment details
                #lot_size = 75
                #total_investment = order.quantity * lot_size * order.price
                #total_shares = order.quantity * lot_size
                
                 # Get order details
                lot_size = getattr(order, 'lot_size', 75)
                total_investment = getattr(order, 'total_investment', order.price * order.quantity * lot_size)
                
                # Log the trade
                self.trading_logger.info(
                    f"PAPER TRADE - {order.transaction_type.value} {order.quantity} lot "
                    f"of {getattr(order, 'strike_symbol', order.symbol)} @ Rs.{order.price:.2f}"
                )
                self.trading_logger.info(f"Investment: Rs.{total_investment:,.2f}")
            
                if order.transaction_type == TransactionType.BUY:
                    # Send entry notification
                    greeks = self._calculate_synthetic_greeks(
                        getattr(order, 'option_type', 'CE'),
                        getattr(order, 'strike_price', 24450),
                        order.price
                    )
                    #await self.send_option_trade_notification(order, total_investment, greeks)
                    self.logger.info(f"Synthetic Greeks: Δ{greeks['delta']}, Θ{greeks['theta']}, V{greeks['vega']}, Γ{greeks['gamma']}, Risk:{greeks['risk_score']}")
                    
                    # Update positions
                    # await self.update_paper_positions(order)
                
                elif order.transaction_type == TransactionType.SELL:
                    # Get position for P&L calculation
                    position_key = f"{order.symbol}_{order.instrument_key or 'default'}"
                    position = self.positions.get(position_key)
                
                    if position:
                        lot_size = 75
                        pnl = (order.price - position.average_price) * position.quantity * lot_size

                        # UPDATE STATISTICS - THIS WAS MISSING
                        self.update_trade_statistics(pnl, pnl > 0)
                        
                        # Send exit notification
                        await self.send_exit_notification(order, position, 0)
                    
                        # Update positions
                        await self.update_paper_positions(order)
            
                return True
            
            else:
                # Real trading implementation would go here
                self.logger.warning("Live trading not implemented yet")
                return False
            
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return False            
    
    def _calculate_synthetic_greeks(self, option_type: str, strike_price: float, premium: float) -> Dict:
        """Calculate synthetic Greeks for paper trading"""
        try:
            if option_type == 'CE':
                delta = 0.5  # ATM CE
                theta = -premium * 0.1  # 10% daily decay
                vega = premium * 0.2
            else:  # PE
                delta = -0.5  # ATM PE
                theta = -premium * 0.1
                vega = premium * 0.2
        
            # Risk score based on theta
            risk_score = "HIGH" if abs(theta) > 25 else "MODERATE" if abs(theta) > 15 else "LOW"
        
            return {
                'delta': delta,
                'theta': theta,
                'vega': vega,
                'gamma': 0.01,
                'risk_score': risk_score
            }
        
        except Exception as e:
            self.logger.error(f"Error calculating Greeks: {e}")
            return {'delta': 0, 'theta': 0, 'vega': 0, 'gamma': 0, 'risk_score': 'UNKNOWN'}
    
    async def send_option_trade_notification(self, order: Order, total_investment: float, greeks: Dict):
        """Send option trade notification with correct details"""
        try:
            option_type = getattr(order, 'option_type', 'UNKNOWN')
            strike_symbol = getattr(order, 'strike_symbol', 'UNKNOWN')
            lot_size = getattr(order, 'lot_size', 75)
        
            direction = "BULLISH 📈" if option_type == 'CE' else "BEARISH 📉"
        
            # Calculate correct values
            actual_shares = order.quantity * lot_size
            actual_investment = getattr(order, 'total_investment', order.price * actual_shares)
        
            # Capital calculations
            current_capital = 50000 + self.total_pnl
            used_percentage = (actual_investment / current_capital) * 100
            remaining_capital = current_capital - actual_investment
        
            message = f"""🎯 *OPTION TRADE EXECUTED - AstraRise Bot*

📊 *SIGNAL:* {direction} {option_type} Option
🎯 *Strike:* {strike_symbol}
📈 *Symbol:* NIFTY {strike_symbol}

💰 *TRADE DETAILS:*
🔹 *Action:* BUY {order.quantity} lot ({actual_shares} shares)
🔹 *Premium:* Rs.{order.price:.2f} per share
🔹 *Investment:* Rs.{actual_investment:,.2f}

📈 *CAPITAL STATUS:*
💵 *Total Capital:* Rs.{current_capital:,.2f}
💸 *Used:* Rs.{actual_investment:,.2f} ({used_percentage:.1f}%)
💰 *Available:* Rs.{remaining_capital:,.2f}

⏰ *Entry Time:* {datetime.now().strftime('%I:%M:%S %p')}

🎯 *TARGETS:*
📈 *Target:* 50% (Rs.{order.price * 1.5:.2f})
🛑 *Stop Loss:* 30% (Rs.{order.price * 0.7:.2f})
📊 *Trailing Stop:* Active after 50% profit

Strategy: {order.strategy_name}"""
        
            await self.notifier.send_message(message)
        
        except Exception as e:
            self.logger.error(f"Error sending trade notification: {e}")
            
            
    async def update_option_positions(self, order: Order):
        """Update paper positions with option-specific tracking"""
        try:
            position_key = f"{order.symbol}_{getattr(order, 'strategy_name', 'default')}"
            option_type = getattr(order, 'option_type', 'UNKNOWN')
            
            if order.transaction_type == TransactionType.BUY:
                entry_time = datetime.now()
                
                # Create position with option details
                position = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    average_price=order.price,
                    current_price=order.price,
                    pnl=0,
                    unrealized_pnl=0,
                    instrument_key=order.instrument_key or 'default'
                )
                
                # Add option-specific attributes
                position.entry_time = entry_time
                position.option_type = option_type
                position.strike_price = getattr(order, 'strike_price', 0)
                position.expiry = getattr(order, 'expiry', 'Unknown')
                position.entry_greeks = getattr(order, 'greeks', {})
                position.strategy_name = getattr(order, 'strategy_name', 'Unknown')
                
                self.positions[position_key] = position
                
                # Update tracking
                if option_type == 'CE':
                    self.trade_performance['ce_trades'] += 1
                elif option_type == 'PE':
                    self.trade_performance['pe_trades'] += 1
                
                # Track Greeks validation
                if hasattr(order, 'greeks') and order.greeks:
                    self.trade_performance['greeks_validated_trades'] += 1
            
            elif order.transaction_type == TransactionType.SELL:
                if position_key in self.positions:
                    existing = self.positions[position_key]
                    
                    # Calculate option-specific P&L
                    lot_size = 75
                    pnl = (order.price - existing.average_price) * existing.quantity * lot_size
                    
                    # Calculate Greeks impact (if available)
                    entry_greeks = getattr(existing, 'entry_greeks', {})
                    theta_impact = self._calculate_theta_impact(existing, entry_greeks)
                    delta_impact = self._calculate_delta_impact(existing, entry_greeks)
                    
                    # Update global statistics
                    self.total_pnl += pnl
                    self.total_trades += 1
                    
                    # Update option-specific statistics
                    if existing.option_type == 'CE':
                        if pnl > 0:
                            self.trade_performance['ce_wins'] += 1
                    elif existing.option_type == 'PE':
                        if pnl > 0:
                            self.trade_performance['pe_wins'] += 1
                    
                    if pnl > 0:
                        self.winning_trades += 1
                    
                    # Update Greeks tracking
                    self.trade_performance['total_theta_decay'] += theta_impact
                    self.trade_performance['total_delta_pnl'] += delta_impact
                    
                    # Track performance records
                    if pnl > self.best_trade:
                        self.best_trade = pnl
                    if pnl < self.worst_trade:
                        self.worst_trade = pnl
                    
                    # Send enhanced P&L notification
                    await self.send_option_pnl_notification(existing, pnl, order.price, entry_greeks)
                    
                    # Remove closed position
                    del self.positions[position_key]
                    
        except Exception as e:
            self.logger.error(f"Error updating option positions: {e}")
            

    def _calculate_theta_impact(self, position, entry_greeks: Dict) -> float:
        """Calculate the impact of theta (time decay) on P&L"""
        try:
            if not entry_greeks:
                return 0
            
            entry_time = getattr(position, 'entry_time', datetime.now())
            current_time = datetime.now()
            days_held = (current_time - entry_time).total_seconds() / (24 * 3600)
            
            theta_per_day = entry_greeks.get('theta', 0)
            lot_size = 75
            
            # Theta impact = theta per day * days held * quantity * lot size
            theta_impact = theta_per_day * days_held * position.quantity * lot_size
            
            return theta_impact
            
        except Exception as e:
            self.logger.error(f"Error calculating theta impact: {e}")
            return 0
    
    def _calculate_delta_impact(self, position, entry_greeks: Dict) -> float:
        """Calculate the impact of delta (price movement) on P&L"""
        try:
            if not entry_greeks:
                return 0
            
            # This would require current spot price vs entry spot price
            # For now, return approximate delta contribution
            delta = entry_greeks.get('delta', 0)
            price_change = position.current_price - position.average_price
            lot_size = 75
            
            # Approximate delta impact
            delta_impact = delta * price_change * position.quantity * lot_size
            
            return delta_impact
            
        except Exception as e:
            return 0
    
    async def send_option_pnl_notification(self, position, pnl: float, exit_price: float, entry_greeks: Dict):
        """Send comprehensive option P&L notification with Greeks analysis"""
        try:
            entry_price = position.average_price
            entry_time = getattr(position, 'entry_time', datetime.now())
            exit_time = datetime.now()
            option_type = getattr(position, 'option_type', 'UNKNOWN')
            strike_price = getattr(position, 'strike_price', 0)
            strategy_name = getattr(position, 'strategy_name', 'Unknown')
            
            # Calculate trade metrics
            lot_size = 75
            total_shares = position.quantity * lot_size
            trade_value = entry_price * total_shares
            pnl_pct = (pnl / trade_value) * 100 if trade_value > 0 else 0
            
            # Calculate duration
            duration = exit_time - entry_time
            duration_minutes = int(duration.total_seconds() / 60)
            duration_hours = duration_minutes // 60
            duration_mins = duration_minutes % 60
            
            # Greeks impact analysis
            theta_impact = self._calculate_theta_impact(position, entry_greeks)
            delta_impact = self._calculate_delta_impact(position, entry_greeks)
            
            # Status and emoji
            status_emoji = "🟢" if pnl > 0 else "🔴"
            status_text = "PROFIT" if pnl > 0 else "LOSS"
            direction_emoji = "📈" if option_type == 'CE' else "📉"
            
            # Performance tracking
            ce_win_rate = (self.trade_performance['ce_wins'] / max(1, self.trade_performance['ce_trades'])) * 100
            pe_win_rate = (self.trade_performance['pe_wins'] / max(1, self.trade_performance['pe_trades'])) * 100
            overall_win_rate = (self.winning_trades / max(1, self.total_trades)) * 100
            
            message = f"""📊 *OPTION TRADE CLOSED - {strategy_name}*

{status_emoji} *{status_text}:* Rs.{abs(pnl):,.2f} ({pnl_pct:+.2f}%)

📈 *OPTION DETAILS:*
🔹 *Type:* {option_type} {direction_emoji} | *Strike:* {strike_price}
🔹 *Quantity:* {position.quantity} lots ({total_shares:,} shares)
🔹 *Entry Premium:* Rs.{entry_price:.2f}
🔹 *Exit Premium:* Rs.{exit_price:.2f}
🔹 *Premium Change:* Rs.{exit_price - entry_price:+.2f}

⏰ *TIMING:*
📅 *Entry:* {entry_time.strftime('%I:%M:%S %p')}
📅 *Exit:* {exit_time.strftime('%I:%M:%S %p')}
⏱️ *Duration:* {duration_hours}h {duration_mins}m

📊 *GREEKS IMPACT ANALYSIS:*
🔸 *Theta Decay:* Rs.{theta_impact:.2f} (Time impact)
🔸 *Delta Movement:* Rs.{delta_impact:.2f} (Price impact)
🔸 *Entry Delta:* {entry_greeks.get('delta', 0):.3f}
🔸 *Entry Theta:* Rs.{entry_greeks.get('theta', 0):.2f}/day

📊 *STRATEGY PERFORMANCE:*
🎯 *{option_type} Win Rate:* {ce_win_rate if option_type == 'CE' else pe_win_rate:.1f}%
🎯 *Overall Win Rate:* {overall_win_rate:.1f}%
🎯 *Total Trades:* {self.total_trades}
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}

📈 *BACKTESTED TARGETS:*
🎯 *Target Win Rate:* 67%
💰 *Avg Target Profit:* Rs.890
📊 *Current vs Target:* {'✅ On Track' if overall_win_rate >= 60 else '⚠️ Below Target'}

🏆 *RECORDS:*
🥇 *Best Trade:* Rs.{self.best_trade:,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:,.2f}

{"🎉 Great trade! Strategy working as expected!" if pnl > 0 else "💪 Stay disciplined! Next one will be better!"}

📊 *Greeks Learning:* {self._get_greeks_insight(entry_greeks, pnl, duration_hours)}"""
            
            await self.notifier.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending option P&L notification: {e}")
    
    def _get_greeks_insight(self, entry_greeks: Dict, pnl: float, duration_hours: float) -> str:
        """Generate educational insights about Greeks performance"""
        try:
            delta = entry_greeks.get('delta', 0)
            theta = entry_greeks.get('theta', 0)
            
            insights = []
            
            # Delta insights
            if abs(delta) > 0.7:
                insights.append(f"High delta ({delta:.2f}) meant high price sensitivity")
            elif abs(delta) < 0.3:
                insights.append(f"Low delta ({delta:.2f}) meant lower price impact")
            
            # Theta insights
            if abs(theta) > 20:
                insights.append(f"High theta decay (Rs.{abs(theta):.0f}/day) was a major factor")
            
            # Duration insights
            if duration_hours < 1:
                insights.append("Quick scalp trade - time decay minimal")
            elif duration_hours > 4:
                insights.append("Longer hold - theta decay significant")
            
            return " | ".join(insights) if insights else "Greeks performed as expected"
            
        except Exception as e:
            return "Greeks analysis unavailable"
    
    
    async def send_enhanced_status_update(self):
        """Send enhanced status update with options and Greeks performance"""
        try:
            current_time = datetime.now()
            
            # Calculate session stats
            session_duration = current_time - self.session_start_time
            hours = int(session_duration.total_seconds() / 3600)
            minutes = int((session_duration.total_seconds() % 3600) / 60)
            
            # Option-specific performance
            ce_trades = self.trade_performance['ce_trades']
            pe_trades = self.trade_performance['pe_trades']
            ce_win_rate = (self.trade_performance['ce_wins'] / max(1, ce_trades)) * 100
            pe_win_rate = (self.trade_performance['pe_wins'] / max(1, pe_trades)) * 100
            
            # Greeks performance
            avg_theta_impact = self.trade_performance['total_theta_decay'] / max(1, self.total_trades)
            greeks_usage = (self.trade_performance['greeks_validated_trades'] / max(1, self.total_trades)) * 100
            
            # Get current NIFTY price
            nifty_price = "N/A"
            if "NIFTY" in self.latest_ticks:
                price = self.latest_ticks['NIFTY'].get('ltp', 0)
                nifty_price = f"Rs.{price:.2f}"
            
            # Backtest comparison
            expected_metrics = self.backtest_manager.get_expected_performance_metrics()
            current_vs_expected = "On Track" if (self.winning_trades/max(1,self.total_trades))*100 >= 60 else "Below Target"
            
            message = f"""📊 *ENHANCED STRATEGY STATUS - AstraRise Bot*

🕐 *Session:* {hours}h {minutes}m | 📈 *NIFTY:* {nifty_price}

💼 *OPTION TRADING PERFORMANCE:*
📈 *CE Trades:* {ce_trades} | Win Rate: {ce_win_rate:.1f}%
📉 *PE Trades:* {pe_trades} | Win Rate: {pe_win_rate:.1f}%
🎯 *Overall:* {self.total_trades} trades | {(self.winning_trades/max(1,self.total_trades))*100:.1f}% win rate

📊 *GREEKS ANALYTICS:*
🔸 *Greeks Validation:* {greeks_usage:.0f}% of trades
🔸 *Avg Theta Impact:* Rs.{avg_theta_impact:.0f} per trade
🔸 *Delta Exposure:* Balanced CE/PE strategy

💰 *FINANCIAL SUMMARY:*
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}
🏆 *Best Trade:* Rs.{self.best_trade:,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:,.2f}

🎯 *BACKTESTED EXPECTATIONS:*
📊 *Target Win Rate:* {expected_metrics['expected_win_rate']:.0f}%
💰 *Expected Monthly:* {expected_metrics['expected_monthly_return']:.1f}%
📈 *Performance Status:* {current_vs_expected}

🎯 *STRATEGY INSIGHTS:*
• Options selection: ATM for trends, ITM for strong signals
• Greeks filtering active: Max theta Rs.25/day
• Risk management: Max Rs.15k per trade
• Market condition: {'Trending' if self.total_trades > 3 else 'Building position'}

🤖 *NEXT ACTIONS:*
• Monitoring for Pine Script signals
• Greeks validation active
• Real-time option chain analysis
• Auto-strike selection enabled

💪 Enhanced strategy with backtested 67% win rate target! 🚀"""
            
            await self.notifier.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending enhanced status update: {e}")
    
    async def send_enhanced_trade_notification(self, order: Order, total_investment: float):
        """Send enhanced trade notification via Telegram"""
        try:
            lot_size = 75
            total_shares = order.quantity * lot_size
            current_capital = 40000 + self.total_pnl
            
            if order.transaction_type == TransactionType.BUY:
                message = f"""🚀 *BUY SIGNAL - AstraRise Bot*

📊 *NIFTY Analysis:* Pine Script Bullish Signal Detected!
🎯 *Conditions Met:* Price > Trend + Strong Green + ADX > 20

💰 *PAPER TRADE EXECUTED:*
🔹 *Symbol:* {order.symbol}
🔹 *Action:* BUY {order.quantity} lots ({total_shares:,} shares)
🔹 *Price:* Rs.{order.price:.2f} per share
🔹 *Investment:* Rs.{total_investment:,.2f}

📈 *Capital Management:*
💵 *Total Capital:* Rs.{current_capital:,.2f}
💸 *Used:* Rs.{total_investment:,.2f} ({(total_investment/current_capital)*100:.1f}%)
💰 *Remaining:* Rs.{current_capital - total_investment:,.2f}

⏰ *Time:* {datetime.now().strftime('%I:%M:%S %p')}
🗓️ *Date:* {datetime.now().strftime('%B %d, %Y')}

🎯 Pine Script strategy in action! Let's see the results! 🚀"""
                
                await self.notifier.send_message(message)
                
        except Exception as e:
            self.logger.error(f"Error sending enhanced trade notification: {e}")
    
    def update_trade_statistics(self, pnl: float, is_winning: bool):
        """Update trade statistics for hourly report"""
        self.total_trades += 1
        
        if is_winning:
            self.winning_trades += 1
        
        self.total_pnl += pnl
        self.daily_pnl += pnl
        
        # Update best/worst trades
        if pnl > self.best_trade:
            self.best_trade = pnl
        if pnl < self.worst_trade:
            self.worst_trade = pnl
        
        # Log for debugging
        self.logger.info(f"STATS UPDATED: Total trades: {self.total_trades}, P&L: Rs.{self.total_pnl:.2f}")
        self.logger.info(f"STATS UPDATE: updated log Trade #{self.total_trades}, P&L: Rs.{pnl:.2f}, Total P&L: Rs.{self.total_pnl:.2f}")

    async def update_paper_positions(self, order: Order):
        """Update paper trading positions with tracking"""
        try:
            position_key = f"{order.symbol}_{order.instrument_key or 'default'}"
            
            if order.transaction_type == TransactionType.BUY:
                entry_time = datetime.now()
                
                if position_key in self.positions:
                    existing = self.positions[position_key]
                    total_quantity = existing.quantity + order.quantity
                    total_cost = (existing.quantity * existing.average_price) + (order.quantity * order.price)
                    new_avg_price = total_cost / total_quantity
                    
                    existing.quantity = total_quantity
                    existing.average_price = new_avg_price
                else:
                    position = Position(
                        symbol=order.symbol,
                        quantity=order.quantity,
                        average_price=order.price,
                        current_price=order.price,
                        pnl=0,
                        unrealized_pnl=0,
                        instrument_key=order.instrument_key or 'default'
                    )
                    position.entry_time = entry_time
                    self.positions[position_key] = position
            
            elif order.transaction_type == TransactionType.SELL:
                if position_key in self.positions:
                    existing = self.positions[position_key]
                    entry_time = getattr(existing, 'entry_time', datetime.now())
                    exit_time = datetime.now()
                    
                    
                    if order.quantity >= existing.quantity:
                        # Close position completely
                        lot_size = 75
                        pnl = (order.price - existing.average_price) * existing.quantity * 75
                        self.update_trade_statistics(pnl, pnl > 0)
                        # Update statistics
                        self.total_pnl += pnl
                        self.total_trades += 1
                        
                        if pnl > 0:
                            self.winning_trades += 1
                        
                        if pnl > self.best_trade:
                            self.best_trade = pnl
                        if pnl < self.worst_trade:
                            self.worst_trade = pnl
                        
                        # Send P&L notification
                        await self.send_pnl_notification(order.symbol, pnl, existing.average_price, 
                                                       order.price, existing.quantity, entry_time, exit_time)
                        
                        del self.positions[position_key]
                        self.trading_logger.info(f"Position closed: {order.symbol} P&L: Rs.{pnl:.2f}")
                    else:
                        # Partial close
                        existing.quantity -= order.quantity
                        
        except Exception as e:
            self.logger.error(f"Error updating paper positions: {e}")
    
    async def send_pnl_notification(self, symbol: str, pnl: float, entry_price: float, 
                                  exit_price: float, quantity: int, entry_time: datetime, exit_time: datetime):
        """Send comprehensive P&L notification"""
        try:
            lot_size = 75
            total_shares = quantity * lot_size
            trade_value = entry_price * total_shares
            pnl_pct = (pnl / trade_value) * 100 if trade_value > 0 else 0
            
            # Calculate trade duration
            duration = exit_time - entry_time
            duration_minutes = int(duration.total_seconds() / 60)
            duration_hours = duration_minutes // 60
            duration_mins = duration_minutes % 60
            
            # Determine status
            status_emoji = "🟢" if pnl > 0 else "🔴"
            status_text = "PROFIT" if pnl > 0 else "LOSS"
            
            # Calculate win rate
            win_rate = (self.winning_trades / max(1, self.total_trades)) * 100
            
            message = f"""📊 *TRADE COMPLETED - AstraRise Bot*

{status_emoji} *{status_text}:* Rs.{abs(pnl):,.2f} ({pnl_pct:+.2f}%)

📈 *Trade Details:*
🔹 *Symbol:* {symbol}
🔹 *Quantity:* {quantity} lots ({total_shares:,} shares)
🔹 *Entry Price:* Rs.{entry_price:.2f}
🔹 *Exit Price:* Rs.{exit_price:.2f}
🔹 *Price Change:* Rs.{exit_price - entry_price:+.2f}

⏰ *Timing:*
📅 *Entry:* {entry_time.strftime('%I:%M:%S %p')}
📅 *Exit:* {exit_time.strftime('%I:%M:%S %p')}
⏱️ *Duration:* {duration_hours}h {duration_mins}m

📊 *Session Performance:*
🎯 *Total Trades:* {self.total_trades}
✅ *Winning Trades:* {self.winning_trades} ({win_rate:.1f}%)
💵 *Total P&L:* Rs.{self.total_pnl:,.2f}
📈 *Pine Script Target:* 67% (Current: {win_rate:.1f}%)

🏆 *Records:*
🥇 *Best Trade:* Rs.{self.best_trade:,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:,.2f}

{"🎉 Excellent work!" if pnl > 0 else "💪 Stay strong, next one will be better!"}"""
            
            await self.notifier.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending P&L notification: {e}")
    
    async def update_positions(self):
        """Update current positions with real-time prices"""
        try:
            if not self.paper_trading:
                # Real positions update would go here
                pass
            else:
                # Update paper positions with current market prices
                for position_key, position in self.positions.items():
                    symbol = position.symbol
                    if symbol in self.latest_ticks:
                        current_price = float(self.latest_ticks[symbol].get('ltp', position.current_price))
                        position.current_price = current_price
                        position.unrealized_pnl = (current_price - position.average_price) * position.quantity
                
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}")
    
    
    async def run(self):
        """Enhanced main bot execution loop with optimized API monitoring"""
        self.logger.info("Starting enhanced trading bot...")

        # Authenticate
        if not await self.authenticate():
            return

        # Setup websockets
        websocket_success = await self.setup_websockets()

        # RECOVER LOST POSITIONS
        self.logger.info("Checking for lost positions...")
        for strategy in self.strategies:
            if hasattr(strategy, 'recover_lost_positions'):
                await strategy.recover_lost_positions()
                    
        # Send startup notification
        await self.notifier.send_message(f"""🚀 *AstraRise Trading Bot Started - NIFTY Focus*

📊 *STRATEGY: Pine Script V5 + Real Options*
💰 *Capital:* Rs.50,000 | *Max Trade:* Rs.15,000

🎯 *OPTION TRADING LOGIC:*
📈 *Uptrend Signal* → Buy NIFTY CE (Call) options
📉 *Downtrend Signal* → Buy NIFTY PE (Put) options

⚙️ *PINE SCRIPT SIGNALS:*
✅ Price above trend + Strong green + ADX>20 → *CE BUY*
❌ Price below trend + Strong red + ADX>20 → *PE BUY*

🏷️ *STRIKE SELECTION:*
🎯 *Mode:* ATM (At The Money)
📊 *Example:* NIFTY@24,978 → Buy 25000CE or 24950PE
💵 *Premium Range:* Rs.10-200 per share

🔄 *REAL-TIME FEATURES:*
📡 Live option premiums from Upstox API
📊 Bid-ask spread validation
🛡️ Liquidity and premium checks

Bot ready for NIFTY option trading! 🚀""")

        self.is_running = True
        last_hourly_report = datetime.now()
        last_square_off_check = datetime.now()
        last_optimized_monitoring = datetime.now()  # New monitoring tracker

        try:
            while self.is_running:
                current_time = datetime.now()
            
                if self.is_market_open():
                    # Check for auto square-off time (3:20 PM)
                    if current_time.time() >= time(15, 20) and \
                        (current_time - last_square_off_check).total_seconds() > 60:
                        await self.auto_square_off_all_positions()
                        last_square_off_check = current_time
                
                    # Send hourly report
                    if (current_time - last_hourly_report).total_seconds() >= 3600:
                        await self.send_hourly_report()
                        last_hourly_report = current_time
                
                    # OPTIMIZED POSITION MONITORING (every 90 seconds)
                    if (current_time - last_optimized_monitoring).total_seconds() >= 90:
                        self.logger.info("=== OPTIMIZED POSITION MONITORING ===")
                        monitoring_success = False
                        
                        for strategy in self.strategies:
                            if hasattr(strategy, 'monitor_positions_simple'):
                                try:
                                    position_data = await strategy.monitor_positions_simple()
                                    if position_data:
                                        self.logger.info(f"SUCCESS: Monitored {len(position_data)} positions")
                                        monitoring_success = True
                                    else:
                                        self.logger.warning("No position data received")
                                except Exception as e:
                                    self.logger.error(f"Error in optimized monitoring: {e}")
                        
                        if not monitoring_success:
                            self.logger.warning("Optimized monitoring failed - using fallback")
                            # Fallback to old monitoring if needed
                            for strategy in self.strategies:
                                if hasattr(strategy, 'monitor_option_prices'):
                                    try:
                                        await strategy.monitor_option_prices()
                                    except Exception as e:
                                        self.logger.error(f"Fallback monitoring error: {e}")
                        
                        last_optimized_monitoring = current_time
                        self.logger.info("=== MONITORING CYCLE COMPLETE ===")
                    
                    # Regular operations (reduced frequency)
                    await self.check_websocket_health()
                    await self.log_market_status_with_analysis()
                    await self.update_positions()
                    await self.process_pending_websocket_callbacks()
                    await self.manual_strategy_execution()
                
                    # Check trailing stops for all positions
                    await self.update_trailing_stops()
                
                    # Increased sleep time to reduce overall API pressure
                    await asyncio.sleep(45)  # Increased from 30 to 45 seconds
                else:
                    # Send end-of-day summary
                    if current_time.time() >= time(15, 30) and current_time.time() < time(15, 31):
                        await self.send_end_of_day_summary()
                        await self.send_daily_summary()
                        await asyncio.sleep(60)
                
                    self.logger.info("Market closed, waiting...")
                    await asyncio.sleep(300)
                
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            await self.send_shutdown_summary()
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            #await self.notifier.send_error_alert(f"Bot crashed: {str(e)}")
        finally:
            if self.websocket_manager:
                self.websocket_manager.stop_all_streams()
            self.is_running = False
    
    async def update_trailing_stops(self):
        """Update trailing stops for all positions"""
        try:
            for position_key, position in self.positions.items():
                # Get current price
                symbol = position.symbol.replace('_CE', '').replace('_PE', '')
                current_price = self.latest_ticks.get(symbol, {}).get('ltp', position.current_price)
            
                # Calculate current P&L
                entry_price = position.average_price
                current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
            
                # Get current trailing stop
                trailing_stop = getattr(position, 'trailing_stop', -30)  # Default 30% stop loss
            
                # Check trailing stop levels from strategy config
                trailing_stops = [
                    {'profit': 0.50, 'trail_to': 0.00},  # At 50% profit, trail to breakeven
                    {'profit': 0.60, 'trail_to': 0.40},  # At 60% profit, trail to 40%
                    {'profit': 0.70, 'trail_to': 0.40},  # At 70% profit, trail to 40%
                    {'profit': 0.80, 'trail_to': 0.50},  # At 80% profit, trail to 50%
                    {'profit': 1.00, 'trail_to': 0.70},  # At 100% profit, trail to 70%
                ]                    
                    
                for level in trailing_stops:
                    if current_pnl_pct >= level['profit']:
                        if trailing_stop < level['trail_to']:
                            position.trailing_stop = level['trail_to']
                            self.logger.info(f"Trailing stop updated to {level['trail_to']}% for {position.symbol}")
                        
                            # Send notification
                            await self.notifier.send_message(
                                f"📊 *Trailing Stop Updated*\n"
                                f"Symbol: {getattr(position, 'strike_symbol', position.symbol)}\n"
                                f"Current P&L: {current_pnl_pct:.1f}%\n"
                                f"New Stop: {level['trail_to']}%"
                            )
    
        except Exception as e:
            self.logger.error(f"Error updating trailing stops: {e}")

    async def send_daily_summary(self):
        """Send comprehensive end-of-day summary"""
        try:
            # Calculate statistics
            total_trades_today = len([t for t in self.trades_today if t['time'].date() == datetime.now().date()])
        
            win_rate = (self.winning_trades / max(1, self.total_trades)) * 100

            message = f"""📊 *DAILY SUMMARY - {datetime.now().strftime('%B %d, %Y')}*

📈 *TRADING PERFORMANCE:*
🎯 *Total Trades:* {self.total_trades}
✅ *Winning Trades:* {self.winning_trades}
❌ *Losing Trades:* {self.total_trades - self.winning_trades}
📊 *Win Rate:* {win_rate:.1f}%

💰 *P&L SUMMARY:*
📈 *Day's P&L:* Rs.{self.daily_pnl:,.2f}
💵 *Total P&L:* Rs.{self.total_pnl:,.2f}
🏆 *Best Trade:* Rs.{self.best_trade:,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:,.2f}

📊 *CAPITAL ANALYSIS:*
💵 *Starting Capital:* Rs.50,000
💰 *Ending Capital:* Rs.{50000 + self.total_pnl:,.2f}
📈 *Return:* {(self.total_pnl/50000)*100:+.2f}%

🎯 *STRATEGY METRICS:*
📊 *Target (67% win rate):* {'✅ Achieved' if win_rate >= 67 else f'❌ Current: {win_rate:.1f}%'}
🔹 *ADX Threshold:* 20 (Working well)
🔹 *Candle Strength:* 40% (Optimal)

⏰ *TRADES BY TIME:*
🔹 Morning (9:30-12:00): {len([t for t in self.trades_today if 9 <= t['time'].hour < 12])} trades
🔹 Afternoon (12:00-15:20): {len([t for t in self.trades_today if 12 <= t['time'].hour < 16])} trades

Great work today! See you tomorrow! 🌟"""
        
            await self.notifier.send_message(message)
        
            # Reset daily counters
            self.daily_pnl = 0
            self.trades_today = []
        
        except Exception as e:
            self.logger.error(f"Error sending daily summary: {e}")

    async def send_shutdown_summary(self):
        """Send summary when bot is stopped"""
        try:
            session_duration = datetime.now() - self.session_start_time
            hours = int(session_duration.total_seconds() / 3600)
            minutes = int((session_duration.total_seconds() % 3600) / 60)
        
            message = f"""🛑 *AstraRise Bot Stopped*

⏱️ *Session Duration:* {hours}h {minutes}m

📊 *Final Statistics:*
🎯 *Total Trades:* {self.total_trades}
✅ *Win Rate:* {(self.winning_trades/max(1,self.total_trades))*100:.1f}%
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}

Thanks for trading! 👋"""
        
            await self.notifier.send_message(message)
        
        except Exception as e:
            self.logger.error(f"Error sending shutdown summary: {e}")

    
    async def run_strategies_with_rest_api(self):
        """Fallback method using REST API when websockets fail"""
        for strategy in self.strategies:
            if not strategy.is_active:
                continue
                
            try:
                # Placeholder for REST API implementation
                market_data = {
                    'symbol': 'FALLBACK',
                    'price': 0,
                    'timestamp': datetime.now()
                }
                
                # Check for entry signals
                entry_order = await strategy.should_enter(market_data)
                if entry_order:
                    if await self.place_order(entry_order):
                        self.orders.append(entry_order)
                
                # Check for exit signals
                for position in self.positions.values():
                    exit_order = await strategy.should_exit(position, market_data)
                    if exit_order:
                        if await self.place_order(exit_order):
                            self.orders.append(exit_order)
                            
            except Exception as e:
                await strategy.on_error(e)
                #await self.notifier.send_error_alert(f"Strategy {strategy.name} error: {str(e)}")
           
    async def send_exit_notification(self, order: Order, position: Position, pnl: float):
        """Send exit notification with P&L details"""
        try:
            option_type = getattr(order, 'option_type', 'CE')
            strike_symbol = getattr(order, 'strike_symbol', 'UNKNOWN')
            exit_reason = getattr(order, 'exit_reason', 'MANUAL')
            entry_price = getattr(order, 'entry_price', position.average_price)
            lot_size = getattr(position, 'lot_size', 75)
        
            # Calculate P&L
            total_shares = position.quantity * lot_size
            entry_value = entry_price * total_shares
            exit_value = order.price * total_shares
            pnl = exit_value - entry_value
            pnl_pct = (pnl / entry_value) * 100
        
            status_emoji = "🟢" if pnl > 0 else "🔴"
            status_text = "PROFIT" if pnl > 0 else "LOSS"
        
            # Update tracking
            self.daily_pnl += pnl
            self.total_pnl += pnl
            self.total_trades += 1
            if pnl > 0:
                self.winning_trades += 1
        
            message = f"""📊 *TRADE CLOSED - AstraRise Bot*

            {status_emoji} *{status_text}:* Rs.{abs(pnl):,.2f} ({pnl_pct:+.2f}%)

📈 *TRADE DETAILS:*
🔹 *Symbol:* NIFTY {strike_symbol}
🔹 *Entry:* Rs.{entry_price:.2f}
🔹 *Exit:* Rs.{order.price:.2f}
🔹 *Quantity:* {position.quantity} lot ({total_shares} shares)
🔹 *Exit Reason:* {exit_reason}

💰 *P&L CALCULATION:*
📥 *Entry Value:* Rs.{entry_value:,.2f}
📤 *Exit Value:* Rs.{exit_value:,.2f}
💵 *Net P&L:* Rs.{pnl:,.2f}

📊 *SESSION STATS:*
🎯 *Total Trades:* {self.total_trades}
✅ *Win Rate:* {(self.winning_trades/max(1,self.total_trades))*100:.1f}%
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}
📈 *Today's P&L:* Rs.{self.daily_pnl:,.2f}

⏰ *Exit Time:* {datetime.now().strftime('%I:%M:%S %p')}"""
        
            await self.notifier.send_message(message)
        
        except Exception as e:
            self.logger.error(f"Error sending exit notification: {e}")

    async def send_hourly_report(self):
        """Send hourly performance report with correct stats"""
        try:
            current_time = datetime.now()

            # Calculate session duration
            session_duration = current_time - self.session_start_time
            hours = int(session_duration.total_seconds() / 3600)
            minutes = int((session_duration.total_seconds() % 3600) / 60)
            
            # Get active positions count
            active_positions = len(self.positions) # + len(getattr(self, 'active_option_positions', {}))
            if hasattr(self, 'active_option_positions'):
                active_positions += len(self.active_option_positions)
            # Calculate win rate
            win_rate = (self.winning_trades / max(1, self.total_trades)) * 100
            
            # Get current NIFTY price
            nifty_price = "N/A"
            try:
                # Method 1: Check latest_ticks
                if hasattr(self, 'latest_ticks') and self.latest_ticks:
                    for symbol, tick_data in self.latest_ticks.items():
                        if 'NIFTY' in symbol:
                            price = tick_data.get('ltp', 0)
                            if price > 0:
                                nifty_price = f"Rs.{price:.2f}"
                                break
    
                # Method 2: Check websocket manager ticks
                if nifty_price == "N/A" and hasattr(self, 'websocket_manager'):
                    if hasattr(self.websocket_manager, 'latest_ticks'):
                        for symbol, tick_data in self.websocket_manager.latest_ticks.items():
                            if 'NIFTY' in symbol:
                                price = tick_data.get('ltp', 0)
                                if price > 0:
                                    nifty_price = f"Rs.{price:.2f}"
                                    break
    
                # Method 3: Get from recent candle data
                if nifty_price == "N/A" and hasattr(self, 'websocket_manager'):
                    if hasattr(self.websocket_manager, 'persistent_ha_candles'):
                        nifty_candles = self.websocket_manager.persistent_ha_candles.get('NIFTY', [])
                        if nifty_candles:
                            latest_candle = nifty_candles[-1]
                            price = latest_candle.get('ha_close', 0)
                            if price > 0:
                                nifty_price = f"Rs.{price:.2f}"
    
            except Exception as e:
                self.logger.error(f"Error getting NIFTY price: {e}")
            
            message = f"""📊 *HOURLY REPORT - {current_time.strftime('%I:%M %p')}*

⏰ *Session Time:* {hours}h {minutes}m

📈 *MARKET STATUS:*
🔹 NIFTY: {nifty_price}
📍 *Active Positions:* {active_positions}

💼 *TRADING SUMMARY:*
🎯 *Total Trades:* {self.total_trades}
✅ *Winning Trades:* {self.winning_trades}
❌ *Losing Trades:* {self.total_trades - self.winning_trades}
📊 *Win Rate:* {win_rate:.1f}%

💰 *P&L STATUS:*
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}
🏆 *Best Trade:* Rs.{self.best_trade:,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:,.2f}

🎯 *CAPITAL STATUS:*
💵 *Total Capital:* Rs.50,000
💸 *Capital in Use:* Rs.{sum(p.average_price * p.quantity * 75 for p in self.positions.values()):,.2f}
💰 *Available:* Rs.{50000 - sum(p.average_price * p.quantity * 75 for p in self.positions.values()):,.2f}

⏰ *Next Actions:*
🔹 New entries stop at: 3:10 PM
🔹 Auto square-off at: 3:20 PM

Keep monitoring! 💪"""
            
            await self.notifier.send_message(message)
            self.logger.info("Hourly report sent successfully")
            
        except Exception as e:
            self.logger.error(f"Error sending hourly report: {e}")
            # Don't crash the bot if reporting fails

    async def auto_square_off_all_positions(self):
        """Auto square-off all positions at 3:20 PM"""
        try:
            if not self.positions:
                return
        
            self.logger.info("AUTO SQUARE-OFF TIME - Closing all positions")

            positions_to_close = list(self.positions.values())

            for position in positions_to_close:
                # Get current market price
                symbol = position.symbol.replace('_CE', '').replace('_PE', '')
                current_price = self.latest_ticks.get(symbol, {}).get('ltp', position.current_price)
            
                # Create exit order
                exit_order = Order(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    price=current_price,
                    order_type=OrderType.MARKET,
                    transaction_type=TransactionType.SELL,
                    strategy_name="AUTO_SQUARE_OFF"
                )
            
                exit_order.exit_reason = "AUTO_SQUARE_OFF_3:20PM"
                exit_order.option_type = getattr(position, 'option_type', 'CE')
                exit_order.strike_symbol = getattr(position, 'strike_symbol', '')
                exit_order.entry_price = position.average_price
            
                # Place exit order
                if await self.place_order(exit_order):
                    # Calculate and send P&L notification
                    await self.send_exit_notification(exit_order, position, 0)
                
                    # Remove position
                    position_key = f"{position.symbol}_{position.instrument_key}"
                    if position_key in self.positions:
                        del self.positions[position_key]
        
            self.logger.info(f"Auto squared-off {len(positions_to_close)} positions")
        
        except Exception as e:
            self.logger.error(f"Error in auto square-off: {e}")
    
    
    async def fixed_single_notification(self, order: Order, total_investment: float):
        """FIXED: Send only ONE comprehensive notification"""
        
        try:
            # Get all required details
            option_type = getattr(order, 'option_type', 'CE')
            strike_symbol = getattr(order, 'strike_symbol', f"{int(order.price * 200)}{option_type}")
            strike_price = getattr(order, 'strike_price', int(order.price * 200))
            lot_size = getattr(order, 'lot_size', 75)
            
            # CONSISTENT CAPITAL CALCULATION
            base_capital = 50000  # Use ONE consistent value
            total_shares = order.quantity * lot_size
            actual_investment = order.price * total_shares  # Correct calculation
            used_percentage = (actual_investment / base_capital) * 100
            remaining_capital = base_capital - actual_investment
            
            # Direction and emoji
            direction = "BULLISH 📈" if option_type == 'CE' else "BEARISH 📉"
            
            # SINGLE COMPREHENSIVE MESSAGE
            message = f"""🚀 *OPTION TRADE EXECUTED - AstraRise Bot*

📊 *SIGNAL:* {direction} {option_type} Option
🎯 *Strike:* {strike_symbol}
📈 *Symbol:* NIFTY {strike_symbol}

💰 *TRADE DETAILS:*
🔹 *Action:* BUY {order.quantity} lot ({total_shares} shares)
🔹 *Premium:* Rs.{order.price:.2f} per share
🔹 *Investment:* Rs.{actual_investment:,.2f}

📈 *CAPITAL STATUS:*
💵 *Total Capital:* Rs.{base_capital:,}
💸 *Used:* Rs.{actual_investment:,.2f} ({used_percentage:.1f}%)
💰 *Available:* Rs.{remaining_capital:,.2f}

⏰ *Entry Time:* {datetime.now().strftime('%I:%M:%S %p')}

🎯 *TARGETS:*
📈 *Target:* 50% (Rs.{order.price * 1.5:.2f})
🛑 *Stop Loss:* 30% (Rs.{order.price * 0.7:.2f})
📊 *Trailing Stop:* Active after 50% profit

Strategy: {order.strategy_name}"""

            await self.notifier.send_message(message)
            
            # LOG THE NOTIFICATION TO VERIFY
            self.logger.info(f"SINGLE notification sent: {strike_symbol} - Rs.{actual_investment:,.2f}")
            
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")
            
    async def fixed_single_exit_notification(self, position, exit_price: float, 
                                           exit_reason: str, pnl: float):
        """FIXED: Send only ONE comprehensive exit notification"""
        
        try:
            entry_price = position.average_price
            entry_time = getattr(position, 'entry_time', datetime.now())
            exit_time = datetime.now()
            option_type = getattr(position, 'option_type', 'CE')
            strike_symbol = getattr(position, 'strike_symbol', 'UNKNOWN')
            
            # Calculate accurate trade metrics
            lot_size = 75
            total_shares = position.quantity * lot_size
            entry_value = entry_price * total_shares
            exit_value = exit_price * total_shares
            actual_pnl = exit_value - entry_value
            pnl_pct = (actual_pnl / entry_value) * 100 if entry_value > 0 else 0
            
            # Calculate duration
            duration = exit_time - entry_time
            duration_minutes = int(duration.total_seconds() / 60)
            duration_hours = duration_minutes // 60
            duration_mins = duration_minutes % 60
            
            # Status indicators
            status_emoji = "🟢" if actual_pnl > 0 else "🔴"
            status_text = "PROFIT" if actual_pnl > 0 else "LOSS"
            
            # ✅ SINGLE COMPREHENSIVE EXIT MESSAGE
            message = f"""📊 *TRADE CLOSED - AstraRise Bot*

{status_emoji} *{status_text}:* Rs.{abs(actual_pnl):,.2f} ({pnl_pct:+.2f}%)

📈 *TRADE DETAILS:*
🔹 *Symbol:* NIFTY {strike_symbol}
🔹 *Entry:* Rs.{entry_price:.2f}
🔹 *Exit:* Rs.{exit_price:.2f}
🔹 *Quantity:* {position.quantity} lot ({total_shares} shares)
🔹 *Exit Reason:* {exit_reason}

💰 *P&L CALCULATION:*
📥 *Entry Value:* Rs.{entry_value:,.2f}
📤 *Exit Value:* Rs.{exit_value:,.2f}
💵 *Net P&L:* Rs.{actual_pnl:+,.2f}

⏰ *TIMING:*
📅 *Entry:* {entry_time.strftime('%I:%M:%S %p')}
📅 *Exit:* {exit_time.strftime('%I:%M:%S %p')}
⏱️ *Duration:* {duration_hours}h {duration_mins}m

📊 *SESSION STATS:*
🎯 *Total Trades:* {self.total_trades}
✅ *Win Rate:* {(self.winning_trades/max(1,self.total_trades))*100:.1f}%
💵 *Session P&L:* Rs.{self.total_pnl:,.2f}

⏰ *Exit Time:* {exit_time.strftime('%I:%M:%S %p')}

{"🎉 Great trade!" if actual_pnl > 0 else "💪 Stay strong, next one will be better!"}"""

            await self.notifier.send_message(message)
            
            # LOG SINGLE EXIT NOTIFICATION
            self.logger.info(f"SINGLE exit notification sent: {strike_symbol} - P&L: Rs.{actual_pnl:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error sending exit notification: {e}")

    # 🆕 NEW METHOD: Enhanced exit processing
    async def _process_all_exits_enhanced(self, strategy, market_data: Dict, symbol: str):
        """ENHANCED: Process exit signals for all positions with better tracking"""
        try:
            # Get positions from multiple sources
            all_positions = []
        
            # 1. Get positions from bot-level tracking
            bot_positions = [pos for pos in self.positions.values() 
                            if pos.symbol.startswith(symbol) or symbol in pos.symbol]
            all_positions.extend(bot_positions)
        
            # 2. Get positions from strategy-level tracking
            if hasattr(strategy, 'active_option_positions'):
                for pos_key, pos_data in strategy.active_option_positions.items():
                    if symbol in pos_key or pos_data.get('symbol', '').startswith(symbol):
                        # Convert strategy position data to Position object
                        strategy_position = self._create_position_from_strategy_data(pos_data)
                        if strategy_position:
                            all_positions.append(strategy_position)
        
            # Remove duplicates based on symbol
            unique_positions = {}
            for pos in all_positions:
                key = pos.symbol
                if key not in unique_positions:
                    unique_positions[key] = pos
        
            positions_to_check = list(unique_positions.values())
        
            if positions_to_check:
                self.logger.info(f"🔍 Checking {len(positions_to_check)} positions for exit...")
        
                for j, position in enumerate(positions_to_check):
                    try:
                        self.logger.info(f"📊 Checking exit for position {j+1}: {position.symbol}")
                    
                        exit_order = await strategy.should_exit(position, market_data)
                        if exit_order:
                            option_type = getattr(exit_order, 'option_type', 'CE')
                            exit_reason = getattr(exit_order, 'exit_reason', 'EXIT_SIGNAL')
                        
                            self.logger.info(f"*** EXIT SIGNAL *** {option_type} - {exit_reason}")
                    
                            if await self.place_order(exit_order):
                                self.orders.append(exit_order)
                                await strategy.on_order_filled(exit_order)
                                await self.send_trade_notification(exit_order, "EXIT")
                        
                                # 🆕 ENHANCED POSITION CLEANUP
                                await self._cleanup_position_after_exit_enhanced(position, exit_order, strategy)
                            
                                self.logger.info(f"✅ Exit order executed: {exit_reason}")
                            else:
                                self.logger.error(f"❌ Failed to place exit order")
                        else:
                            self.logger.debug(f"No exit signal for {position.symbol}")
                
                    except Exception as exit_error:
                        self.logger.error(f"❌ Error processing exit for position {j+1}: {exit_error}")
            else:
                self.logger.debug(f"No positions to check for {symbol}")
    
        except Exception as e:
            self.logger.error(f"❌ Error processing exits: {e}")

    # 🆕 NEW METHOD: Create Position from strategy data
    def _create_position_from_strategy_data(self, pos_data: Dict):
        """Convert strategy position data to Position object"""
        try:
            from src.models.position import Position
        
            position = Position(
                symbol=pos_data.get('symbol', ''),
                quantity=pos_data.get('quantity', 0),
                average_price=pos_data.get('entry_premium', 0),
                current_price=pos_data.get('current_premium', pos_data.get('entry_premium', 0)),
                pnl=0,
                unrealized_pnl=0,
                instrument_key=pos_data.get('instrument_key', '')
            )
        
            # Add option-specific attributes
            position.option_type = pos_data.get('option_type', 'CE')
            position.strike_price = pos_data.get('strike_price', 0)
            position.entry_time = pos_data.get('entry_time', datetime.now())
        
            return position
        
        except Exception as e:
            self.logger.error(f"❌ Error creating position from strategy data: {e}")
            return None

    # 🆕 NEW METHOD: Enhanced position cleanup
    async def _cleanup_position_after_exit_enhanced(self, position, exit_order, strategy):
        """ENHANCED: Clean up position from all tracking systems"""
        try:
            position_symbol = position.symbol
        
            # 1. Remove from bot-level positions
            keys_to_remove = []
            for key, pos in self.positions.items():
                if pos.symbol == position_symbol:
                    keys_to_remove.append(key)
        
            for key in keys_to_remove:
                if key in self.positions:
                    del self.positions[key]
                    self.logger.info(f"🧹 Removed bot position: {key}")
        
            # 2. Remove from strategy-level positions
            if hasattr(strategy, 'active_option_positions'):
                strategy_keys_to_remove = []
                for key, pos_data in strategy.active_option_positions.items():
                    if pos_data.get('symbol') == position_symbol:
                        strategy_keys_to_remove.append(key)
            
                for key in strategy_keys_to_remove:
                    strategy.active_option_positions.pop(key, None)
                    self.logger.info(f"🧹 Removed strategy position: {key}")
        
            # 3. Update position counters
            if hasattr(strategy, 'position_count'):
                strategy.position_count = len(getattr(strategy, 'active_option_positions', {}))
        
            # 4. Release capital if tracked
            if hasattr(strategy, 'used_capital'):
                lot_size = getattr(exit_order, 'lot_size', 75)
                released_capital = position.average_price * position.quantity * lot_size
                strategy.used_capital = max(0, strategy.used_capital - released_capital)
                self.logger.info(f"💰 Released capital: Rs.{released_capital:,.2f}")
        
            self.logger.info(f"✅ Enhanced position cleanup completed for {position_symbol}")
        
        except Exception as e:
            self.logger.error(f"❌ Error in enhanced position cleanup: {e}")

        # 🆕 NEW METHOD: Check daily trade limit
    def _check_daily_trade_limit(self) -> bool:
        """Check if daily trade limit has been reached"""
        try:
            current_date = datetime.now().date()
        
            # Reset daily trades if new day
            if current_date != self.current_date:
                self.daily_trades = []
                self.current_date = current_date
                self.logger.info(f"🗓️ New trading day: {current_date} - Reset daily trade count")
        
            # Count today's entry trades only
            today_entries = len([trade for trade in self.daily_trades 
                               if trade.get('date') == current_date and trade.get('type') == 'ENTRY'])
        
            can_trade = today_entries < self.max_daily_trades

            if not can_trade:
                self.logger.warning(f"🚫 Daily trade limit reached: {today_entries}/{self.max_daily_trades}")
            else:
                self.logger.info(f"📊 Daily trades: {today_entries}/{self.max_daily_trades} - Can trade: ✅")
        
            return can_trade

        except Exception as e:
            self.logger.error(f"❌ Error checking daily trade limit: {e}")
            return True  # Allow trading if error

    def test_statistics_update(self):
        """Test statistics update manually"""
        self.update_trade_statistics(500.0, True)   # Winning trade
        self.update_trade_statistics(-200.0, False) # Losing trade
        self.logger.info(f"Test: {self.total_trades} trades, Rs.{self.total_pnl:.2f} P&L")

    # 🆕 NEW METHOD: Record daily trade
    def _record_daily_trade(self, order):
        """FIXED: Consistent daily trade recording"""
        try:
            current_date = datetime.now().date()
            
            # Initialize if needed
            if not hasattr(self, 'daily_trades'):
                self.daily_trades = []
            if not hasattr(self, 'current_date'):
                self.current_date = current_date


            # Reset if new day
            if not hasattr(self, 'current_date') or current_date != self.current_date:
                self.daily_trades = []
                self.current_date = current_date
            
            # Record trade
            if order.transaction_type == TransactionType.BUY:
                trade_record = {
                    'date': current_date,
                    'time': datetime.now(),
                    'symbol': order.symbol,
                    'type': 'ENTRY',
                    'strike_price': getattr(order, 'strike_price', 0),
                    'option_type': getattr(order, 'option_type', 'CE')
                }
                self.daily_trades.append(trade_record)
                
                # Update counter consistently
                entry_count = len([t for t in self.daily_trades if t['type'] == 'ENTRY'])
                self.logger.info(f"[NOTE] Recorded daily trade #{entry_count}: {order.symbol}")
                
        except Exception as e:
            self.logger.error(f"Error recording daily trade: {e}")

    async def get_rate_limit_status(self):
        """Get current API rate limiting status"""
        return self.rate_limiter.get_rate_limit_status()
        

class PriceMovementSimulation:
    """Simulate realistic price movements for paper trading"""
    
    def __init__(self):
        self.price_history = {}  # Track price movements
        
    def simulate_option_price_movement(self, entry_price: float, time_elapsed_minutes: int, 
                                     market_direction: str = 'neutral') -> float:
        """Simulate realistic option price movement"""
        
        try:
            # Base volatility (options are more volatile than underlying)
            base_volatility = 0.02  # 2% per hour base volatility
            
            # Time decay effect (theta)
            time_hours = time_elapsed_minutes / 60
            theta_decay = -0.01 * time_hours  # 1% decay per hour (simplified)
            
            # Random price movement
            import random
            random_factor = random.uniform(-0.15, 0.15)  # ±15% random movement
            
            # Market direction bias
            direction_bias = 0
            if market_direction == 'bullish':
                direction_bias = 0.05  # 5% upward bias
            elif market_direction == 'bearish':
                direction_bias = -0.05  # 5% downward bias
            
            # Combine all factors
            total_change = random_factor + direction_bias + theta_decay
            
            # Apply change to entry price
            new_price = entry_price * (1 + total_change)
            
            # Ensure reasonable bounds
            new_price = max(new_price, entry_price * 0.5)  # Max 50% loss
            new_price = min(new_price, entry_price * 3.0)  # Max 300% gain
            
            # Round to realistic values
            return round(new_price, 2)
            
        except Exception as e:
            self.logger.error(f"Error simulating price movement: {e}")
            # Fallback: small random change
            return round(entry_price * random.uniform(0.8, 1.3), 2)
        
    async def send_end_of_day_summary(self):
        """Send comprehensive end-of-day P&L summary"""
        try:
            win_rate = (self.winning_trades / max(1, self.total_trades)) * 100
        
            message = f"""📊 *END-OF-DAY SUMMARY - {datetime.now().strftime('%B %d, %Y')}*

💼 *TRADING PERFORMANCE:*
🎯 *Total Trades:* {self.total_trades}
✅ *Winning:* {self.winning_trades}
❌ *Losing:* {self.total_trades - self.winning_trades}
📊 *Win Rate:* {win_rate:.1f}%

💰 *P&L SUMMARY:*
💵 *Total P&L:* Rs.{self.total_pnl:+,.2f}
🏆 *Best Trade:* Rs.{self.best_trade:+,.2f}
📉 *Worst Trade:* Rs.{self.worst_trade:+,.2f}

💸 *CAPITAL ANALYSIS:*
🏦 *Starting Capital:* Rs.50,000
💰 *Ending Capital:* Rs.{50000 + self.total_pnl:,.2f}
📈 *Return:* {(self.total_pnl/50000)*100:+.2f}%

Trading day completed! 🏁"""

            await self.notifier.send_message(message)
            self.logger.info(f"End-of-day summary sent - {self.total_trades} trades, Rs.{self.total_pnl:.2f} P&L")
        
        except Exception as e:
            self.logger.error(f"Error sending end-of-day summary: {e}")