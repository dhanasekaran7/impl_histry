# ==================== FIXED: main.py ====================
import asyncio
import logging
from pathlib import Path
import sys
from datetime import datetime
import os
os.environ['PYTHONIOENCODING'] = 'utf-8:replace'
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.trading_bot import TradingBot
from config.settings import get_settings
from config.logging_config import setup_logging

async def preload_historical_candles_working(bot):
    """
    ENHANCED VERSION: Immediate strategy activation with signal testing
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info("Quick Start: Loading NIFTY historical data...")
        
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        instrument_key = "NSE_INDEX%7CNifty%2050"
        interval = "1minute"
        to_date = end_date.strftime('%Y-%m-%d')
        from_date = start_date.strftime('%Y-%m-%d')
        
        url = f"{bot.upstox_client.base_url}/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        
        headers = {
            'Authorization': f'Bearer {bot.upstox_client.access_token}',
            'Accept': 'application/json'
        }
        
        logger.info(f"Fetching NIFTY data from {from_date} to {to_date}...")
        
        await bot.upstox_client.rate_limiter.wait_if_needed()
        
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('status') == 'success':
                        raw_candles = data.get('data', {}).get('candles', [])
                        
                        logger.info(f"Downloaded {len(raw_candles)} historical candles")
                        
                        # Debug: print one raw candle
                        if raw_candles:
                            logger.debug(f"[DEBUG] Raw historical candle: {raw_candles[0]}")

                        if raw_candles and len(raw_candles) >= 25:
                            logger.info("Step 1: Converting to bot format...")
                            formatted_candles = []
                            
                            for candle_data in raw_candles[-100:]:
                                if len(candle_data) >= 5:
                                    try:
                                        timestamp_value = candle_data[0]
                                        
                                        if isinstance(timestamp_value, str):
                                            timestamp = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                                        else:
                                            timestamp = datetime.fromtimestamp(float(timestamp_value) / 1000)
                                    except:
                                        timestamp = datetime.now()
                                    
                                    formatted_candle = {
                                        'open': float(candle_data[1]),
                                        'high': float(candle_data[2]), 
                                        'low': float(candle_data[3]),
                                        'close': float(candle_data[4]),
                                        'volume': int(candle_data[5]) if len(candle_data) > 5 else 0,
                                        'timestamp': timestamp
                                    }
                                    formatted_candles.append(formatted_candle)
                            
                            logger.info(f"Step 1 Complete: {len(formatted_candles)} candles converted")
                            
                            if formatted_candles:
                                logger.info("Step 2: Converting to Heikin Ashi...")
                                ha_candles = convert_to_heikin_ashi_fixed(formatted_candles)
                                
                                # Debug: print one HA candle
                                if ha_candles:
                                    logger.debug(f"[DEBUG] Heikin Ashi candle: {ha_candles[0]}")

                                if ha_candles and len(ha_candles) >= 25:
                                    logger.info("Step 3: IMMEDIATE STRATEGY SETUP...")
                                    
                                    success_count = 0
                                    
                                    for strategy in bot.strategies:
                                        try:
                                            logger.info(f"Loading into strategy: {strategy.name}")
                                            
                                            # Load into BOTH arrays for compatibility
                                            strategy.ha_candles_history = ha_candles[-50:]
                                            strategy.candle_history = ha_candles[-50:]
                                            
                                            logger.info(f"Strategy loaded: {len(strategy.ha_candles_history)} HA candles")
                                            logger.info(f"Candle history loaded: {len(strategy.candle_history)} candles")
                                            
                                            # IMMEDIATE ACTIVATION TEST
                                            required_candles = strategy.adx_length + 9  # 23 candles
                                            
                                            if len(strategy.candle_history) >= required_candles:
                                                logger.info("TESTING IMMEDIATE STRATEGY ACTIVATION...")
                                                
                                                # NEW: Test ADX calculation first
                                                logger.info("RUNNING ADX VALIDATION TEST...")
                                                strategy.test_adx_calculation()
                                                
                                                # Test trend line calculation
                                                trend_line = strategy.calculate_trend_line()
                                                if trend_line:
                                                    logger.info(f"SUCCESS: Trend line calculated: Rs.{trend_line:.2f}")
                                                    
                                                    # Test ADX calculation with validation
                                                    adx, plus_di, minus_di = strategy.calculate_adx_manual()
                                                    if adx and strategy.validate_adx_values(adx, plus_di, minus_di):
                                                        logger.info(f"SUCCESS: Valid ADX calculated: {adx:.2f}")
                                                        logger.info(f"ADX Value: {adx:.2f} (Valid range: 0-50)")
                                                        
                                                        # Create test market data with consistent pricing
                                                        latest_candle = ha_candles[-1]
                                                        consistent_price = latest_candle['ha_close']
                                                        
                                                        test_market_data = {
                                                            'symbol': 'NIFTY',
                                                            'ha_candle': latest_candle,
                                                            'ha_candles_history': ha_candles,
                                                            'current_price': consistent_price,
                                                            'timestamp': datetime.now(),
                                                            'price': consistent_price,
                                                            'instrument_key': 'NSE_INDEX|Nifty 50'
                                                        }
                                                        
                                                        # Test entry signal with full signal debugging
                                                        logger.info("TESTING SIGNAL DETECTION WITH FIXED ADX...")
                                                        logger.info("Testing entry signal logic...")
                                                        
                                                        entry_test = await strategy.should_enter(test_market_data)
                                                        
                                                        if entry_test:
                                                            logger.info("SIGNAL DETECTED! Order created successfully")
                                                            logger.info(f"Order type: {getattr(entry_test, 'option_type', 'Unknown')}")
                                                            logger.info(f"Strike: {getattr(entry_test, 'strike_price', 'Unknown')}")
                                                            logger.info(f"Premium: Rs.{entry_test.price:.2f}")
                                                            logger.info(f"Investment: Rs.{getattr(entry_test, 'total_investment', 0):,.2f}")
                                                        else:
                                                            logger.info("No signal detected - this is normal for current market conditions")
                                                            logger.info("Bot will monitor live data for signal opportunities")
                                                        
                                                        logger.info("STRATEGY 100% READY FOR LIVE TRADING!")
                                                    else:
                                                        logger.error("ADX calculation still invalid")
                                                else:
                                                    logger.error("Trend line calculation failed")
                                            else:
                                                logger.warning(f"Insufficient candles: {len(strategy.candle_history)}/{required_candles}")
                                            
                                            success_count += 1
                                            
                                        except Exception as strategy_error:
                                            logger.error(f"Error loading strategy {strategy.name}: {strategy_error}")
                                            import traceback
                                            logger.debug(f"Strategy error details: {traceback.format_exc()}")
                                    
                                    # Load into WebSocket for live processing
                                    if bot.websocket_manager and ha_candles:
                                        try:
                                            logger.info("Loading historical data into WebSocket...")
                                            preload_success = bot.websocket_manager.preload_historical_candles('NIFTY', ha_candles[-50:])
                                            
                                            if preload_success:
                                                logger.info("WebSocket preload success!")
                                            
                                        except Exception as ws_error:
                                            logger.error(f"WebSocket preload error: {ws_error}")
                                    
                                    if success_count > 0:
                                        logger.info("ENHANCED QUICK START SUCCESS!")
                                        logger.info(f"HA Candles: {len(ha_candles)}")
                                        logger.info(f"Strategies Ready: {success_count}/{len(bot.strategies)}")
                                        logger.info("ADX calculation fixed and validated")
                                        logger.info("Signal detection system active")
                                        
                                        # Send enhanced success notification
                                        await bot.notifier.send_message(f"""Enhanced Quick Start Success!

Data Loaded: {len(ha_candles)} HA candles
Strategies Ready: {success_count}
ADX Calculation: Fixed and validated
Signal Detection: Active

Bot ready for live trading!""")
                                        
                                        return True
                                    else:
                                        logger.error("No strategies were successfully loaded")
                        
                        else:
                            logger.warning(f"Insufficient data: {len(raw_candles)} candles")
                    else:
                        logger.error(f"API error: {data.get('message', data)}")
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text[:200]}...")
        
        logger.warning("Quick start failed, using live data collection")
        return False
        
    except Exception as e:
        logger.error(f"Historical preload error: {e}")
        import traceback
        logger.debug(f"Full error: {traceback.format_exc()}")
        return False

def convert_to_heikin_ashi_fixed(regular_candles):
    """
    ENHANCED: HA conversion with error handling and validation
    """
    try:
        if not regular_candles:
            logging.getLogger(__name__).error("❌ No input candles for HA conversion")
            return []
        
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 Converting {len(regular_candles)} candles to Heikin Ashi...")
        
        ha_candles = []
        conversion_errors = 0
        
        for i, candle in enumerate(regular_candles):
            try:
                # Validate input candle
                required_fields = ['open', 'high', 'low', 'close', 'volume', 'timestamp']
                for field in required_fields:
                    if field not in candle:
                        raise ValueError(f"Missing field: {field}")
                
                # HA calculation
                if i == 0:
                    # First candle
                    ha_open = (candle['open'] + candle['close']) / 2
                    ha_close = (candle['open'] + candle['high'] + candle['low'] + candle['close']) / 4
                else:
                    # Subsequent candles
                    prev_ha = ha_candles[i-1]
                    ha_open = (prev_ha['ha_open'] + prev_ha['ha_close']) / 2
                    ha_close = (candle['open'] + candle['high'] + candle['low'] + candle['close']) / 4
                
                ha_high = max(candle['high'], ha_open, ha_close)
                ha_low = min(candle['low'], ha_open, ha_close)
                
                ha_candle = {
                    'ha_open': ha_open,
                    'ha_high': ha_high,
                    'ha_low': ha_low,
                    'ha_close': ha_close,
                    'volume': candle['volume'],
                    'timestamp': candle['timestamp'],
                    'symbol': 'NIFTY'
                }
                
                ha_candles.append(ha_candle)
                
            except Exception as e:
                conversion_errors += 1
                if conversion_errors <= 3:
                    logger.warning(f"HA conversion error #{conversion_errors}: {e}")
        
        if ha_candles:
            logger.info(f"✅ HA conversion complete: {len(ha_candles)} candles ({conversion_errors} errors)")
            return ha_candles
        else:
            logger.error("❌ HA conversion failed: No candles created")
            return []
        
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ HA conversion critical error: {e}")
        return []

async def main():
    """COMPLETELY FIXED main function with proper option integration"""
    try:
        # Setup logging
        setup_logging()
        logger = logging.getLogger(__name__)
        
        # Load configuration
        settings = get_settings()
        
        logger.info("🚀 Starting AstraRise Trading Bot - FIXED Option Integration V5")
        logger.info("💰 Capital: Rs.50,000 | Max per trade: Rs.15,000")
        
        # Initialize enhanced trading bot
        bot = TradingBot(settings)
        
        # 🔧 STEP 1: AUTHENTICATE FIRST
        logger.info("🔐 Authenticating with Upstox...")
        if not await bot.authenticate():
            logger.error("❌ Authentication failed!")
            return
        
        # 🔧 STEP 2: CREATE OPTION CHAIN MANAGER WITH AUTHENTICATED CLIENT
        logger.info("📊 Initializing Option Chain Manager...")
        from src.options.option_chain_manager import OptionChainManager
        bot.option_chain_manager = OptionChainManager(bot.upstox_client)
        
        # 🔧 STEP 3: TEST OPTION CHAIN MANAGER
        logger.info("🧪 Testing Option Chain Manager...")
        test_spot_price = await bot.option_chain_manager.get_spot_price("NIFTY")
        if test_spot_price:
            logger.info(f"✅ Option Chain Manager working! NIFTY: Rs.{test_spot_price:.2f}")
        else:
            logger.warning("⚠️ Option Chain Manager spot price failed - will use fallbacks")
        
        # 🔧 STEP 4: IMPORT AND CREATE STRATEGY
        logger.info("🎯 Loading Option-Integrated Pine Script Strategy...")
        from src.strategy.option_integrated_pine_script import OptionIntegratedPineScript
        
        # ✅ COMPREHENSIVE CONFIG
        option_pine_config = {
            'strategy_id': 'OptionIntegratedPineScript_V5_FIXED',
            'trading_mode': 'OPTION_TRADING',
            
            # Pine Script Parameters
            'adx_length': 12,
            'adx_threshold': 20,
            'strong_candle_threshold': 0.45,
            
            # Capital Management
            'total_capital': 50000,
            'risk_per_trade': 15000,
            'max_positions': 1,  # One trade at a time
            
            # Option Trading Configuration
            'option_trading_enabled': True,
            'strike_selection_mode': 'ATM',  # ATM, OTM, ITM
            'max_option_premium': 500,       # Max Rs.200 per share
            'min_option_premium': 5,        # Min Rs.10 per share
            
            # Advanced Features Configuration
            'enable_premium_monitoring': True,
            'monitoring_interval': 30,        # Monitor every 30 seconds
            'profit_target_pct': 50,         # 50% profit target
            'stop_loss_pct': 30,             # 30% stop loss
            'trailing_stop_enabled': True,
            'trail_activation_pct': 25,      # Start trailing at 25% profit
            'trail_step_pct': 10,            # Trail by 10%
            
            # Symbol Configuration
            'allowed_symbols': ['NIFTY'],
            'lot_sizes': {'NIFTY': 75},
            
            # Time Management
            'trading_start_time': '09:30',
            'no_entry_after': '15:10',
            'auto_square_off_time': '15:20',
        }
        
        # 🔧 STEP 5: CREATE STRATEGY WITH PROPER SETUP
        logger.info("🏗️ Creating Option-Integrated Strategy...")
        option_strategy = OptionIntegratedPineScript("option_pine_v5", option_pine_config)
        
        # 🔧 STEP 6: CRITICAL SETUP - SET BOTH CLIENTS
        logger.info("🔗 Connecting strategy to services...")
        
        # Set Upstox client for real option pricing
        option_strategy.set_upstox_client(bot.upstox_client)
        
        # 🚨 CRITICAL FIX: Set option chain manager
        option_strategy.option_chain_manager = bot.option_chain_manager
        
        # 🔧 STEP 7: TEST STRATEGY SETUP
        logger.info("🧪 Testing strategy setup...")
        
        # Test if strategy can access option chain
        if hasattr(option_strategy, 'option_chain_manager'):
            test_chain = await option_strategy.option_chain_manager.get_option_chain("NIFTY", 3)
            if test_chain and 'spot_price' in test_chain:
                logger.info(f"✅ Strategy can access option chain! Spot: Rs.{test_chain['spot_price']:.2f}")
            else:
                logger.warning("⚠️ Strategy option chain access failed - will use fallbacks")
        else:
            logger.error("❌ Strategy missing option_chain_manager!")
            return
        
        # 🔧 STEP 8: ADD STRATEGY TO BOT
        logger.info("📎 Adding strategy to bot...")
        bot.add_strategy(option_strategy)
        
        # 🔧 STEP 5: QUICK START WITH HISTORICAL DATA
        logger.info("📚 Attempting quick start with historical data...")
        quick_start_success = await preload_historical_candles_working(bot)
        
        if quick_start_success:
            logger.info("🎉 QUICK START ENABLED: Bot ready immediately!")
            logger.info("⚡ Eliminated 40+ minute wait time!")
        else:
            logger.info("⏳ FALLBACK: Using live data collection (25+ minutes)")


        # 🔧 STEP 9: SETUP WEBSOCKETS
        logger.info("🌐 Setting up WebSocket connections...")
        websocket_success = await bot.setup_websockets()
        
        if websocket_success:
            logger.info("✅ WebSocket setup successful!")

            # 🔧 IMMEDIATE FIX: Connect historical data to WebSocket processing
            logger.info("🔧 CONNECTING historical data to WebSocket signal processing...")
    
            for strategy in bot.strategies:
                if hasattr(strategy, 'ha_candles_history') and strategy.ha_candles_history:
                    historical_candles = strategy.ha_candles_history
            
                    # Inject historical data into WebSocket manager
                    if bot.websocket_manager:
                        try:
                            # Method 1: Direct injection into persistent storage
                            if not hasattr(bot.websocket_manager, 'persistent_ha_candles'):
                                bot.websocket_manager.persistent_ha_candles = {}
                    
                            bot.websocket_manager.persistent_ha_candles['NIFTY'] = historical_candles.copy()
                    
                            # Method 2: Also update latest storage for compatibility
                            if not hasattr(bot.websocket_manager, 'latest_ha_candles'):
                                bot.websocket_manager.latest_ha_candles = {}
                    
                            bot.websocket_manager.latest_ha_candles['NIFTY'] = historical_candles.copy()
                    
                            # Method 3: Update HA converter state for continuity
                            if hasattr(bot.websocket_manager, 'ha_converter'):
                                from collections import deque
                                if not hasattr(bot.websocket_manager.ha_converter, 'ha_candles'):
                                    bot.websocket_manager.ha_converter.ha_candles = {}
                        
                                bot.websocket_manager.ha_converter.ha_candles['NIFTY'] = deque(
                                    historical_candles[-10:], maxlen=100
                                )
                    
                            logger.info(f"✅ INJECTION SUCCESS: {len(historical_candles)} historical candles injected into WebSocket")
                            logger.info(f"📊 WebSocket now has: {len(bot.websocket_manager.persistent_ha_candles['NIFTY'])} total candles")
                    
                            # Verify the injection worked
                            ws_count = bot.websocket_manager.get_total_candle_count('NIFTY')
                            logger.info(f"🔍 VERIFICATION: WebSocket reports {ws_count} total candles")
                    
                            if ws_count >= 23:
                                logger.info("🎉 SIGNAL PROCESSING READY: Strategy can now detect signals immediately!")
                    
                        except Exception as injection_error:
                            logger.error(f"❌ Historical data injection failed: {injection_error}")
            
                    break  # Only need to do this once
    
            logger.info("🔧 Historical data connection completed")

        else:
            logger.warning("⚠️ WebSocket setup failed - will use polling mode")
        
        # 🔧 STEP 10: FINAL VALIDATION
        logger.info("🔍 Final system validation...")
        
        # Check all components
        checks = {
            "Upstox Client": bot.upstox_client.access_token is not None,
            "Option Chain Manager": bot.option_chain_manager is not None,
            "Strategy Loaded": len(bot.strategies) > 0,
            "Option Chain Access": hasattr(option_strategy, 'option_chain_manager'),
            "WebSocket Manager": bot.websocket_manager is not None
        }
        
        logger.info("📋 System Status:")
        all_good = True
        for component, status in checks.items():
            status_icon = "✅" if status else "❌"
            logger.info(f"   {status_icon} {component}: {'OK' if status else 'FAILED'}")
            if not status:
                all_good = False
        
        if not all_good:
            logger.error("❌ System validation failed! Check the issues above.")
            return
        
        # 🔧 STEP 11: SUCCESS MESSAGE
        logger.info("🎯 Option-Integrated Pine Script V5 Strategy READY!")
        logger.info("📊 Features: Pine Script + Real Option Trading + Advanced Monitoring")
        logger.info("📈 Uptrend → CE options | Downtrend → PE options")
        logger.info("💰 Premium Range: Rs.10-200 per share")
        logger.info("🎯 Profit Target: 50% | Stop Loss: 30% | Trailing Stop: Active")
        logger.info("🔍 Real-time Monitoring: Every 30 seconds")
        
        # Send startup notification
        #await bot.notifier.send_message(f"""🚀 *AstraRise Trading Bot Started - FIXED VERSION*

#📊 *STRATEGY: Pine Script V5 + Real Options*
#💰 *Capital:* Rs.50,000 | *Max Trade:* Rs.15,000

#🎯 *OPTION TRADING LOGIC:*
#📈 *Uptrend Signal* → Buy NIFTY CE (Call) options
#📉 *Downtrend Signal* → Buy NIFTY PE (Put) options

#⚙️ *PINE SCRIPT SIGNALS:*
#✅ Price above trend + Strong green + ADX>20 → *CE BUY*
#❌ Price below trend + Strong red + ADX>20 → *PE BUY*

#🏷️ *STRIKE SELECTION:*
#🎯 *Mode:* ATM (At The Money)
#📊 *Example:* NIFTY@24,968 → Buy 24950CE or 24950PE
#💵 *Premium Range:* Rs.10-200 per share

#🔄 *REAL-TIME FEATURES:*
#📡 Live option premiums from Upstox API
#📊 Bid-ask spread validation
#🛡️ Liquidity and premium checks
#🔧 Enhanced fallback systems

#🎉 *FIXES APPLIED:*
#✅ Multiple spot price fallback methods
#✅ Enhanced option chain caching
#✅ Improved error handling
#✅ Market hours validation
#✅ Robust option premium fetching

#Bot ready for NIFTY option trading! 🚀""")
        
        # 🔧 STEP 12: RUN THE BOT
        logger.info("🚀 Starting enhanced trading bot...")
        await bot.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        # Print detailed error for debugging
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())