# ==================== FIXED HISTORICAL DATA TEST ====================
# Save as: test_historical_data_fixed.py

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

def get_last_trading_days(days_back=10):
    """
    Get last trading days (exclude weekends)
    """
    trading_days = []
    current_date = datetime.now()
    
    # Go back day by day and find trading days (Monday=0, Sunday=6)
    days_checked = 0
    while len(trading_days) < days_back and days_checked < 20:
        check_date = current_date - timedelta(days=days_checked)
        
        # Skip weekends (Saturday=5, Sunday=6)
        if check_date.weekday() < 5:  # Monday to Friday
            trading_days.append(check_date)
        
        days_checked += 1
    
    return trading_days

async def test_historical_data_fixed():
    """Test with proper trading days"""
    
    print("TESTING HISTORICAL DATA WITH TRADING DAYS")
    print("=" * 50)
    
    try:
        from config.settings import get_settings
        from src.upstox_api_client import UpstoxClient
        
        # Setup
        settings = get_settings()
        client = UpstoxClient(
            settings.upstox_api_key,
            settings.upstox_api_secret,
            settings.upstox_redirect_uri
        )
        
        # Test if we can load stored token
        if client.load_stored_token():
            print("Access token loaded")
            
            if await client.test_token():
                print("Token is valid")
                
                # Get last trading days
                trading_days = get_last_trading_days(5)
                
                print(f"\nLast 5 trading days:")
                for i, day in enumerate(trading_days):
                    weekday = day.strftime('%A')
                    print(f"  {i+1}. {day.strftime('%Y-%m-%d')} ({weekday})")
                
                # Test with different date ranges
                test_cases = [
                    {
                        'name': 'Last 2 trading days',
                        'start_date': trading_days[1],  # 2nd last trading day
                        'end_date': trading_days[0]     # Last trading day
                    },
                    {
                        'name': 'Last 5 trading days', 
                        'start_date': trading_days[4],  # 5th last trading day
                        'end_date': trading_days[0]     # Last trading day
                    },
                    {
                        'name': 'Last Friday only',
                        'start_date': trading_days[0],  # Last trading day
                        'end_date': trading_days[0]     # Same day
                    }
                ]
                
                best_result = None
                
                for test_case in test_cases:
                    print(f"\nTesting: {test_case['name']}")
                    print(f"Date range: {test_case['start_date'].strftime('%Y-%m-%d')} to {test_case['end_date'].strftime('%Y-%m-%d')}")
                    
                    # Build API URL
                    instrument_key = "NSE_INDEX%7CNifty%2050"
                    interval = "1minute"
                    to_date = test_case['end_date'].strftime('%Y-%m-%d')
                    from_date = test_case['start_date'].strftime('%Y-%m-%d')
                    
                    url = f"{client.base_url}/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
                    
                    headers = {
                        'Authorization': f'Bearer {client.access_token}',
                        'Accept': 'application/json'
                    }
                    
                    # Wait for rate limiting
                    await client.rate_limiter.wait_if_needed()
                    
                    import aiohttp
                    timeout = aiohttp.ClientTimeout(total=30)
                    
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                if data.get('status') == 'success':
                                    candles = data.get('data', {}).get('candles', [])
                                    
                                    print(f"  Result: {len(candles)} candles")
                                    
                                    if len(candles) > 0:
                                        # Show sample data
                                        sample_candle = candles[0]
                                        timestamp = datetime.fromtimestamp(sample_candle[0] / 1000)
                                        print(f"  Sample: {timestamp} - O:{sample_candle[1]}, H:{sample_candle[2]}, L:{sample_candle[3]}, C:{sample_candle[4]}")
                                        
                                        if not best_result or len(candles) > best_result['count']:
                                            best_result = {
                                                'name': test_case['name'],
                                                'count': len(candles),
                                                'start_date': test_case['start_date'],
                                                'end_date': test_case['end_date']
                                            }
                                    else:
                                        print("  Result: No candles found")
                                else:
                                    print(f"  API Error: {data.get('message', 'Unknown error')}")
                            else:
                                error_text = await response.text()
                                print(f"  HTTP Error: {response.status} - {error_text[:200]}...")
                
                # Summary
                print("\n" + "=" * 50)
                print("HISTORICAL DATA AVAILABILITY SUMMARY")
                print("=" * 50)
                
                if best_result:
                    print(f"Best result: {best_result['name']}")
                    print(f"Candles available: {best_result['count']}")
                    print(f"Date range: {best_result['start_date'].strftime('%Y-%m-%d')} to {best_result['end_date'].strftime('%Y-%m-%d')}")
                    
                    if best_result['count'] >= 30:
                        print("QUICK START: Possible - enough data available")
                        return True
                    else:
                        print("QUICK START: Limited - may need to collect live data")
                        return False
                else:
                    print("No historical data available")
                    print("QUICK START: Not possible - must collect live data")
                    return False
                    
            else:
                print("Token is invalid")
                return False
        else:
            print("No stored token found")
            return False
            
    except Exception as e:
        print(f"Test error: {e}")
        return False

# Additional test for maximum available history
async def test_maximum_history():
    """Test maximum available history (30 days)"""
    
    print("\nTESTING MAXIMUM AVAILABLE HISTORY")
    print("=" * 40)
    
    try:
        from config.settings import get_settings
        from src.upstox_api_client import UpstoxClient
        
        settings = get_settings()
        client = UpstoxClient(settings.upstox_api_key, settings.upstox_api_secret, settings.upstox_redirect_uri)
        
        if client.load_stored_token() and await client.test_token():
            
            # Test different periods
            test_periods = [7, 15, 30]  # 1 week, 2 weeks, 1 month
            
            for days in test_periods:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                print(f"\nTesting {days} days back ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}):")
                
                url = f"{client.base_url}/historical-candle/NSE_INDEX%7CNifty%2050/1minute/{end_date.strftime('%Y-%m-%d')}/{start_date.strftime('%Y-%m-%d')}"
                
                headers = {
                    'Authorization': f'Bearer {client.access_token}',
                    'Accept': 'application/json'
                }
                
                await client.rate_limiter.wait_if_needed()
                
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get('status') == 'success':
                                candles = data.get('data', {}).get('candles', [])
                                print(f"  Available: {len(candles)} candles")
                                
                                if len(candles) > 0:
                                    first_candle = candles[0]
                                    last_candle = candles[-1]
                                    first_time = datetime.fromtimestamp(first_candle[0] / 1000)
                                    last_time = datetime.fromtimestamp(last_candle[0] / 1000)
                                    print(f"  Range: {first_time.strftime('%Y-%m-%d %H:%M')} to {last_time.strftime('%Y-%m-%d %H:%M')}")
                            else:
                                print(f"  Error: {data.get('message', 'API error')}")
                        else:
                            print(f"  HTTP Error: {response.status}")
        
    except Exception as e:
        print(f"Maximum history test error: {e}")

if __name__ == "__main__":
    print(f"Current time: {datetime.now().strftime('%A, %Y-%m-%d %H:%M:%S')}")
    print("Note: Markets are closed on weekends and holidays\n")
    
    result = asyncio.run(test_historical_data_fixed())
    
    # Test maximum available history
    asyncio.run(test_maximum_history())
    
    if result:
        print("\nHistorical data preloader ready for implementation!")
    else:
        print("\nHistorical data has limitations - quick start may not work optimally")
        print("Recommendation: Use live data collection for now")