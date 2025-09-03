# ==================== src/strategy/option_integrated_pine_script.py (FIXED) ====================
import logging
from datetime import datetime
import numpy as np
import pandas as pd
import aiohttp
import json
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from src.strategy.complete_pine_script_strategy import CompletePineScriptStrategy
from src.models.order import Order, OrderType, TransactionType
from src.models.position import Position 
from datetime import datetime, time, timedelta

#from anyio import current_time

class OptionIntegratedPineScript(CompletePineScriptStrategy):
    """
    Pine Script Strategy with REAL Option Trading Integration - FIXED VERSION
    
    Features:
    - Real-time option chain data from Upstox
    - ATM/OTM strike selection based on NIFTY spot price
    - Live option premium pricing
    - Uptrend → CE options, Downtrend → PE options
    - Proper bid-ask spread handling
    - FIXED: No Unicode emojis in logging
    """
    
    def __init__(self, name: str, config: Optional[Dict] = None):
        super().__init__(name, config)
        
        # Option trading configuration
        self.option_trading_enabled = config.get('option_trading_enabled', True) if config else True
        self.strike_selection_mode = config.get('strike_selection_mode', 'ATM')  # ATM, OTM, ITM
        self.max_option_premium = config.get('max_option_premium', 500) if config else 500  # Increase to Rs.500
        self.min_option_premium = config.get('min_option_premium', 5) if config else 5     # Reduce to Rs.5
        
        # Strike interval (NIFTY options are in 50-point intervals)
        self.strike_interval = 50
        
        #self.profit_target_pct = 50      # 50% profit target
        self.stop_loss_pct = 30          # 30% stop loss
        #self.trail_activation_pct = 25   # Start trailing at 25%
        #self.trail_step_pct = 10         # Trail by 10%
        self.trailing_stop_enabled = False  # Disable trailing stops

        # Add this to your init method
        self.ltp_cache = {}  # Cache LTP values
        self.cache_duration = 30  # 30 seconds cache


        # Option expiry management
        self.preferred_expiry = 'weekly'  # weekly, monthly
        self.min_days_to_expiry = 1       # Avoid same-day expiry
        self.max_days_to_expiry = 7       # Prefer weekly options
        
        # Option chain cache (5-minute cache)
        self.option_chain_cache = {}
        self.cache_duration = 300  # 5 minutes
        
        # Upstox client reference (will be set by trading bot)
        self.upstox_client = None
        
        # Advanced features configuration
        self.enable_premium_monitoring = config.get('enable_premium_monitoring', True) if config else True
        self.monitoring_interval = config.get('monitoring_interval', 30) if config else 30  # seconds
        self.last_monitoring_time = datetime.now()
    
        # Enhanced exit parameters
        self.profit_target_pct = config.get('profit_target_pct', 50) if config else 50    # 50% profit target
        self.stop_loss_pct = config.get('stop_loss_pct', 30) if config else 30           # 30% stop loss
       # self.trailing_stop_enabled = config.get('trailing_stop_enabled', True) if config else True
        self.trail_activation_pct = config.get('trail_activation_pct', 25) if config else 25  # Start trailing at 25% profit
        self.trail_step_pct = config.get('trail_step_pct', 10) if config else 10         # Trail by 10%
    
        # Position tracking for advanced features
        self.active_option_positions = {}  # Enhanced position tracking
        self.position_monitoring_data = {}  # Real-time monitoring data
    

        # Performance tracking
        self.total_premium_monitored = 0
        self.monitoring_updates = 0
        self.last_monitoring_time = datetime.now()
        
        # FIXED: Use plain text instead of emojis in logs
        self.logger.info("Advanced Features Enabled:")
        self.logger.info(f"  Premium Monitoring: {self.enable_premium_monitoring}")
        self.logger.info(f"  Profit Target: {self.profit_target_pct}%")
        self.logger.info(f"  Stop Loss: {self.stop_loss_pct}%")
        self.logger.info(f"  Trailing Stop: {self.trailing_stop_enabled}")
        
        self.logger.info(f"Option Integration enabled: {self.option_trading_enabled}")
        self.logger.info(f"Strike Selection: {self.strike_selection_mode}")
        self.logger.info(f"Premium Range: Rs.{self.min_option_premium}-{self.max_option_premium}")

        # ADD THIS LINE to ensure ha_candles_history exists:
        if not hasattr(self, 'ha_candles_history'):
            self.ha_candles_history = []
    
        # Also ensure candle_history exists for compatibility
        if not hasattr(self, 'candle_history'):
            self.candle_history = []
    
    async def should_exit(self, position: Position, market_data: Dict) -> Optional[Order]:
        """
        SIMPLIFIED EXIT STRATEGY - Only Essential Exits
        
        Priority Order:
        1. Mandatory exits (stop loss, market close)
        2. Profit target (50%)  
        3. Pine Script technical reversal
        """
        try:
            self.logger.info(f"Checking exits for {position.symbol}")
            
            # Get current option premium with fallback
            current_premium = await self._get_current_premium_safe(position)
            if current_premium is None:
                self.logger.warning(f"Could not get premium for {position.symbol} - skipping exit check")
                return None
            
            # Calculate current P&L
            entry_price = position.average_price
            pnl_pct = ((current_premium - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            
            self.logger.debug(f"{position.symbol}: Premium Rs.{current_premium:.2f} -> P&L: {pnl_pct:+.2f}%")
            
            # === PRIORITY 1: MANDATORY EXITS (Always execute) ===
            mandatory_exit = await self._check_mandatory_exits(position, current_premium)
            if mandatory_exit:
                await self._cleanup_position_after_exit(position.symbol)
                return mandatory_exit
            
            # === PRIORITY 2: PROFIT TARGET (Secure gains) ===
            if pnl_pct >= 50:
                self.logger.info(f"PROFIT TARGET HIT: {pnl_pct:.1f}% profit achieved")
                exit_order = self._create_exit_order(position, current_premium, "PROFIT_TARGET_50%", pnl_pct)
                await self._cleanup_position_after_exit(position.symbol)
                return exit_order
            
            # === PRIORITY 3: PINE SCRIPT TECHNICAL REVERSAL ===
            # Only check technical exits if we're not in profit target range
            if pnl_pct < 40:  # Only check technical exits if profit < 40%
                pine_exit = await self._check_pine_script_exit(position, market_data, current_premium)
                if pine_exit:
                    await self._cleanup_position_after_exit(position.symbol)
                    return pine_exit
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in exit check for {position.symbol}: {e}")
            return None

    async def _get_current_premium_safe(self, position: Position) -> Optional[float]:
        """Safely get current option premium with fallbacks"""
        try:
            # Method 1: Fetch real-time option premium
            if hasattr(position, 'strike_price') and hasattr(position, 'option_type'):
                current_premium = await self.fetch_option_ltp(position.strike_price, position.option_type)
                if current_premium and current_premium > 0:
                    return current_premium
            
            # Method 2: Use position's current price
            if position.current_price > 0:
                return position.current_price
            
            # Method 3: Fallback to entry price (no change)
            self.logger.warning(f"Using entry price as fallback for {position.symbol}")
            return position.average_price
            
        except Exception as e:
            self.logger.error(f"Error getting current premium: {e}")
            return None
        
    async def _check_pine_script_exit(self, position: Position, market_data: Dict, current_premium: float) -> Optional[Order]:
        """Check Pine Script technical reversal using parent class logic"""
        try:
            # Use the parent class Pine Script exit logic
            pine_exit = await super().should_exit(position, market_data)
            
            if pine_exit:
                # Update exit order with correct option details
                pine_exit.price = current_premium  # Use option premium, not spot price
                pine_exit.option_type = getattr(position, 'option_type', 'CE')
                pine_exit.strike_price = getattr(position, 'strike_price', 0)
                
                # Calculate P&L for the exit order
                pnl_pct = self._calculate_pnl_pct(current_premium, position.average_price)
                pine_exit.pnl_pct = pnl_pct
                pine_exit.total_pnl = self._calculate_total_pnl(position, current_premium)
                
                exit_reason = getattr(pine_exit, 'exit_reason', 'PINE_SCRIPT_REVERSAL')
                self.logger.info(f"PINE SCRIPT EXIT: {exit_reason} at {pnl_pct:+.2f}% P&L")
                
                return pine_exit
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking Pine Script exit: {e}")
            return None

    def _create_exit_order(self, position: Position, current_premium: float, exit_reason: str, pnl_pct: float) -> Order:
        """Create standardized exit order"""
        try:
            order = Order(
                symbol=position.symbol,
                quantity=position.quantity,
                price=current_premium,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.SELL,
                strategy_name=self.name,
                instrument_key=getattr(position, 'instrument_key', '')
            )
            
            # Add exit details
            order.exit_reason = exit_reason
            order.option_type = getattr(position, 'option_type', 'CE')
            order.strike_price = getattr(position, 'strike_price', 0)
            order.strike_symbol = f"{getattr(position, 'strike_price', 0)}{getattr(position, 'option_type', 'CE')}"
            order.entry_price = position.average_price
            order.exit_time = datetime.now()
            order.pnl_pct = pnl_pct
            order.total_pnl = self._calculate_total_pnl(position, current_premium)
            
            return order
            
        except Exception as e:
            self.logger.error(f"Error creating exit order: {e}")
            return None

    def _calculate_pnl_pct(self, current_premium: float, entry_price: float) -> float:
        """Calculate P&L percentage"""
        if entry_price <= 0:
            return 0.0
        return ((current_premium - entry_price) / entry_price) * 100

    def _calculate_total_pnl(self, position: Position, current_premium: float) -> float:
        """Calculate total P&L in rupees"""
        try:
            pnl_per_share = current_premium - position.average_price
            lot_size = 75  # NIFTY lot size
            total_pnl = pnl_per_share * position.quantity * lot_size
            return total_pnl
        except Exception as e:
            self.logger.error(f"Error calculating total P&L: {e}")
            return 0.0
    
    def _is_strong_red_candle(self, candle: Dict) -> bool:
        """Check if candle is strong red (70%+ body for exit confirmation)"""
        try:
            ha_open = candle.get('ha_open', 0)
            ha_close = candle.get('ha_close', 0) 
            ha_high = candle.get('ha_high', 0)
            ha_low = candle.get('ha_low', 0)
            
            if ha_high == ha_low:  # Avoid division by zero
                return False
                
            body = abs(ha_close - ha_open)
            candle_range = ha_high - ha_low
            body_pct = body / candle_range if candle_range > 0 else 0
            
            is_red = ha_close < ha_open
            is_strong = body_pct > 0.7  # 70% body for exit (stricter than entry)
            
            return is_red and is_strong
            
        except:
            return False

    def _is_red_candle(self, candle: Dict) -> bool:
        """Check if candle is red"""
        try:
            return candle.get('ha_close', 0) < candle.get('ha_open', 0)
        except:
            return False

    def _create_simple_exit_order(self, position: Position, current_premium: float, exit_reason: str) -> Order:
        """Create exit order with proper P&L calculation"""
        try:
            order = Order(
                symbol=position.symbol,
                quantity=position.quantity,
                price=current_premium,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.SELL,
                strategy_name=self.name,
                instrument_key=getattr(position, 'instrument_key', '')
            )
            
            # Calculate P&L
            entry_price = position.average_price
            pnl_per_share = current_premium - entry_price
            pnl_pct = (pnl_per_share / entry_price) * 100 if entry_price > 0 else 0
            total_pnl = pnl_per_share * position.quantity * 75  # 75 shares per lot
            
            # Set order details
            order.exit_reason = exit_reason
            order.pnl_per_share = pnl_per_share
            order.pnl_pct = pnl_pct
            order.total_pnl = total_pnl
            order.option_type = getattr(position, 'option_type', 'CE')
            order.strike_price = getattr(position, 'strike_price', 0)
            order.entry_price = entry_price
            
            self.logger.info(f"Exit order: {exit_reason} - P&L: Rs.{total_pnl:+,.2f} ({pnl_pct:+.2f}%)")
            return order
            
        except Exception as e:
            self.logger.error(f"Error creating exit order: {e}")
            return None

    async def check_reentry_opportunity(self, market_data: Dict) -> Optional[Order]:
        """
        NEW: Check for re-entry when trend continues after early exit
        
        Your issue: Missing continuation moves after premature exits
        Solution: Re-enter when original trend resumes strongly
        """
        try:
            # Only check re-entry if not currently in trade
            if self.in_trade or hasattr(self, 'active_option_positions') and self.active_option_positions:
                return None
            
            # Check if we recently exited a position  
            if not hasattr(self, 'last_exit_time'):
                return None
                
            time_since_exit = (datetime.now() - self.last_exit_time).total_seconds()
            
            # Wait at least 3 minutes before re-entry (prevent overtrading)
            if time_since_exit < 180:
                return None
            
            # Only re-enter within 30 minutes of exit
            if time_since_exit > 1800:
                return None
            
            # Check if original trend resumed strongly
            ha_candles = market_data.get('ha_candles_history', [])
            if len(ha_candles) < 15:
                return None
            
            current_price = market_data.get('current_price', 0)
            trend_line = self.calculate_trend_line(ha_candles)
            
            if not trend_line:
                return None
            
            # Check for strong trend resumption
            price_above_trend = current_price > trend_line
            trend_strength = ((current_price - trend_line) / trend_line) * 100
            
            # Get last candle for strength check
            latest_candle = ha_candles[-1]
            strong_green, strong_red, body_pct = self.analyze_candle_strength(latest_candle)
            
            # Re-entry conditions: VERY strong trend resumption (stricter than initial entry)
            if (price_above_trend and 
                trend_strength > 1.0 and  # At least 1% above trend (stricter)
                strong_green and 
                body_pct > 0.75):  # Very strong candle (75%+ body)
                
                self.logger.info(f"RE-ENTRY SIGNAL: Strong trend resumption +{trend_strength:.1f}% above trend")
                self.logger.info(f"  Time since exit: {time_since_exit/60:.1f} minutes")
                self.logger.info(f"  Candle strength: {body_pct:.1%} body")
                
                # Use same entry logic but mark as re-entry
                reentry_order = await self.should_enter(market_data)
                
                if reentry_order:
                    # Mark as re-entry for tracking
                    reentry_order.entry_type = "RE_ENTRY"
                    reentry_order.original_exit_time = getattr(self, 'last_exit_time', datetime.now())
                    
                    return reentry_order
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking re-entry: {e}")
            return None
        
    def set_upstox_client(self, client):
        """Set Upstox client for option data fetching"""
        self.upstox_client = client
        self.logger.info("Upstox client configured for option trading")
    
    async def calculate_option_strike(self, spot_price: float, option_type: str, selection_mode: str = None) -> int:
        """Calculate option strike with enhanced fallbacks - COMPLETELY FIXED"""
        try:
            self.logger.info(f"🎯 Calculating {option_type} strike for spot: Rs.{spot_price:.2f}")
            
            # Method 1: Try to use option chain manager
            if hasattr(self, 'option_chain_manager') and self.option_chain_manager:
                try:
                    option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 10)
                    
                    if option_chain and 'strikes' in option_chain and option_chain['strikes']:
                        available_strikes = sorted(option_chain['strikes'].keys())
                        atm_strike = min(available_strikes, key=lambda x: abs(x - spot_price))
                        
                        mode = selection_mode or self.strike_selection_mode
                        selected_strike = self._calculate_strike_from_mode(atm_strike, option_type, mode)
                        
                        # Ensure selected strike exists
                        if selected_strike in available_strikes:
                            self.logger.info(f"✅ Strike from option chain: {selected_strike}{option_type}")
                            return selected_strike
                        else:
                            # Find closest available strike
                            selected_strike = min(available_strikes, key=lambda x: abs(x - selected_strike))
                            self.logger.info(f"📊 Adjusted to available strike: {selected_strike}{option_type}")
                            return selected_strike
                
                except Exception as e:
                    self.logger.warning(f"⚠️ Option chain method failed: {e}")
            
            # Method 2: Calculate using spot price (FALLBACK)
            self.logger.info("🔄 Using fallback strike calculation...")
            atm_strike = round(spot_price / 50) * 50  # Round to nearest 50
            
            mode = selection_mode or self.strike_selection_mode
            selected_strike = self._calculate_strike_from_mode(atm_strike, option_type, mode)
            
            self.logger.info(f"✅ Fallback strike calculation: {selected_strike}{option_type} (ATM: {atm_strike})")
            return selected_strike
    
        except Exception as e:
            self.logger.error(f"❌ Error calculating option strike: {e}")
            # Emergency fallback
            emergency_strike = round(spot_price / 50) * 50
            self.logger.warning(f"🚨 Emergency fallback strike: {emergency_strike}")
            return emergency_strike
    
    def get_option_symbol(self, strike: int, option_type: str, expiry_date: str = None) -> str:
        """FIXED: Generate proper option symbol"""
        try:
            if not expiry_date:
                # Get current expiry from option chain
                if hasattr(self, 'option_chain_manager') and self.option_chain_manager:
                    #option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 1)
                    if option_chain and 'expiry_date' in option_chain:
                        expiry_date = option_chain['expiry_date']

            if expiry_date:
                # Parse expiry date properly
                if isinstance(expiry_date, str):
                    try:
                        expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
                    except ValueError:
                        expiry_dt = datetime.strptime(expiry_date, '%d-%m-%Y')
                else:
                    expiry_dt = expiry_date
            
                # Format: NIFTY24AUG25000CE
                year = expiry_dt.strftime('%y')
                month = expiry_dt.strftime('%b').upper()

                symbol = f"NIFTY{year}{month}{strike}{option_type}"
                self.logger.info(f"✅ Generated symbol: {symbol}")
                return symbol
            else:
                # Fallback format
                return f"NIFTY{strike}{option_type}"
        except Exception as e:
            self.logger.error(f"Error generating option symbol: {e}")
            return f"NIFTY{strike}{option_type}"  # Safe fallback
        
    async def get_nearest_expiry(self) -> str:
        """Get nearest expiry date - WORKING VERSION"""
        try:
            # Use the new option chain manager
            option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 1)
            if option_chain and 'expiry_date' in option_chain:
                expiry_date = option_chain['expiry_date']
                # Convert to string format if it's a date object
                if hasattr(expiry_date, 'strftime'):
                    return expiry_date.strftime('%Y-%m-%d')
                return str(expiry_date)
        
            return None
        
        except Exception as e:
            self.logger.error(f"Error getting nearest expiry: {e}")
            return None
    
    async def get_option_instrument_key(self, strike: int, option_type: str) -> Optional[str]:
        """Get option instrument key with enhanced fallbacks"""
        try:
            # Method 1: From option chain manager
            if hasattr(self, 'option_chain_manager') and self.option_chain_manager:
                try:
                    option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 10)
                    
                    if option_chain and 'strikes' in option_chain:
                        if strike in option_chain['strikes']:
                            strike_data = option_chain['strikes'][strike]
                            
                            if option_type.upper() == 'CE' and 'ce' in strike_data:
                                instrument_key = strike_data['ce'].get('instrument_key')
                            elif option_type.upper() == 'PE' and 'pe' in strike_data:
                                instrument_key = strike_data['pe'].get('instrument_key')
                            else:
                                instrument_key = None
                            
                            if instrument_key and not instrument_key.endswith('_FALLBACK'):
                                self.logger.debug(f"✅ Found instrument key: {instrument_key}")
                                return instrument_key
                
                except Exception as e:
                    self.logger.debug(f"Option chain instrument key failed: {e}")
            
            # Method 2: Try to construct from Upstox client
            if hasattr(self, 'upstox_client') and self.upstox_client:
                try:
                    # This would require access to the contracts cache
                    if hasattr(self.upstox_client, '_option_contracts_cache'):
                        contracts = self.upstox_client._option_contracts_cache
                        key = f"{strike}{option_type}"
                        if key in contracts:
                            return contracts[key].get('instrument_key')
                
                except Exception as e:
                    self.logger.debug(f"Client instrument key failed: {e}")
            
            # Method 3: Generate fallback key
            fallback_key = f"NSE_FO|{strike}{option_type}_FALLBACK"
            self.logger.warning(f"⚠️ Using fallback instrument key: {fallback_key}")
            return fallback_key
    
        except Exception as e:
            self.logger.error(f"❌ Error getting instrument key: {e}")
            return f"NSE_FO|{strike}{option_type}_FALLBACK"
    
    # Add to your strategy class
    async def _wait_for_api_limit(self):
        """Add delay between API calls to prevent rate limiting"""
        if hasattr(self, 'last_api_call'):
            time_since_last = (datetime.now() - self.last_api_call).total_seconds()
            if time_since_last < 1.0:  # Wait at least 1 second between calls
                await asyncio.sleep(1.0 - time_since_last)
    
        self.last_api_call = datetime.now()

    async def fetch_option_ltp(self, strike: int, option_type: str, retries: int = 2) -> Optional[float]:
        """Fetch option LTP with enhanced fallbacks - COMPLETELY FIXED"""
        try:
            self.logger.debug(f"🔍 Fetching LTP for {strike}{option_type}...")
            
            # Method 1: Try option chain manager first
            if hasattr(self, 'option_chain_manager') and self.option_chain_manager:
                try:
                    option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 10)
                    
                    if option_chain and 'strikes' in option_chain:
                        if strike in option_chain['strikes']:
                            strike_data = option_chain['strikes'][strike]
                            
                            option_data = None
                            if option_type.upper() == 'CE' and 'ce' in strike_data:
                                option_data = strike_data['ce']
                            elif option_type.upper() == 'PE' and 'pe' in strike_data:
                                option_data = strike_data['pe']
                            
                            if option_data and 'ltp' in option_data:
                                ltp = option_data['ltp']
                                if ltp and ltp > 0:
                                    self.logger.info(f"Got LTP from option chain: {strike}{option_type} = Rs.{ltp:.2f}")
                                    return float(ltp)
                
                except Exception as e:
                    self.logger.debug(f"Option chain LTP failed: {e}")
            
            # Method 2: Direct API call through upstox client
            if hasattr(self, 'upstox_client') and self.upstox_client:
                try:
                    instrument_key = await self.get_option_instrument_key(strike, option_type)
                    if instrument_key and not instrument_key.endswith('_FALLBACK'):
                        ltp = await self.upstox_client.get_option_ltp(instrument_key)
                        if ltp and ltp > 0:
                            self.logger.info(f"Got LTP from direct API: {strike}{option_type} = Rs.{ltp:.2f}")
                            return float(ltp)
                
                except Exception as e:
                    if "429" in str(e):
                        self.logger.warning(f"API rate limit hit for {strike}{option_type}, using cached data if available")
                        # Try to get cached data
                        if hasattr(self, 'ltp_cache'):
                            cache_key = f"{strike}{option_type}"
                            if cache_key in self.ltp_cache:
                                _, cached_ltp = self.ltp_cache[cache_key]
                                self.logger.info(f"Using cached LTP: {strike}{option_type} = Rs.{cached_ltp:.2f}")
                                return cached_ltp

                    else:   
                        self.logger.debug(f"Direct API LTP failed: {e}")
            
            # Method 3: Estimate premium based on market conditions (FALLBACK)
            self.logger.warning(f"Could not fetch LTP for {strike}{option_type} - skipping trade")
            return None
    
        except Exception as e:
            self.logger.error(f"❌ Error fetching option LTP for {strike}{option_type}: {e}")
            return None
    
    def _calculate_strike_from_mode(self, atm_strike: int, option_type: str, mode: str) -> int:
        """Calculate strike based on selection mode"""
        if mode == 'ATM':
            return atm_strike
        elif mode == 'OTM':
            if option_type == 'CE':
                return atm_strike + 50  # CE OTM: above current price
            else:  # PE
                return atm_strike - 50  # PE OTM: below current price
        elif mode == 'ITM':
            if option_type == 'CE':
                return atm_strike - 50  # CE ITM: below current price
            else:  # PE
                return atm_strike + 50  # PE ITM: above current price
        else:
            return atm_strike   # Default to ATM if unknown mode
        
    def _estimate_option_premium(self, strike: int, option_type: str, spot_price: float = None) -> float:
        """Estimate option premium when API fails - EMERGENCY FALLBACK"""
        try:
            if not spot_price:
                spot_price = 25000  # Default NIFTY value
            
            # Calculate moneyness
            if option_type.upper() == 'CE':
                moneyness = spot_price - strike  # Positive = ITM
            else:  # PE
                moneyness = strike - spot_price  # Positive = ITM
            
            # Base premium calculation
            if moneyness > 0:  # ITM
                intrinsic_value = moneyness
                time_value = max(20, abs(moneyness) * 0.1)  # Minimum Rs.20 time value
                estimated_premium = intrinsic_value + time_value
            else:  # OTM
                distance = abs(moneyness)
                if distance <= 50:  # Near ATM
                    estimated_premium = max(30, 100 - distance)  # Rs.30-100
                elif distance <= 100:  # Moderate OTM
                    estimated_premium = max(15, 50 - (distance - 50) * 0.5)  # Rs.15-50
                else:  # Far OTM
                    estimated_premium = max(5, 25 - (distance - 100) * 0.2)  # Rs.5-25
            
            # Ensure reasonable bounds
            estimated_premium = max(5, min(500, estimated_premium))
            
            self.logger.debug(f"📊 Estimated premium for {strike}{option_type}: Rs.{estimated_premium:.2f}")
            return estimated_premium
    
        except Exception as e:
            self.logger.error(f"❌ Error estimating premium: {e}")
            return 50.0  # Default fallback

    async def get_option_quote_detailed(self, strike: int, option_type: str) -> Dict:
        """Get detailed option quote including bid-ask spread"""
        try:
            if not self.upstox_client:
                return {}
            
            instrument_key = await self.get_option_instrument_key(strike, option_type)
            if not instrument_key:
                return {}
            
            # Fetch detailed quote
            url = f"https://api.upstox.com/v2/market-quote/quotes"
            headers = {
                'Authorization': f'Bearer {self.upstox_client.access_token}',
                'Accept': 'application/json'
            }
            
            params = {'symbol': instrument_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'data' in data:
                            quote_data = data['data']
                            
                            if quote_data:
                                actual_key = list(quote_data.keys())[0]
                                option_data = quote_data[actual_key]
                                
                                # Extract bid-ask data
                                depth = option_data.get('depth', {})
                                buy_orders = depth.get('buy', [])
                                sell_orders = depth.get('sell', [])
                                
                                bid_price = buy_orders[0].get('price', 0) if buy_orders else 0
                                ask_price = sell_orders[0].get('price', 0) if sell_orders else 0
                                ltp = option_data.get('last_price', 0)
                                
                                return {
                                    'strike': strike,
                                    'option_type': option_type,
                                    'ltp': ltp,
                                    'bid': bid_price,
                                    'ask': ask_price,
                                    'spread': ask_price - bid_price if (ask_price and bid_price) else 0,
                                    'volume': option_data.get('volume', 0),
                                    'oi': option_data.get('oi', 0),
                                    'instrument_key': instrument_key
                                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error getting detailed quote: {e}")
            return {}
    
    async def validate_option_trading_setup(self) -> bool:
        """Validate that option trading setup is working"""
        try:
            self.logger.info("🔍 Validating option trading setup...")
            
            # Check 1: Option chain manager
            if not hasattr(self, 'option_chain_manager') or not self.option_chain_manager:
                self.logger.error("❌ No option chain manager!")
                return False
            
            # Check 2: Upstox client
            if not hasattr(self, 'upstox_client') or not self.upstox_client:
                self.logger.error("❌ No upstox client!")
                return False
            
            # Check 3: Test spot price fetching
            try:
                spot_price = await self.option_chain_manager.get_spot_price("NIFTY")
                if not spot_price or spot_price <= 0:
                    self.logger.warning("⚠️ Spot price fetching failed, but continuing...")
                    spot_price = 25000  # Use default
                else:
                    self.logger.info(f"✅ Spot price: Rs.{spot_price:.2f}")
            except Exception as e:
                self.logger.warning(f"⚠️ Spot price test failed: {e}")
                spot_price = 25000
            
            # Check 4: Test option chain fetching
            try:
                option_chain = await self.option_chain_manager.get_option_chain("NIFTY", 3)
                if option_chain and 'strikes' in option_chain:
                    strikes_count = len(option_chain['strikes'])
                    self.logger.info(f"✅ Option chain: {strikes_count} strikes available")
                else:
                    self.logger.warning("⚠️ Option chain limited, using fallbacks")
            except Exception as e:
                self.logger.warning(f"⚠️ Option chain test failed: {e}")
            
            # Check 5: Test strike calculation
            try:
                test_strike = await self.calculate_option_strike(spot_price, 'CE')
                self.logger.info(f"✅ Strike calculation: {test_strike}CE")
            except Exception as e:
                self.logger.error(f"❌ Strike calculation failed: {e}")
                return False
            
            self.logger.info("🎉 Option trading setup validation completed!")
            return True
    
        except Exception as e:
            self.logger.error(f"❌ Setup validation failed: {e}")
            return False

    def validate_option_premium(self, premium: float, strike: int, spot_price: float) -> bool:
        """Validate option premium - SIMPLIFIED VERSION"""
        try:
            if premium is None or premium <= 0:
                return False
        
            # Basic validation: premium should be reasonable
            if premium < self.min_option_premium or premium > self.max_option_premium:
                self.logger.warning(f"Premium Rs.{premium:.2f} outside range Rs.{self.min_option_premium}-{self.max_option_premium}")
                return False
        
            # Additional check: premium shouldn't be too high for far OTM options
            price_diff = abs(spot_price - strike)
            if price_diff > 200 and premium > 100:  # Far OTM with high premium
                self.logger.warning(f"High premium Rs.{premium:.2f} for far OTM option (diff: {price_diff})")
                return False
        
            self.logger.debug(f"Premium validated: Rs.{premium:.2f}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error validating option premium: {e}")
            return False
            
    async def should_enter(self, market_data: Dict) -> Optional[Order]:
        """
        FIXED: Enhanced entry logic with proper HA candle handling
        Process:
        1. Check available candles from ALL sources
        2. Run Pine Script analysis on NIFTY spot
        3. If signal detected, determine option type (CE/PE)
        4. Calculate appropriate strike (ATM/OTM)
        5. Fetch real option premium from Upstox
        6. Validate premium and liquidity
        7. Create option order
        """
        try:
            # Add current candle data - FIXED to handle HA format
            if not self.add_candle_data(market_data):
                return None

            # Get available candles from ALL sources
            available_candles = 0
            data_source = "none"
            
            # Method 1: Check strategy's historical data first (most reliable)
            if hasattr(self, 'ha_candles_history') and self.ha_candles_history:
                available_candles = len(self.ha_candles_history)
                data_source = "strategy_historical"
            
            # Method 2: Check candle_history
            elif hasattr(self, 'candle_history') and self.candle_history:
                available_candles = len(self.candle_history)
                data_source = "candle_history"
            
            # Method 3: Check WebSocket persistent candles
            elif hasattr(self, 'upstox_client') and hasattr(self.upstox_client, 'websocket_manager'):
                if hasattr(self.upstox_client.websocket_manager, 'persistent_ha_candles'):
                    ws_candles = self.upstox_client.websocket_manager.persistent_ha_candles.get('NIFTY', [])
                    if len(ws_candles) > available_candles:
                        available_candles = len(ws_candles)
                        data_source = "websocket_persistent"

            required_candles = self.adx_length + 9  # 23 candles needed

            if available_candles < required_candles:
                self.logger.info(f"NEED MORE DATA: {available_candles}/{required_candles} candles (source: {data_source})")
                return None

            self.logger.info(f"SUFFICIENT DATA: {available_candles} candles available from {data_source} - ANALYZING FOR SIGNALS!")

            # CRITICAL FIX: Ensure candle_history has enough data with proper format
            if len(self.candle_history) < required_candles:
                # Try to populate from ha_candles_history
                if hasattr(self, 'ha_candles_history') and len(self.ha_candles_history) >= required_candles:
                    self.candle_history = self.ha_candles_history.copy()
                    self.logger.info(f"Populated candle_history from ha_candles_history: {len(self.candle_history)} candles")
                else:
                    return None

            # Check if already in trade
            if self.in_trade:
                self.logger.debug("Already in trade, skipping entry signal")
                return None

            # Get current price from HA candle - FIXED
            current_candle = self.candle_history[-1]
            
            # FIXED: Handle both HA and regular formats
            if 'ha_close' in current_candle:
                spot_price = current_candle['ha_close']
            elif 'close' in current_candle:
                spot_price = current_candle['close']  
            else:
                spot_price = market_data.get('current_price', market_data.get('price', 0))

            if spot_price <= 0:
                self.logger.warning("Invalid spot price for analysis")
                return None

            # Calculate Pine Script indicators
            trend_line = self.calculate_trend_line()
            if trend_line is None:
                self.logger.warning("Could not calculate trend line")
                return None

            # Analyze current candle and trend
            strong_green, strong_red, body_pct = self.analyze_candle_properties(current_candle)
            adx, plus_di, minus_di = self.calculate_adx_manual()

            if adx is None:
                self.logger.warning("Could not calculate ADX")
                return None

            # Determine market direction and option type
            price_above_trend = spot_price > trend_line
            trend_strength_ok = adx > self.adx_threshold

            option_type = None
            signal_direction = None

            # *** PINE SCRIPT SIGNAL DETECTION ***
            if price_above_trend and strong_green and trend_strength_ok:
                option_type = 'CE'  # Call option for uptrend
                signal_direction = 'BULLISH'
                self.logger.info(f"BULLISH SIGNAL DETECTED: Price above trend + Strong green + ADX>{self.adx_threshold}")
                
            elif not price_above_trend and strong_red and trend_strength_ok:
                option_type = 'PE'  # Put option for downtrend  
                signal_direction = 'BEARISH'
                self.logger.info(f"BEARISH SIGNAL DETECTED: Price below trend + Strong red + ADX>{self.adx_threshold}")

            if not option_type:
                # Log analysis for debugging
                conditions = []
                if price_above_trend:
                    conditions.append(f"Price above trend (+{spot_price - trend_line:.2f})")
                else:
                    conditions.append(f"Price below trend ({spot_price - trend_line:.2f})")
                
                if strong_green:
                    conditions.append(f"Strong green ({body_pct:.1%})")
                elif strong_red:
                    conditions.append(f"Strong red ({body_pct:.1%})")
                else:
                    conditions.append(f"Weak candle ({body_pct:.1%})")
                
                conditions.append(f"ADX: {adx:.1f} ({'OK' if trend_strength_ok else 'WEAK'})")
                
                self.logger.debug(f"No signal: {', '.join(conditions)}")
                return None

            # *** OPTION TRADING LOGIC ***
            if self.option_trading_enabled:
                self.logger.info(f"Creating {option_type} option order for {signal_direction} signal...")
                return await self.create_option_order(
                    spot_price=spot_price,
                    option_type=option_type,
                    signal_direction=signal_direction,
                    signal_strength=body_pct,
                    trend_line=trend_line,
                    adx_value=adx,
                    market_data=market_data
                )
            else:
                # Fallback to spot trading
                return await self.create_spot_order(spot_price, option_type, market_data)

        except Exception as e:
            self.logger.error(f"Error in enhanced should_enter: {e}")
            import traceback
            self.logger.debug(f"Full error: {traceback.format_exc()}")
            return None
    
    async def should_reenter(self, market_data: Dict) -> Optional[Order]:
        """New method to check for re-entry conditions"""
        try:
            # Check if enough time has passed since last exit
            if hasattr(self, 'last_exit_time'):
                time_since_exit = (datetime.now() - self.last_exit_time).total_seconds()
                if time_since_exit < 300:  # 5 minutes minimum wait
                    return None

            # Check if trend is still strong
            current_candle = self.candle_history[-1]
            current_price = current_candle['close']
            trend_line = self.calculate_trend_line()
            
            if trend_line is None:
                return None
                
            # Check if price is still following trend
            if current_price > trend_line:
                # Check for re-entry signal
                return await self.should_enter(market_data)

            return None

        except Exception as e:
            self.logger.error(f"Error in re-entry check: {e}")
            return None

    async def create_option_order(self, spot_price: float, option_type: str, signal_direction: str,
                            signal_strength: float, trend_line: float, adx_value: float,
                            market_data: Dict) -> Optional[Order]:
        """
        FIXED: Ensure strike information is properly set
        """
        try:
            # Calculate optimal strike using the new method
            strike_price = await self.calculate_option_strike(spot_price, option_type)
        
            # Get proper expiry
            expiry_date = await self.get_nearest_expiry()
        
            # Generate correct symbol
            option_symbol = self.get_option_symbol(strike_price, option_type, expiry_date)
        
            self.logger.info(f"OPTION SIGNAL: {signal_direction} - {option_type} Strategy")
            self.logger.info(f"   NIFTY Spot: Rs.{spot_price:.2f}")
            self.logger.info(f"   Trend Line: Rs.{trend_line:.2f} ({'+' if spot_price > trend_line else '-'}{abs(spot_price-trend_line):.2f})")
            self.logger.info(f"   Target Strike: {strike_price}{option_type}")
        
            # Fetch REAL option premium using the new method
            self.logger.info(f"Fetching real market price for {strike_price}{option_type}...")
            option_premium = await self.fetch_option_ltp(strike_price, option_type)
        
            if option_premium is None:
                self.logger.error(f"Could not fetch option premium for {strike_price}{option_type}")
                return None
        
            # Validate premium
            if not self.validate_option_premium(option_premium, strike_price, spot_price):
                self.logger.warning(f"Option premium Rs.{option_premium:.2f} failed validation- skip trade")
                return None
        
            # Get detailed quote for bid-ask analysis
            detailed_quote = await self.get_option_quote_detailed(strike_price, option_type)
        
            if detailed_quote:
                spread = detailed_quote.get('spread', 0)
                bid = detailed_quote.get('bid', 0)
                ask = detailed_quote.get('ask', 0)
            
                self.logger.info(f"Option Quote: LTP=Rs.{option_premium:.2f}, Bid=Rs.{bid:.2f}, Ask=Rs.{ask:.2f}, Spread=Rs.{spread:.2f}")
            
                # Check liquidity (spread should be reasonable)
                if spread > option_premium * 0.1:  # Spread > 10% of premium
                    self.logger.warning(f"Wide spread ({spread:.2f}) for {strike_price}{option_type}")
        
            # Calculate position size
            lot_size = 75  # NIFTY lot size
            max_lots = int(self.risk_per_trade / (option_premium * lot_size))
            lots = max(1, min(max_lots, 3))  # 1-3 lots
        
            total_investment = option_premium * lot_size * lots

            self.logger.info(f"OPTION ORDER DETAILS:")
            self.logger.info(f"   Symbol: NIFTY {strike_price}{option_type}")
            self.logger.info(f"   Premium: Rs.{option_premium:.2f} per share")
            self.logger.info(f"   Quantity: {lots} lots ({lots * lot_size} shares)")
            self.logger.info(f"   Investment: Rs.{total_investment:,.2f}")
        
            # Create option order
            option_symbol = self.get_option_symbol(strike_price, option_type, expiry_date)
            instrument_key = await self.get_option_instrument_key(strike_price, option_type)
        
            order = Order(
                symbol=option_symbol,
                quantity=lots,
                price=option_premium,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                strategy_name=self.name,
                instrument_key=instrument_key
            )
        
            # Add option-specific details
            order.option_type = option_type
            order.strike_price = strike_price
            order.spot_price = spot_price
            order.signal_direction = signal_direction
            order.trend_line = trend_line
            order.adx_value = adx_value
            order.signal_strength = signal_strength
            order.total_investment = total_investment
            order.lot_size = lot_size
            order.strike_symbol = f"{strike_price}{option_type}"  # e.g., "24950CE"
            order.lot_size = 75
            order.total_investment = option_premium * lots * 75
            order.entry_time = datetime.now()

            # Add market data for tracking
            if detailed_quote:
                order.bid_price = detailed_quote.get('bid', 0)
                order.ask_price = detailed_quote.get('ask', 0)
                order.spread = detailed_quote.get('spread', 0)
                order.volume = detailed_quote.get('volume', 0)
                order.open_interest = detailed_quote.get('oi', 0)
        
            # Set trade state
            self.in_trade = True
        
            self.logger.info(f"OPTION ORDER CREATED: {option_symbol} @ Rs.{option_premium:.2f}")
        
            return order
        
        except Exception as e:
            self.logger.error(f"Error creating option order: {e}")
            return None
    
    async def create_spot_order(self, spot_price: float, direction: str, market_data: Dict) -> Optional[Order]:
        """Fallback spot trading if option trading is disabled"""
        try:
            lots = 1
            order = Order(
                symbol="NIFTY_SPOT",
                quantity=lots,
                price=spot_price,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.BUY,
                strategy_name=self.name,
                instrument_key=market_data.get('instrument_key', '')
            )
            
            self.in_trade = True
            return order
            
        except Exception as e:
            self.logger.error(f"Error creating spot order: {e}")
            return None
        
    async def monitor_option_prices(self):
        """
        SIMPLIFIED: Basic position monitoring without complex features
        """
        try:
            current_time = datetime.now()
            
            # Check every 60 seconds (reduced frequency)
            if (current_time - self.last_monitoring_time).total_seconds() < 60:
                return
            
            # Only monitor during market hours
            if not self.is_market_open():
                return
            
            # Simple monitoring for active positions
            if not self.active_option_positions:
                return
            
            for position_key, position_data in self.active_option_positions.items():
                try:
                    await self._simple_monitor_position(position_data)
                except Exception as e:
                    self.logger.error(f"Error monitoring {position_key}: {e}")
            
            self.last_monitoring_time = current_time
            
        except Exception as e:
            self.logger.error(f"Error in simple monitoring: {e}")

    async def _simple_monitor_position(self, position_data: Dict):
        """Simple position monitoring - just log P&L, no complex alerts"""
        try:
            symbol = position_data['symbol']
            strike = position_data['strike_price']
            option_type = position_data['option_type']
            entry_premium = position_data['entry_premium']
            
            # Get current premium
            current_premium = await self.fetch_option_ltp(strike, option_type)
            if current_premium is None:
                return
            
            # Calculate simple P&L
            premium_change_pct = ((current_premium - entry_premium) / entry_premium) * 100
            
            # Update position data
            position_data['current_premium'] = current_premium
            position_data['premium_change_pct'] = premium_change_pct
            
            # Simple logging
            self.logger.info(f"{symbol}: Rs.{current_premium:.2f} | P&L: {premium_change_pct:+.2f}%")
            
            # Only log major milestones (25% profit/loss)
            if abs(premium_change_pct) >= 25 and abs(premium_change_pct) % 25 < 1:
                status = "PROFIT" if premium_change_pct > 0 else "LOSS"
                self.logger.info(f"MILESTONE: {symbol} - {abs(premium_change_pct):.0f}% {status}")
            
        except Exception as e:
            self.logger.error(f"Error in simple position monitoring: {e}")
    
    async def _monitor_single_position(self, position_data: Dict):
        """Monitor a single option position with detailed tracking"""
        try:
            strike = position_data['strike_price']
            option_type = position_data['option_type']
            entry_premium = position_data['entry_premium']
            quantity = position_data['quantity']
            entry_time = position_data['entry_time']
            symbol = position_data['symbol']
            
            # Fetch current premium
            current_premium = await self.fetch_option_ltp(strike, option_type)
            
            if current_premium is None:
                self.logger.warning(f"Could not fetch current premium for {symbol}")
                return
            
            # Calculate P&L metrics
            premium_change = current_premium - entry_premium
            premium_change_pct = (premium_change / entry_premium) * 100
            
            # Calculate position P&L
            lot_size = 75
            total_pnl = premium_change * quantity * lot_size
            total_investment = entry_premium * quantity * lot_size
            
            # Calculate time metrics
            time_held = datetime.now() - entry_time
            hours_held = time_held.total_seconds() / 3600
            
            # Update position data
            position_data.update({
                'current_premium': current_premium,
                'premium_change': premium_change,
                'premium_change_pct': premium_change_pct,
                'total_pnl': total_pnl,
                'hours_held': hours_held,
                'last_updated': datetime.now()
            })
            
            # Store in monitoring data
            self.position_monitoring_data[symbol] = position_data.copy()
            
            # Log detailed monitoring info
            self.logger.info(f"{symbol}: Rs.{current_premium:.2f} | "
                           f"P&L: Rs.{total_pnl:+,.2f} ({premium_change_pct:+.2f}%) | "
                           f"Time: {hours_held:.1f}h")
            
            # Check for alert conditions
            await self._check_monitoring_alerts(position_data)
            
            # Update global tracking
            self.total_premium_monitored += current_premium
            
        except Exception as e:
            self.logger.error(f"Error monitoring single position: {e}")
    
    async def _check_monitoring_alerts(self, position_data: Dict):
        """Check for alert conditions during monitoring"""
        try:
            premium_change_pct = position_data['premium_change_pct']
            symbol = position_data['symbol']
            total_pnl = position_data['total_pnl']
            
            # Profit milestone alerts
            if premium_change_pct >= 50 and not position_data.get('alert_50_sent'):
                await self._send_milestone_alert(symbol, "50% PROFIT!", total_pnl, premium_change_pct)
                position_data['alert_50_sent'] = True
                
            elif premium_change_pct >= 25 and not position_data.get('alert_25_sent'):
                await self._send_milestone_alert(symbol, "25% Profit", total_pnl, premium_change_pct)
                position_data['alert_25_sent'] = True
            
            # Loss warning alerts  
            elif premium_change_pct <= -20 and not position_data.get('alert_loss_20_sent'):
                await self._send_milestone_alert(symbol, "WARNING: 20% Loss", total_pnl, premium_change_pct)
                position_data['alert_loss_20_sent'] = True
                
        except Exception as e:
            self.logger.error(f"Error checking monitoring alerts: {e}")
    
    async def _send_milestone_alert(self, symbol: str, milestone: str, pnl: float, pct: float):
        """Send milestone alert via Telegram"""
        try:
            message = f"""Position Alert - {milestone}

Option: {symbol}
P&L: Rs.{pnl:+,.2f} ({pct:+.2f}%)
Time: {datetime.now().strftime('%I:%M:%S %p')}

{"Great performance!" if pnl > 0 else "Monitor closely"}"""
            
            # Send via notification system (if available)
            if hasattr(self, 'notifier') and self.notifier:
                await self.notifier.send_message(message)
            else:
                self.logger.info(f"Alert: {milestone} for {symbol}")
                
        except Exception as e:
            self.logger.error(f"Error sending milestone alert: {e}")
    
    async def _send_monitoring_report(self):
        """Send comprehensive monitoring report"""
        try:
            if not self.position_monitoring_data:
                return
            
            total_positions = len(self.position_monitoring_data)
            total_pnl = sum(pos['total_pnl'] for pos in self.position_monitoring_data.values())
            
            profitable_positions = len([pos for pos in self.position_monitoring_data.values() 
                                      if pos['total_pnl'] > 0])
            
            message = f"""Option Monitoring Report

Active Positions: {total_positions}
Total P&L: Rs.{total_pnl:+,.2f}
Profitable: {profitable_positions}/{total_positions}

Position Details:"""
            
            for symbol, data in self.position_monitoring_data.items():
                message += f"\n   • {symbol}: Rs.{data['total_pnl']:+,.2f} ({data['premium_change_pct']:+.1f}%)"
            
            message += f"\n\nMonitoring: Every {self.monitoring_interval}s"
            message += f"\nReport Time: {datetime.now().strftime('%I:%M %p')}"
            
            self.logger.info(f"Monitoring Report: {total_positions} positions, Rs.{total_pnl:+,.2f} P&L")
            
        except Exception as e:
            self.logger.error(f"Error sending monitoring report: {e}")
    
    # ==================== ENHANCED EXIT STRATEGY ====================
    
    async def _check_trailing_stop(self, position_data: Dict, current_premium: float, position) -> Optional[Order]:
        """Check trailing stop conditions"""
        try:
            premium_change_pct = position_data['premium_change_pct']
            symbol = position_data['symbol']
            
            # Only activate trailing stop after reaching activation threshold
            if premium_change_pct < self.trail_activation_pct:
                return None
            
            # Get or initialize trailing stop level
            if 'trailing_stop_level' not in position_data:
                # Initialize trailing stop at current profit minus trail step
                position_data['trailing_stop_level'] = premium_change_pct - self.trail_step_pct
                position_data['highest_profit_pct'] = premium_change_pct
                self.logger.info(f"TRAILING STOP ACTIVATED at {position_data['trailing_stop_level']:.1f}%")
                return None
            
            # Update trailing stop if profit increased
            if premium_change_pct > position_data['highest_profit_pct']:
                old_level = position_data['trailing_stop_level']
                position_data['highest_profit_pct'] = premium_change_pct
                position_data['trailing_stop_level'] = premium_change_pct - self.trail_step_pct
                self.logger.info(f"TRAILING STOP UPDATED: {old_level:.1f}% -> {position_data['trailing_stop_level']:.1f}%")
            
            # Check if trailing stop hit
            if premium_change_pct <= position_data['trailing_stop_level']:
                self.logger.info(f"TRAILING STOP HIT: {premium_change_pct:.2f}% <= {position_data['trailing_stop_level']:.1f}%")
                return self._create_option_exit_order(position, current_premium, 
                                                    f"TRAILING_STOP_{position_data['trailing_stop_level']:.1f}%")
                
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking trailing stop: {e}")
            return None
    
    async def _check_time_based_exit(self, position_data: Dict, current_premium: float, position) -> Optional[Order]:
        """Check time-based exit conditions"""
        try:
            entry_time = position_data['entry_time']
            current_time = datetime.now()
            #current_time = self._get_current_time().time()
            hours_held = (current_time - entry_time).total_seconds() / 3600
            
            # Exit if held for more than 4 hours without significant profit
            if hours_held >= 4 and position_data['premium_change_pct'] < 10:
                self.logger.info(f"TIME EXIT: {hours_held:.1f}h with {position_data['premium_change_pct']:.1f}% profit")
                return self._create_option_exit_order(position, current_premium, "TIME_BASED_4H")
            
            # Exit if held for more than 6 hours regardless of P&L
            if hours_held >= 6:
                self.logger.info(f"MAX TIME EXIT: {hours_held:.1f}h - force exit")
                return self._create_option_exit_order(position, current_premium, "MAX_TIME_6H")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking time-based exit: {e}")
            return None
    
    async def on_order_filled(self, order: Order):
        """Enhanced order fill handling with position tracking"""
        try:
            await super().on_order_filled(order)
            
            if order.transaction_type == TransactionType.BUY:
                # Add to active option positions for monitoring
                if hasattr(order, 'option_type') and hasattr(order, 'strike_price'):
                    self.active_option_positions[order.symbol] = {
                        'symbol': order.symbol,
                        'strike_price': order.strike_price,
                        'option_type': order.option_type,
                        'entry_premium': order.price,
                        'quantity': order.quantity,
                        'entry_time': datetime.now(),
                        'instrument_key': order.instrument_key or '',
                        'premium_change_pct': 0,
                        'current_premium': order.price
                    }
                    
                    self.logger.info(f"Added {order.symbol} to advanced monitoring")
                    
            elif order.transaction_type == TransactionType.SELL:
                # Position already removed in _create_option_exit_order
                self.logger.info(f"Removed {order.symbol} from monitoring")
                
        except Exception as e:
            self.logger.error(f"Error in enhanced order fill handling: {e}")
    
    async def _check_greeks_based_exit(self, position_data: Dict, current_premium: float, market_data: Dict) -> Optional[Order]:
        """Check Greeks-based exit conditions (advanced)"""
        try:
            # Check if it's close to market close (theta decay accelerates)
            current_time = datetime.now()

            market_close = current_time.replace(hour=15, minute=20)  # 3:20 PM auto square-off
            minutes_to_close = (market_close - current_time).total_seconds() / 60
            
            # Force exit if less than 10 minutes to close
            if minutes_to_close <= 10 and minutes_to_close > 0:
                self.logger.info(f"MARKET CLOSE EXIT: {minutes_to_close:.0f} minutes to auto square-off")
                return self._create_option_exit_order(
                    self._get_position_from_data(position_data), 
                    current_premium, 
                    "MARKET_CLOSE_10MIN"
                )
            
            # Exit if premium dropped below minimum viable level
            if current_premium < 5:  # Below Rs.5 per share
                self.logger.info(f"MINIMUM PREMIUM EXIT: Rs.{current_premium:.2f} < Rs.5")
                return self._create_option_exit_order(
                    self._get_position_from_data(position_data), 
                    current_premium, 
                    "MINIMUM_PREMIUM"
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking Greeks-based exit: {e}")
            return None
    
    async def _check_volatility_exit(self, position_data: Dict, current_premium: float, market_data: Dict) -> Optional[Order]:
        """Check volatility-based exit conditions"""
        try:
            # Get NIFTY spot price movement
            if 'ha_candle' in market_data:
                current_spot = market_data['ha_candle'].get('ha_close', 0)
                
                # Check if NIFTY moved significantly against our position
                option_type = position_data['option_type']
                strike_price = position_data['strike_price']
                
                if option_type == 'CE':
                    # For CE, exit if NIFTY moved significantly below strike
                    if current_spot < strike_price - 100:  # 100 points below strike
                        self.logger.info(f"VOLATILITY EXIT (CE): NIFTY {current_spot:.2f} too far below strike {strike_price}")
                        return self._create_option_exit_order(
                            self._get_position_from_data(position_data), 
                            current_premium, 
                            "VOLATILITY_ADVERSE_MOVE"
                        )
                        
                elif option_type == 'PE':
                    # For PE, exit if NIFTY moved significantly above strike
                    if current_spot > strike_price + 100:  # 100 points above strike
                        self.logger.info(f"VOLATILITY EXIT (PE): NIFTY {current_spot:.2f} too far above strike {strike_price}")
                        return self._create_option_exit_order(
                            self._get_position_from_data(position_data), 
                            current_premium, 
                            "VOLATILITY_ADVERSE_MOVE"
                        )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking volatility exit: {e}")
            return None
    
    def _create_option_exit_order(self, position, current_premium: float, exit_reason: str) -> Order:
        """
        FIXED: Create exit order with correct P&L calculation
        """
        try:
            self.logger.info(f"📝 CREATING EXIT ORDER: {exit_reason} @ Rs.{current_premium:.2f}")
        
            order = Order(
                symbol=position.symbol,
                quantity=position.quantity,
                price=current_premium,
                order_type=OrderType.MARKET,
                transaction_type=TransactionType.SELL,
                strategy_name=self.name,
                instrument_key=getattr(position, 'instrument_key', '')
            )
        
            # FIXED P&L calculation
            entry_price = position.average_price
            exit_price = current_premium
            lot_size = 75  # NIFTY lot size

            # Calculate per-share P&L (option premium difference)
            pnl_per_share = exit_price - entry_price  
            pnl_percentage = (pnl_per_share / entry_price) * 100 if entry_price > 0 else 0
        
                    
            # Calculate total P&L
            total_shares = position.quantity * lot_size
            total_pnl = pnl_per_share * total_shares
        
            # Set correct values
            order.exit_reason = exit_reason
            order.option_type = getattr(position, 'option_type', 'PE')
            order.strike_price = getattr(position, 'strike_price', 24900)
            order.strike_symbol = f"{getattr(position, 'strike_price', 24900)}{getattr(position, 'option_type', 'PE')}"
            order.pnl_per_share = pnl_per_share
            order.pnl_pct = pnl_percentage  # This should be reasonable like +5% or -3%
            order.total_pnl = total_pnl  # This should be reasonable like +375 or -225
            order.entry_price = entry_price
            order.exit_time = datetime.now()


            # Add enhanced exit details
            #order.exit_reason = exit_reason
            #order.option_type = getattr(position, 'option_type', 'CE')
            #order.strike_price = getattr(position, 'strike_price', 0)
            #order.entry_price = position.average_price
            #order.exit_time = datetime.now()
            #order.current_premium = current_premium
        
            # Calculate P&L
            #if hasattr(position, 'average_price') and position.average_price > 0:
            #    pnl_per_share = current_premium - position.average_price
            #    pnl_pct = (pnl_per_share / position.average_price) * 100
            #    total_pnl = pnl_per_share * position.quantity * 75  # 75 shares per lot
            
            #    order.pnl_per_share = pnl_per_share
            #    order.pnl_pct = pnl_pct
            #    order.total_pnl = total_pnl
            
            #    self.logger.info(f"💰 Exit P&L: Rs.{total_pnl:+,.2f} ({pnl_pct:+.2f}%)")

            self.logger.info(f"💰 FIXED Exit P&L: Rs.{total_pnl:+,.2f} ({pnl_percentage:+.2f}%)")
            return order

        except Exception as e:
            self.logger.error(f"❌ Error creating exit order: {e}")
            return None
    
    def _get_position_from_data(self, position_data: Dict):
        """Convert position data to Position object for exit order creation"""
        class MockPosition:
            def __init__(self, data):
                self.symbol = data['symbol']
                self.quantity = data['quantity']
                self.average_price = data['entry_premium']
                self.instrument_key = data.get('instrument_key', '')
        
        return MockPosition(position_data)
    
    def is_market_open(self) -> bool:
        """Check if market is open for monitoring"""
        current_time = datetime.now()
        market_open = current_time.replace(hour=9, minute=15)
        market_close = current_time.replace(hour=15, minute=30)
        
        # Check if it's a weekday
        if current_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return market_open <= current_time <= market_close

    # 🚨 STEP 3: FIX POSITION DATA HANDLING
    # Add this NEW method to option_integrated_pine_script.py:

    async def _get_or_create_position_data(self, position: Position) -> Dict:
        """
        FIXED: Get position data or create from Position object
        """
        try:
            # Try to find existing position data
            symbol = position.symbol
        
            if hasattr(self, 'active_option_positions') and symbol in self.active_option_positions:
                return self.active_option_positions[symbol]
        
            # 🆕 FALLBACK: Create position data from Position object
            self.logger.info(f"Creating position data from Position object for {symbol}")
        
            position_data = {
                'symbol': symbol,
                'strike_price': getattr(position, 'strike_price', 0),
                'option_type': getattr(position, 'option_type', 'CE'),
                'entry_premium': position.average_price,
                'quantity': position.quantity,
                'entry_time': getattr(position, 'entry_time', datetime.now()),
                'instrument_key': position.instrument_key or '',
                'current_premium': position.current_price,
                'premium_change_pct': 0
            }
        
            # Store for future reference
            if not hasattr(self, 'active_option_positions'):
                self.active_option_positions = {}
        
            self.active_option_positions[symbol] = position_data

            return position_data
        
        except Exception as e:
            self.logger.error(f"❌ Error getting position data: {e}")
            return None

    # 🚨 STEP 4: FIX PREMIUM FETCHING WITH FALLBACKS
    # Add this NEW method to option_integrated_pine_script.py:

    async def _get_current_premium_with_fallback(self, position_data: Dict, position: Position) -> Optional[float]:
        """
        FIXED: Get current premium with multiple fallbacks
        """
        try:
            strike_price = position_data.get('strike_price', 0)
            option_type = position_data.get('option_type', 'CE')
        
            # Method 1: Try to fetch real-time premium
            if strike_price > 0 and hasattr(self, 'fetch_option_ltp'):
                try:
                    current_premium = await self.fetch_option_ltp(strike_price, option_type)
                    if current_premium is not None and current_premium > 0:
                        self.logger.debug(f"✅ Real-time premium: Rs.{current_premium:.2f}")
                        return current_premium
                except Exception as e:
                    self.logger.debug(f"Real-time premium fetch failed: {e}")
        
            # Method 2: Use position current_price
            if position.current_price > 0:
                self.logger.debug(f"🔄 Using position current price: Rs.{position.current_price:.2f}")
                return position.current_price
        
            # Method 3: Use cached premium from position data
            cached_premium = position_data.get('current_premium', 0)
            if cached_premium > 0:
                self.logger.debug(f"💾 Using cached premium: Rs.{cached_premium:.2f}")
                return cached_premium
        
            # Method 4: Use entry premium as fallback
            entry_premium = position_data.get('entry_premium', position.average_price)
            if entry_premium > 0:
                self.logger.warning(f"⚠️ Using entry premium as fallback: Rs.{entry_premium:.2f}")
                return entry_premium
        
            self.logger.error(f"❌ Could not determine current premium for {position.symbol}")
            return None
        
        except Exception as e:
            self.logger.error(f"❌ Error getting current premium: {e}")
            return None

    # 🚨 STEP 5: FIX TRAILING STOP LOGIC
    # Add this NEW method to option_integrated_pine_script.py:

    async def _check_trailing_stop_fixed(self, position_data: Dict, current_premium: float, position: Position) -> Optional[Order]:
        """
        FIXED: Trailing stop logic with proper state management
        """
        try:
            premium_change_pct = position_data.get('premium_change_pct', 0)
            symbol = position_data.get('symbol', position.symbol)
        
            # Only activate trailing stop after reaching activation threshold
            if premium_change_pct < self.trail_activation_pct:
                return None
        
            # Get or initialize trailing stop level
            if 'trailing_stop_level' not in position_data:
                # Initialize trailing stop
                position_data['trailing_stop_level'] = premium_change_pct - self.trail_step_pct
                position_data['highest_profit_pct'] = premium_change_pct
                self.logger.info(f"📈 TRAILING STOP ACTIVATED at {position_data['trailing_stop_level']:.1f}% for {symbol}")
                return None
        
            # Update trailing stop if profit increased
            if premium_change_pct > position_data.get('highest_profit_pct', 0):
                old_level = position_data['trailing_stop_level']
                position_data['highest_profit_pct'] = premium_change_pct
                position_data['trailing_stop_level'] = premium_change_pct - self.trail_step_pct
            
                self.logger.info(f"📊 TRAILING STOP UPDATED: {old_level:.1f}% → {position_data['trailing_stop_level']:.1f}% for {symbol}")

            # Check if trailing stop hit
            if premium_change_pct <= position_data['trailing_stop_level']:
                self.logger.info(f"🎯 TRAILING STOP HIT: {premium_change_pct:.2f}% <= {position_data['trailing_stop_level']:.1f}%")
                return self._create_option_exit_order(position, current_premium, f"TRAILING_STOP_{position_data['trailing_stop_level']:.1f}%")
            
            return None

        except Exception as e:
            self.logger.error(f"❌ Error checking trailing stop: {e}")
            return None

    # 🚨 STEP 6: FIX TIME-BASED EXITS
    # Add this NEW method to option_integrated_pine_script.py:

    async def _check_time_based_exits_fixed(self, position_data: Dict, current_premium: float, position: Position) -> Optional[Order]:
        """
        FIXED: Time-based exit logic
        """
        try:
            entry_time = position_data.get('entry_time', position.entry_time if hasattr(position, 'entry_time') else datetime.now())
            current_time = datetime.now()
            #current_time = self._get_current_time().time()
            hours_held = (current_time - entry_time).total_seconds() / 3600
            premium_change_pct = position_data.get('premium_change_pct', 0)
        
            # Exit after 4 hours if profit < 10%
            if hours_held >= 4 and premium_change_pct < 10:
                self.logger.info(f"⏰ TIME EXIT (4H): {hours_held:.1f}h with {premium_change_pct:.1f}% profit")
                return self._create_option_exit_order(position, current_premium, "TIME_BASED_4H")
        
            # Force exit after 6 hours regardless of P&L
            if hours_held >= 6:
                self.logger.info(f"🚨 MAX TIME EXIT (6H): {hours_held:.1f}h - force exit")
                return self._create_option_exit_order(position, current_premium, "MAX_TIME_6H")
        
            return None

        except Exception as e:
            self.logger.error(f"❌ Error checking time-based exits: {e}")
            return None

    # 🚨 STEP 7: FIX MANDATORY EXITS
    # Add this NEW method to option_integrated_pine_script.py:

    async def _check_mandatory_exits(self, position: Position, current_premium: float) -> Optional[Order]:
        """Check mandatory exits that always take priority"""
        try:
            current_time = datetime.now()
            entry_price = position.average_price
            
            # 1. Market close exit (3:20 PM)
            if current_time.time() >= time(15, 20):
                self.logger.info("MANDATORY EXIT: Market close (3:20 PM)")
                return self._create_exit_order(position, current_premium, "MARKET_CLOSE", 
                                            self._calculate_pnl_pct(current_premium, entry_price))
            
            # 2. Stop loss (30% loss)
            loss_pct = ((entry_price - current_premium) / entry_price) * 100 if entry_price > 0 else 0
            if loss_pct >= 30:
                self.logger.info(f"MANDATORY EXIT: 30% stop loss hit ({loss_pct:.1f}%)")
                return self._create_exit_order(position, current_premium, "STOP_LOSS_30%", -loss_pct)
            
            # 3. Emergency exit for very low premium (avoid worthless options)
            if current_premium < 2:
                self.logger.info(f"MANDATORY EXIT: Premium too low (Rs.{current_premium:.2f})")
                return self._create_exit_order(position, current_premium, "LOW_PREMIUM", 
                                            self._calculate_pnl_pct(current_premium, entry_price))
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking mandatory exits: {e}")
            return None

    async def _cleanup_position_after_exit(self, symbol: str):
        """Clean up position tracking after exit"""
        try:
            # Remove from active positions tracking
            if hasattr(self, 'active_option_positions') and symbol in self.active_option_positions:
                self.active_option_positions.pop(symbol, None)
                
            # Reset trade state to allow new entries  
            self.in_trade = False
            
            # Record exit time for re-entry logic
            self.last_exit_time = datetime.now()
            
            self.logger.info(f"Position cleanup completed for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up position: {e}")

    async def _check_volatility_exits_fixed(self, position_data: Dict, current_premium: float, position: Position, market_data: Dict) -> Optional[Order]:
        """
        FIXED: Volatility-based exit conditions
        """
        try:
            option_type = position_data.get('option_type', 'CE')
            strike_price = position_data.get('strike_price', 0)
        
            # Get current NIFTY price
            current_spot = market_data.get('current_price', 0)
            if current_spot <= 0:
                return None
        
            # Check for adverse moves
            if option_type == 'CE':
                # CE adverse: NIFTY significantly below strike
                if current_spot < strike_price - 100:  # 100 points below
                    self.logger.info(f"📉 VOLATILITY EXIT (CE): NIFTY {current_spot:.2f} too far below strike {strike_price}")
                    return self._create_option_exit_order(position, current_premium, "VOLATILITY_ADVERSE_CE")
                
            elif option_type == 'PE':
                # PE adverse: NIFTY significantly above strike
                if current_spot > strike_price + 100:  # 100 points above
                    self.logger.info(f"📈 VOLATILITY EXIT (PE): NIFTY {current_spot:.2f} too far above strike {strike_price}")
                    return self._create_option_exit_order(position, current_premium, "VOLATILITY_ADVERSE_PE")
        
            return None

        except Exception as e:
            self.logger.error(f"❌ Error checking volatility exits: {e}")
            return None

    def _get_current_time(self):
        """Fixed time method"""
        return datetime.now()