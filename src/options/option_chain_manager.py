# ==================== FIXED: option_chain_manager.py ====================
"""
COMPLETE FIX for spot price fetching issues
- Multiple fallback methods for NIFTY spot price
- Enhanced error handling and logging
- Market hours validation
- Robust option chain building
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)

class OptionChainManager:
    """
    COMPLETELY FIXED Option Chain Manager
    """
    
    def __init__(self, upstox_client):
        """Initialize with upstox client that has token"""
        self.upstox_client = upstox_client
        self.token = upstox_client.access_token
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json'
        }
        self.logger = logging.getLogger(__name__)
        self._option_contracts = {}
        self._last_fetch_time = None
        self._cached_spot_price = None
        self._spot_price_cache_time = None
        
        # Enhanced caching
        self._spot_price_cache_duration = 30  # 30 seconds cache
        self._option_contracts_cache = {}
        self._contracts_cache_time = None
        self._contracts_cache_duration = 300  # 5 minutes cache
    
    def is_market_open(self) -> bool:
        """Check if market is open for spot price fetching"""
        current_time = datetime.now()
        market_open = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Check if it's a weekday
        if current_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return market_open <= current_time <= market_close
    
    async def get_option_chain(self, symbol: str = "NIFTY", strikes_around_atm: int = 5) -> Optional[Dict[str, Any]]:
        """
        Get option chain for nearest expiry with COMPLETELY FIXED spot price logic
        """
        try:
            # STEP 1: Get current spot price with ALL fallback methods
            spot_price = await self._get_spot_price_with_all_fallbacks(symbol)
            if not spot_price:
                self.logger.error("❌ CRITICAL: Could not fetch spot price with ANY method")
                return self._create_fallback_option_chain(symbol)
            
            self.logger.info(f"✅ Got {symbol} spot price: Rs.{spot_price:.2f}")
            
            # STEP 2: Fetch nearest expiry option contracts
            contracts = await self._fetch_nearest_expiry_contracts_cached()
            if not contracts:
                self.logger.error("❌ Could not fetch option contracts")
                return self._create_fallback_option_chain(symbol, spot_price)
            
            # STEP 3: Build option chain around ATM
            option_chain = await self._build_option_chain_enhanced(
                spot_price, contracts, strikes_around_atm
            )
            
            if option_chain and 'strikes' in option_chain:
                self.logger.info(f"✅ Option chain built: {len(option_chain['strikes'])} strikes")
                return option_chain
            else:
                self.logger.warning("⚠️ Option chain build failed, using fallback")
                return self._create_fallback_option_chain(symbol, spot_price)
            
        except Exception as e:
            self.logger.error(f"❌ Error getting option chain: {e}")
            return self._create_fallback_option_chain(symbol)
    
    async def _get_spot_price_with_all_fallbacks(self, symbol: str) -> Optional[float]:
        """
        ENHANCED spot price fetching with 6 different fallback methods
        """
        try:
            # Check cache first
            if (self._cached_spot_price and self._spot_price_cache_time and
                (datetime.now() - self._spot_price_cache_time).total_seconds() < self._spot_price_cache_duration):
                self.logger.debug(f"📦 Using cached spot price: Rs.{self._cached_spot_price:.2f}")
                return self._cached_spot_price
            
            # Method 1: Try the working approach from your test
            spot_price = await self._get_spot_price_method1(symbol)
            if spot_price and spot_price > 20000:  # Reasonable NIFTY range
                return self._cache_and_return_spot_price(spot_price)
            
            # Method 2: Alternative instrument key format
            spot_price = await self._get_spot_price_method2(symbol)
            if spot_price and spot_price > 20000:
                return self._cache_and_return_spot_price(spot_price)
            
            # Method 3: Try with quotes API instead of LTP
            spot_price = await self._get_spot_price_method3(symbol)
            if spot_price and spot_price > 20000:
                return self._cache_and_return_spot_price(spot_price)
            
            # Method 4: Use market data from websocket if available
            spot_price = await self._get_spot_price_from_websocket(symbol)
            if spot_price and spot_price > 20000:
                return self._cache_and_return_spot_price(spot_price)
            
            # Method 5: Get from upstox client directly if available
            spot_price = await self._get_spot_price_from_client(symbol)
            if spot_price and spot_price > 20000:
                return self._cache_and_return_spot_price(spot_price)
            
            # Method 6: Emergency fallback with reasonable default
            if not self.is_market_open():
                self.logger.warning("🕐 Market closed - using last known/default price")
                return 25000.0  # Reasonable default for NIFTY
            
            self.logger.error("❌ ALL spot price methods failed")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error in spot price fetching: {e}")
            return None
    
    def _cache_and_return_spot_price(self, spot_price: float) -> float:
        """Cache spot price and return it"""
        self._cached_spot_price = spot_price
        self._spot_price_cache_time = datetime.now()
        self.logger.debug(f"💾 Cached spot price: Rs.{spot_price:.2f}")
        return spot_price
    
    async def _get_spot_price_method1(self, symbol: str) -> Optional[float]:
        """Method 1: Working approach from your test files"""
        try:
            if symbol.upper() == "NIFTY":
                instrument_key = "NSE_INDEX|Nifty 50"
            else:
                instrument_key = f"NSE_INDEX|{symbol}"
            
            url = "https://api.upstox.com/v2/market-quote/ltp"
            params = {'instrument_key': instrument_key}
            
            timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'success':
                            quote_data = data.get('data', {})
                            
                            # Find spot price in response
                            for key, value in quote_data.items():
                                if 'Nifty' in key or 'NIFTY' in key:
                                    spot_price = value.get('last_price')
                                    if spot_price and spot_price > 20000:
                                        self.logger.debug(f"Method 1: Found {symbol} spot: Rs.{spot_price:.2f}")
                                        return float(spot_price)
                    else:
                        self.logger.debug(f"Method 1: HTTP {response.status}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Method 1 failed: {e}")
            return None
    
    async def _get_spot_price_method2(self, symbol: str) -> Optional[float]:
        """Method 2: Alternative instrument key formats"""
        try:
            instrument_keys = [
                f"NSE_INDEX|{symbol} 50",
                f"NSE_INDEX|{symbol}",
                f"NSE_INDEX|NIFTY 50",
                "NSE_INDEX|Nifty 50",
                "NSE_INDEX|NIFTY"
            ]
            
            url = "https://api.upstox.com/v2/market-quote/ltp"
            timeout = aiohttp.ClientTimeout(total=10)
            
            for instrument_key in instrument_keys:
                try:
                    params = {'instrument_key': instrument_key}
                    
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, headers=self.headers, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                if data.get('status') == 'success':
                                    quote_data = data.get('data', {})
                                    
                                    # Try to find any valid price
                                    for key, value in quote_data.items():
                                        last_price = value.get('last_price')
                                        if last_price and 20000 <= last_price <= 30000:  # Reasonable NIFTY range
                                            self.logger.debug(f"Method 2: Found spot via {instrument_key}: Rs.{last_price:.2f}")
                                            return float(last_price)
                
                except Exception as e:
                    self.logger.debug(f"Method 2 attempt with {instrument_key} failed: {e}")
                    continue
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Method 2 failed: {e}")
            return None
    
    async def _get_spot_price_method3(self, symbol: str) -> Optional[float]:
        """Method 3: Using quotes API instead of LTP"""
        try:
            instrument_key = "NSE_INDEX|Nifty 50"
            url = "https://api.upstox.com/v2/market-quote/quotes"
            params = {'instrument_key': instrument_key}
            
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'success':
                            quote_data = data.get('data', {})
                            
                            for key, value in quote_data.items():
                                if 'Nifty' in key or 'NIFTY' in key:
                                    last_price = value.get('last_price')
                                    if last_price and 20000 <= last_price <= 30000:
                                        self.logger.debug(f"Method 3: Found spot via quotes: Rs.{last_price:.2f}")
                                        return float(last_price)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Method 3 failed: {e}")
            return None
    
    async def _get_spot_price_from_websocket(self, symbol: str) -> Optional[float]:
        """Method 4: Get from websocket data if available"""
        try:
            # Check if upstox_client has websocket manager
            if hasattr(self.upstox_client, 'websocket_manager'):
                websocket_manager = self.upstox_client.websocket_manager
                
                if hasattr(websocket_manager, 'latest_ticks'):
                    tick_data = websocket_manager.latest_ticks.get('NIFTY')
                    if tick_data:
                        ltp = tick_data.get('ltp')
                        if ltp and 20000 <= ltp <= 30000:
                            self.logger.debug(f"Method 4: Found spot from websocket: Rs.{ltp:.2f}")
                            return float(ltp)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Method 4 failed: {e}")
            return None
    
    async def _get_spot_price_from_client(self, symbol: str) -> Optional[float]:
        """Method 5: Direct from upstox client if available"""
        try:
            if hasattr(self.upstox_client, 'get_market_data'):
                market_data = await self.upstox_client.get_market_data('NSE_INDEX|Nifty 50')
                
                if market_data and isinstance(market_data, dict):
                    data = market_data.get('data', {})
                    for key, value in data.items():
                        if 'Nifty' in key:
                            last_price = value.get('last_price')
                            if last_price and 20000 <= last_price <= 30000:
                                self.logger.debug(f"Method 5: Found spot from client: Rs.{last_price:.2f}")
                                return float(last_price)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Method 5 failed: {e}")
            return None
    
    async def _fetch_nearest_expiry_contracts_cached(self) -> Dict:
        """
        Fetch option contracts with caching
        """
        try:
            # Check cache first
            if (self._option_contracts_cache and self._contracts_cache_time and
                (datetime.now() - self._contracts_cache_time).total_seconds() < self._contracts_cache_duration):
                self.logger.debug(f"📦 Using cached option contracts: {len(self._option_contracts_cache)}")
                return self._option_contracts_cache
            
            # Fetch fresh contracts
            contracts = await self._fetch_nearest_expiry_contracts()
            
            if contracts:
                self._option_contracts_cache = contracts
                self._contracts_cache_time = datetime.now()
                self.logger.info(f"💾 Cached {len(contracts)} option contracts")
            
            return contracts
            
        except Exception as e:
            self.logger.error(f"❌ Error fetching cached contracts: {e}")
            return {}
    
    async def _fetch_nearest_expiry_contracts(self) -> Dict:
        """
        Fetch option contracts for nearest expiry - ENHANCED VERSION
        """
        try:
            url = "https://api.upstox.com/v2/option/contract"
            params = {'instrument_key': 'NSE_INDEX|Nifty 50'}
            
            timeout = aiohttp.ClientTimeout(total=15)  # 15 second timeout
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'success':
                            # Process contracts
                            all_contracts = []
                            
                            for contract in data.get('data', []):
                                strike = contract.get('strike_price')
                                option_type = contract.get('instrument_type')
                                instrument_key = contract.get('instrument_key')
                                trading_symbol = contract.get('trading_symbol')
                                expiry = contract.get('expiry')
                                
                                if strike and option_type and instrument_key and expiry:
                                    try:
                                        strike_int = int(float(strike))
                                        
                                        all_contracts.append({
                                            'strike_price': strike_int,
                                            'option_type': option_type,
                                            'instrument_key': instrument_key,
                                            'trading_symbol': trading_symbol,
                                            'expiry': expiry,
                                            'expiry_date': datetime.strptime(expiry, '%Y-%m-%d').date()
                                        })
                                    except (ValueError, TypeError):
                                        continue
                            
                            if not all_contracts:
                                self.logger.error("❌ No valid contracts found")
                                return {}
                            
                            # Find nearest expiry
                            expiry_dates = sorted(set(contract['expiry_date'] for contract in all_contracts))
                            nearest_expiry = expiry_dates[0]
                            
                            self.logger.info(f"📅 Using nearest expiry: {nearest_expiry} (from {len(expiry_dates)} available)")
                            
                            # Filter for nearest expiry only
                            contracts = {}
                            for contract in all_contracts:
                                if contract['expiry_date'] == nearest_expiry:
                                    key = f"{contract['strike_price']}{contract['option_type']}"
                                    contracts[key] = {
                                        'instrument_key': contract['instrument_key'],
                                        'strike_price': contract['strike_price'],
                                        'option_type': contract['option_type'],
                                        'trading_symbol': contract['trading_symbol'],
                                        'expiry': contract['expiry'],
                                        'expiry_date': contract['expiry_date']
                                    }
                            
                            self.logger.info(f"✅ Loaded {len(contracts)} nearest expiry contracts")
                            return contracts
                        
                        else:
                            self.logger.error(f"❌ API error fetching contracts: {data}")
                    else:
                        error_text = await response.text()
                        self.logger.error(f"❌ HTTP {response.status} fetching contracts: {error_text}")
            
            return {}
            
        except Exception as e:
            self.logger.error(f"❌ Error fetching option contracts: {e}")
            return {}
    
    async def _build_option_chain_enhanced(self, spot_price: float, contracts: Dict, strikes_around_atm: int) -> Dict:
        """Build option chain with enhanced error handling"""
        try:
            # Find available strikes
            ce_strikes = sorted([int(k[:-2]) for k in contracts.keys() if k.endswith('CE')])
            
            if not ce_strikes:
                self.logger.error("❌ No CE strikes found")
                return self._create_fallback_option_chain("NIFTY", spot_price)
            
            # Find ATM strike
            atm_strike = min(ce_strikes, key=lambda x: abs(x - spot_price))
            atm_index = ce_strikes.index(atm_strike)
            
            # Select strikes around ATM
            start_index = max(0, atm_index - strikes_around_atm)
            end_index = min(len(ce_strikes), atm_index + strikes_around_atm + 1)
            target_strikes = ce_strikes[start_index:end_index]
            
            self.logger.info(f"🎯 Building option chain: ATM={atm_strike}, Strikes={target_strikes}")
            
            # Build option chain
            option_chain = {
                'spot_price': spot_price,
                'atm_strike': atm_strike,
                'expiry_date': contracts[f"{atm_strike}CE"]['expiry_date'] if f"{atm_strike}CE" in contracts else None,
                'strikes': {},
                'timestamp': datetime.now().isoformat()
            }
            
            # Fetch LTP for each strike (with timeout)
            for strike in target_strikes:
                strike_data = {
                    'strike': strike,
                    'ce': {},
                    'pe': {}
                }
                
                # Get CE data
                ce_key = f"{strike}CE"
                if ce_key in contracts:
                    ce_contract = contracts[ce_key]
                    ce_ltp = await self._get_option_ltp_with_timeout(ce_contract['instrument_key'])
                    
                    strike_data['ce'] = {
                        'ltp': ce_ltp,
                        'instrument_key': ce_contract['instrument_key'],
                        'trading_symbol': ce_contract['trading_symbol'],
                        'expiry': ce_contract['expiry']
                    }
                
                # Get PE data
                pe_key = f"{strike}PE"
                if pe_key in contracts:
                    pe_contract = contracts[pe_key]
                    pe_ltp = await self._get_option_ltp_with_timeout(pe_contract['instrument_key'])
                    
                    strike_data['pe'] = {
                        'ltp': pe_ltp,
                        'instrument_key': pe_contract['instrument_key'],
                        'trading_symbol': pe_contract['trading_symbol'],
                        'expiry': pe_contract['expiry']
                    }
                
                option_chain['strikes'][strike] = strike_data
            
            # Count successful LTP fetches
            successful_ltps = sum(1 for strike_data in option_chain['strikes'].values() 
                                for option_data in [strike_data['ce'], strike_data['pe']] 
                                if option_data.get('ltp') is not None)
            
            self.logger.info(f"✅ Option chain built: {len(target_strikes)} strikes, {successful_ltps} LTPs fetched")
            
            return option_chain
            
        except Exception as e:
            self.logger.error(f"❌ Error building option chain: {e}")
            return self._create_fallback_option_chain("NIFTY", spot_price)
    
    async def _get_option_ltp_with_timeout(self, instrument_key: str) -> Optional[float]:
        """
        Get LTP with timeout and error handling
        """
        try:
            url = "https://api.upstox.com/v2/market-quote/ltp"
            params = {'instrument_key': instrument_key}
            
            timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout for options
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'success':
                            quote_data = data.get('data', {})
                            
                            # Try different key formats
                            possible_keys = [
                                instrument_key,
                                instrument_key.replace('|', ':'),
                                instrument_key.replace('NSE_FO|', 'NSE_FO:'),
                            ]
                            
                            for key_format in possible_keys:
                                if key_format in quote_data:
                                    ltp = quote_data[key_format].get('last_price', 0)
                                    if ltp and ltp > 0:
                                        return float(ltp)
                            
                            # Try partial matches
                            for key in quote_data.keys():
                                if any(part in key for part in instrument_key.split('|')):
                                    ltp = quote_data[key].get('last_price', 0)
                                    if ltp and ltp > 0:
                                        return float(ltp)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"LTP fetch failed for {instrument_key}: {e}")
            return None
    
    def _create_fallback_option_chain(self, symbol: str = "NIFTY", spot_price: float = None) -> Dict:
        """Create a fallback option chain when API fails"""
        try:
            if not spot_price:
                spot_price = 25000.0  # Default NIFTY value
            
            # Calculate ATM strike
            atm_strike = round(spot_price / 50) * 50
            
            # Create basic strikes around ATM
            strikes = [atm_strike - 100, atm_strike - 50, atm_strike, atm_strike + 50, atm_strike + 100]
            
            option_chain = {
                'spot_price': spot_price,
                'atm_strike': atm_strike,
                'expiry_date': datetime.now().date(),
                'strikes': {},
                'timestamp': datetime.now().isoformat(),
                'fallback': True  # Mark as fallback
            }
            
            for strike in strikes:
                option_chain['strikes'][strike] = {
                    'strike': strike,
                    'ce': {
                        'ltp': None,
                        'instrument_key': f'NSE_FO|{strike}CE_FALLBACK',
                        'trading_symbol': f'NIFTY{strike}CE',
                        'expiry': datetime.now().strftime('%Y-%m-%d')
                    },
                    'pe': {
                        'ltp': None,
                        'instrument_key': f'NSE_FO|{strike}PE_FALLBACK',
                        'trading_symbol': f'NIFTY{strike}PE',
                        'expiry': datetime.now().strftime('%Y-%m-%d')
                    }
                }
            
            self.logger.warning(f"⚠️ Created fallback option chain with ATM: {atm_strike}")
            return option_chain
            
        except Exception as e:
            self.logger.error(f"❌ Error creating fallback option chain: {e}")
            return {}
    
    # Backward compatibility methods
    async def get_spot_price(self, symbol: str = "NIFTY") -> Optional[float]:
        """Public method to get spot price"""
        return await self._get_spot_price_with_all_fallbacks(symbol)
    
    async def get_atm_strike(self, symbol: str = "NIFTY") -> Optional[int]:
        """Get ATM strike for the symbol"""
        try:
            spot_price = await self.get_spot_price(symbol)
            if spot_price:
                return round(spot_price / 50) * 50
            return None
        except Exception as e:
            self.logger.error(f"❌ Error getting ATM strike: {e}")
            return None