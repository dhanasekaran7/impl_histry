#!/usr/bin/env python3
"""
QUICK TELEGRAM BOT TEST - Run this to immediately diagnose your 401 error
"""

import asyncio
import aiohttp
import json

async def quick_test_telegram():
    """Quick test of your Telegram bot"""
    
    # Your token from .env
    bot_token = "7325110708:AAHG74VGw_0ZXX9OTxGb4WioegHgzYsA6nE"
    chat_ids = ["5636009404", "-1002867661585"]
    
    print("=" * 50)
    print("TELEGRAM BOT 401 ERROR QUICK TEST")
    print("=" * 50)
    
    # Test 1: Validate token format
    print(f"\n1. TOKEN FORMAT CHECK:")
    print(f"   Token length: {len(bot_token)}")
    print(f"   Has colon: {':' in bot_token}")
    
    if ':' in bot_token:
        bot_id, hash_part = bot_token.split(':', 1)
        print(f"   Bot ID: {bot_id} ({'VALID' if bot_id.isdigit() else 'INVALID'})")
        print(f"   Hash length: {len(hash_part)} ({'VALID' if len(hash_part) == 35 else 'INVALID'})")
    
    # Test 2: Authentication test
    print(f"\n2. AUTHENTICATION TEST:")
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                print(f"   HTTP Status: {response.status}")
                
                if response.status == 200:
                    bot_info = data.get('result', {})
                    print(f"   ✅ SUCCESS! Bot authenticated")
                    print(f"   Bot Name: {bot_info.get('first_name')}")
                    print(f"   Username: @{bot_info.get('username')}")
                    
                elif response.status == 401:
                    print(f"   ❌ 401 UNAUTHORIZED")
                    print(f"   Error: {data.get('description', 'Token invalid')}")
                    print(f"\n   🔧 IMMEDIATE FIXES NEEDED:")
                    print(f"   1. Go to @BotFather in Telegram")
                    print(f"   2. Send: /mybots")
                    print(f"   3. Select your bot")
                    print(f"   4. Generate new token")
                    print(f"   5. Replace token in .env file")
                    return
                    
                else:
                    print(f"   ❌ ERROR: {response.status}")
                    print(f"   Response: {data}")
                    return
                    
    except Exception as e:
        print(f"   ❌ NETWORK ERROR: {e}")
        return
    
    # Test 3: Chat access test
    print(f"\n3. CHAT ACCESS TEST:")
    
    for chat_id in chat_ids:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getChat"
            params = {'chat_id': chat_id}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    
                    if response.status == 200:
                        chat_info = data.get('result', {})
                        print(f"   ✅ Chat {chat_id}: Accessible")
                        print(f"      Type: {chat_info.get('type', 'unknown')}")
                        if 'title' in chat_info:
                            print(f"      Title: {chat_info['title']}")
                        
                    elif response.status == 400:
                        print(f"   ❌ Chat {chat_id}: Not found")
                        print(f"      Fix: Send /start to bot (for private)")
                        print(f"      Fix: Add bot to group (for groups)")
                        
                    elif response.status == 403:
                        print(f"   ❌ Chat {chat_id}: Access denied")
                        print(f"      Fix: Unblock bot or re-add to group")
                        
                    else:
                        print(f"   ❌ Chat {chat_id}: Error {response.status}")
                        print(f"      {data.get('description', 'Unknown error')}")
                        
        except Exception as e:
            print(f"   ❌ Chat {chat_id}: Network error - {e}")
    
    # Test 4: Send test message
    print(f"\n4. SEND TEST MESSAGE:")
    
    test_message = f"🔧 Bot connection test - {asyncio.get_event_loop().time()}"
    
    for chat_id in chat_ids:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': test_message
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        print(f"   ✅ Message sent to {chat_id}")
                    else:
                        print(f"   ❌ Failed to send to {chat_id}: {response.status}")
                        print(f"      Error: {response_data.get('description', 'Unknown')}")
                        
        except Exception as e:
            print(f"   ❌ Send error to {chat_id}: {e}")
    
    print(f"\n" + "=" * 50)
    print("TEST COMPLETED")
    print("=" * 50)

# IMMEDIATE ACTION STEPS
def print_fix_steps():
    """Print immediate fix steps"""
    print(f"""
IMMEDIATE 401 FIX STEPS:
========================

If you got 401 Unauthorized above:

1. Open Telegram app on your phone
2. Search for: @BotFather
3. Send: /mybots
4. Click on your bot name
5. Click "API Token"
6. Click "Revoke current token" 
7. Copy the NEW token (it will look like: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ123456789)
8. Update your .env file:
   TELEGRAM_BOT_TOKEN=YOUR_NEW_TOKEN_HERE
9. Save the file
10. Restart your bot

For chat access issues:
- Private chat: Send /start to your bot first
- Group chat: Add your bot to the group as member
- Check that bot isn't blocked

Run this test again after fixing!
""")

if __name__ == "__main__":
    # Run the quick test
    asyncio.run(quick_test_telegram())
    print_fix_steps()