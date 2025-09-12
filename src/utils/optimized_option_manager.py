import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class OptimizedOptionManager:
    """Single API call solution for position monitoring"""
    
    def __init__(self, upstox_client):
        self.upstox_client = upstox_client
        self.logger = logging.getLogger(__name__)
        
        # Cache settings
        self.option_chain_cache = None
        self.cache_time = None
        self.cache_duration = 90  # 90 seconds cache
        
    async def get_all_position_ltps(self, positions: List) -> Dict:
        """Get LTP for all positions with single API call"""
        try:
            if not positions:
                return {}
            
            # Get cached option chain
            option_chain = await self._get_cached_option_chain()
            if not option_chain:
                self.logger.error("Could not get option chain")
                return {}
            
            # Extract LTPs for all positions
            position_data = {}
            
            for position in positions:
                try:
                    symbol = position.symbol
                    strike = getattr(position, 'strike_price', 0)
                    option_type = getattr(position, 'option_type', 'CE')
                    
                    if strike > 0 and strike in option_chain.get('strikes', {}):
                        strike_data = option_chain['strikes'][strike]
                        
                        ltp = None
                        if option_type == 'CE' and 'ce' in strike_data:
                            ltp = strike_data['ce'].get('ltp')
                        elif option_type == 'PE' and 'pe' in strike_data:
                            ltp = strike_data['pe'].get('ltp')
                        
                        if ltp and ltp > 0:
                            position_data[symbol] = {
                                'ltp': float(ltp),
                                'entry_price': position.average_price,
                                'pnl_pct': ((float(ltp) - position.average_price) / position.average_price) * 100
                            }
                            
                except Exception as e:
                    self.logger.debug(f"Error processing position {position.symbol}: {e}")
                    continue
            
            self.logger.info(f"SUCCESS: Got LTPs for {len(position_data)}/{len(positions)} positions")
            return position_data
            
        except Exception as e:
            self.logger.error(f"Error in get_all_position_ltps: {e}")
            return {}
    
    async def _get_cached_option_chain(self) -> Optional[Dict]:
        """Get option chain with detailed debugging"""
        try:
            cache_key = "NIFTY_CHAIN"
            current_time = datetime.now()
            
            # Check cache first
            if (self.option_chain_cache and self.cache_time and 
                (current_time - self.cache_time).total_seconds() < self.cache_duration):
                self.logger.debug("Using cached option chain")
                return self.option_chain_cache
            
            # Fetch fresh data with detailed logging
            self.logger.info("Cache miss - fetching fresh option chain...")
            
            if hasattr(self.upstox_client, 'option_chain_manager'):
                self.logger.info("Calling option_chain_manager.get_option_chain...")
                option_chain = await self.upstox_client.option_chain_manager.get_option_chain("NIFTY", 15)
                
                if option_chain:
                    self.logger.info(f"Option chain received: {len(option_chain.get('strikes', {}))} strikes")
                    self.option_chain_cache = option_chain
                    self.cache_time = current_time
                    return option_chain
                else:
                    self.logger.error("Option chain returned None/empty")
                    return None
            else:
                self.logger.error("option_chain_manager not found in upstox_client")
                return None
            
        except Exception as e:
            self.logger.error(f"Exception in _get_cached_option_chain: {e}")
            import traceback
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            return None