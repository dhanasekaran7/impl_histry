# Save as: diagnose_step5.py

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

async def diagnose_step5_issue():
    """Quick diagnostic to find Step 5 issue"""
    
    print("🔍 DIAGNOSING STEP 5 ISSUE")
    print("=" * 40)
    
    try:
        from config.settings import get_settings
        from src.upstox_api_client import UpstoxClient
        
        settings = get_settings()
        client = UpstoxClient(
            settings.upstox_api_key,
            settings.upstox_api_secret,
            settings.upstox_redirect_uri
        )
        
        if client.load_stored_token() and await client.test_token():
            
            # Test the exact API call from your logs
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
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
                            raw_candles = data.get('data', {}).get('candles', [])
                            print(f"✅ API Call: {len(raw_candles)} candles downloaded")
                            
                            if raw_candles:
                                # Test first few candles
                                print(f"\n📊 Sample data analysis:")
                                for i in range(min(3, len(raw_candles))):
                                    candle = raw_candles[i]
                                    print(f"  Candle {i}: {candle}")
                                    print(f"    Timestamp type: {type(candle[0])}")
                                    print(f"    Values: O:{candle[1]} H:{candle[2]} L:{candle[3]} C:{candle[4]}")
                                
                                return True
                    
                    print(f"❌ API Error: {response.status}")
                    return False
        
        print("❌ Authentication failed")
        return False
        
    except Exception as e:
        print(f"❌ Diagnostic error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(diagnose_step5_issue())