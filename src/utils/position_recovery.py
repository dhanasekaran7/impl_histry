import logging
from datetime import datetime
from typing import List, Dict, Optional

class PositionRecoveryManager:
    """Recover lost positions from Upstox account"""
    
    def __init__(self, upstox_client):
        self.upstox_client = upstox_client
        self.logger = logging.getLogger(__name__)
    
    async def recover_all_option_positions(self) -> List[Dict]:
        """Recover all open option positions from Upstox"""
        try:
            self.logger.info("Starting position recovery from Upstox account...")
            
            # Get positions from Upstox API
            positions_response = await self.upstox_client.get_positions()
            
            if not positions_response or 'data' not in positions_response:
                self.logger.warning("No position data received from Upstox")
                return []
            
            positions = positions_response['data']
            recovered_positions = []
            
            for position in positions:
                try:
                    # Filter for NIFTY options with non-zero quantity
                    instrument_key = position.get('instrument_key', '')
                    quantity = int(position.get('quantity', 0))
                    
                    if 'NIFTY' in instrument_key and quantity != 0:
                        # Parse option details
                        position_data = self._parse_option_position(position)
                        if position_data:
                            recovered_positions.append(position_data)
                            self.logger.info(f"Recovered: {position_data['symbol']} - {quantity} qty")
                
                except Exception as e:
                    self.logger.debug(f"Error parsing position: {e}")
                    continue
            
            self.logger.info(f"Successfully recovered {len(recovered_positions)} option positions")
            return recovered_positions
            
        except Exception as e:
            self.logger.error(f"Error in position recovery: {e}")
            return []
    
    def _parse_option_position(self, position: Dict) -> Optional[Dict]:
        """Parse Upstox position data into our format"""
        try:
            instrument_key = position.get('instrument_key', '')
            symbol = position.get('trading_symbol', '')
            quantity = int(position.get('quantity', 0))
            average_price = float(position.get('average_price', 0))
            
            if quantity == 0 or average_price <= 0:
                return None
            
            # Extract option details from symbol (e.g., NIFTY25SEP24750CE)
            option_type = 'CE' if symbol.endswith('CE') else 'PE'
            
            # Extract strike price (rough parsing)
            import re
            strike_match = re.search(r'(\d{5})(CE|PE)$', symbol)
            strike_price = int(strike_match.group(1)) if strike_match else 0
            
            # Extract expiry
            expiry_match = re.search(r'NIFTY(\d{2}[A-Z]{3})', symbol)
            expiry = expiry_match.group(1) if expiry_match else '25SEP'
            
            return {
                'symbol': symbol,
                'instrument_key': instrument_key,
                'strike_price': strike_price,
                'option_type': option_type,
                'quantity': quantity,
                'entry_premium': average_price,
                'expiry_date': expiry,
                'entry_time': datetime.now(),  # Approximate
                'recovered': True
            }
            
        except Exception as e:
            self.logger.debug(f"Error parsing position data: {e}")
            return None