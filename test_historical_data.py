# Create this file: test_historical_data.py

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

async def test_historical_data_preloader():
    """Test the historical data preloader"""
    
    print("🧪 TESTING HISTORICAL DATA PRELOADER")
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
            print("✅ Access token loaded")
            
            if await client.test_token():
                print("✅ Token is valid")
                
                # Test historical data API
                print("\n🔄 Testing historical data API...")
                
                from datetime import timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=2)
                
                url = f"{client.base_url}/historical-candle/NSE_INDEX%7CNifty%2050/1minute/{end_date.strftime('%Y-%m-%d')}/{start_date.strftime('%Y-%m-%d')}"
                
                headers = {
                    'Authorization': f'Bearer {client.access_token}',
                    'Accept': 'application/json'
                }
                
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get('status') == 'success':
                                candles = data.get('data', {}).get('candles', [])
                                
                                print(f"✅ Historical API working!")
                                print(f"   📊 Downloaded: {len(candles)} candles")
                                print(f"   📅 Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
                                
                                if len(candles) >= 30:
                                    print("✅ Enough data for quick start!")
                                    return True
                                else:
                                    print("⚠️ Limited data available")
                                    return False
                            else:
                                print(f"❌ API error: {data}")
                                return False
                        else:
                            print(f"❌ HTTP error: {response.status}")
                            return False
            else:
                print("❌ Token is invalid")
                return False
        else:
            print("❌ No stored token found")
            print("💡 Run authentication first")
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_historical_data_preloader())
    
    if result:
        print("\n🎉 Historical data preloader ready!")
        print("🎯 You can now implement Step 5 in main.py")
    else:
        print("\n⚠️ Historical data preloader has issues")
        print("💡 Check your authentication and API access")