#!/usr/bin/env python3
"""
IMMEDIATE TEST FOR YOUR NEW BOT: trailupstox_bot
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_new_bot():
    """Test your new Telegram bot immediately"""
    
    # NEW BOT CREDENTIALS
    bot_token = "7650079003:AAFVmnP3VNojVYdmT4s1-XpFhcHPF7AOQFQ"
    chat_ids = ["5636009404", "-1002867661585"]  # Your chat IDs
    bot_username = "trailupstox_bot"
    
    print("=" * 60)
    print(f"TESTING NEW BOT: @{bot_username}")
    print("=" * 60)
    
    # Test 1: Bot Authentication
    print("\n1. AUTHENTICATION TEST:")
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                print(f"   HTTP Status: {response.status}")
                
                if response.status == 200 and data.get('ok'):
                    bot_info = data['result']
                    print(f"   ✅ SUCCESS! Bot is working")
                    print(f"   Bot ID: {bot_info['id']}")
                    print(f"   Bot Name: {bot_info['first_name']}")
                    print(f"   Username: @{bot_info['username']}")
                    print(f"   Can Join Groups: {bot_info.get('can_join_groups', False)}")
                    print(f"   Can Read Messages: {bot_info.get('can_read_all_group_messages', False)}")
                    
                else:
                    print(f"   ❌ FAILED: {response.status}")
                    print(f"   Error: {data}")
                    return False
                    
    except Exception as e:
        print(f"   ❌ NETWORK ERROR: {e}")
        return False
    
    # Test 2: Chat Access (before sending messages)
    print(f"\n2. CHAT PREPARATION:")
    print(f"   IMPORTANT: You need to prepare your chats first!")
    
    for chat_id in chat_ids:
        if chat_id.startswith('-'):
            print(f"   • Group/Channel {chat_id}: Add @{bot_username} as member")
        else:
            print(f"   • Private chat {chat_id}: Send /start to @{bot_username}")
    
    print(f"\n   📱 DO THIS NOW:")
    print(f"   1. Open Telegram app")
    print(f"   2. Search: @{bot_username}")
    print(f"   3. Send: /start")
    print(f"   4. For groups: Add bot as member")
    print(f"\n   Press Enter when ready...")
    input()
    
    # Test 3: Send Test Messages
    print(f"\n3. SENDING TEST MESSAGES:")
    
    test_message = f"""🔧 NEW BOT TEST - {datetime.now().strftime('%H:%M:%S')}

✅ Bot: @{bot_username} 
🔗 Token: Working
📊 Status: Ready for trading notifications

This is a test message from your new trading bot!"""
    
    success_count = 0
    
    for chat_id in chat_ids:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': test_message,
                'parse_mode': 'HTML'  # Try HTML first
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        print(f"   ✅ Message sent to chat {chat_id}")
                        success_count += 1
                        
                    elif response.status == 400:
                        print(f"   ❌ Chat {chat_id}: {response_data.get('description', 'Bad request')}")
                        
                        # Try without formatting
                        plain_message = "NEW BOT TEST - Bot is working and ready!"
                        data_plain = {'chat_id': chat_id, 'text': plain_message}
                        
                        async with session.post(url, json=data_plain) as retry_response:
                            if retry_response.status == 200:
                                print(f"   ✅ Plain message sent to chat {chat_id}")
                                success_count += 1
                            else:
                                retry_data = await retry_response.json()
                                print(f"   ❌ Retry failed: {retry_data.get('description')}")
                                
                    elif response.status == 403:
                        print(f"   ❌ Chat {chat_id}: Bot blocked or no access")
                        print(f"      Fix: Send /start to bot or add to group")
                        
                    else:
                        print(f"   ❌ Chat {chat_id}: HTTP {response.status}")
                        print(f"      Error: {response_data.get('description', 'Unknown')}")
                        
        except Exception as e:
            print(f"   ❌ Chat {chat_id}: Network error - {e}")
    
    # Test 4: Summary
    print(f"\n4. TEST SUMMARY:")
    print(f"   Bot Authentication: ✅ Working")
    print(f"   Messages Sent: {success_count}/{len(chat_ids)}")
    
    if success_count == len(chat_ids):
        print(f"   🎉 ALL TESTS PASSED!")
        print(f"   Your new bot is ready to use")
        
        # Update .env reminder
        print(f"\n5. UPDATE YOUR .ENV FILE:")
        print(f"   Replace this line:")
        print(f"   TELEGRAM_BOT_TOKEN=7650079003:AAFVmnP3VNojVYdmT4s1-XpFhcHPF7AOQFQ")
        print(f"\n   Restart your trading bot application")
        
        return True
        
    elif success_count > 0:
        print(f"   ⚠️  PARTIAL SUCCESS")
        print(f"   Some chats need attention (see errors above)")
        return True
        
    else:
        print(f"   ❌ ALL TESTS FAILED")
        print(f"   Check chat preparation steps above")
        return False

# Quick fix for common issues
async def quick_chat_setup_test():
    """Test individual chat setup"""
    
    bot_token = "7650079003:AAFVmnP3VNojVYdmT4s1-XpFhcHPF7AOQFQ"
    
    print("\nTESTING CHAT SETUP:")
    print("=" * 30)
    
    # Test private chat
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                if response.status == 200 and data.get('result'):
                    updates = data['result']
                    print(f"Found {len(updates)} recent messages")
                    
                    for update in updates[-3:]:  # Show last 3 updates
                        if 'message' in update:
                            msg = update['message']
                            chat_id = msg['chat']['id']
                            chat_type = msg['chat']['type']
                            text = msg.get('text', 'N/A')[:30]
                            
                            print(f"   Chat {chat_id} ({chat_type}): {text}...")
                            
                else:
                    print("No recent updates found")
                    print("Send /start to your bot first!")
                    
    except Exception as e:
        print(f"Error checking updates: {e}")

if __name__ == "__main__":
    print("STEP 1: Testing new bot functionality...")
    asyncio.run(test_new_bot())
    
    print("\nSTEP 2: Checking recent chat activity...")
    asyncio.run(quick_chat_setup_test())
    
    print(f"""

NEXT STEPS:
==========

1. ✅ Update your .env file with the new token
2. 🔄 Restart your trading bot application  
3. 📱 Check Telegram for test messages
4. 🚀 Your bot should now work without 401 errors!

New Bot Details:
- Name: tradingbot_dhana
- Username: @trailupstox_bot
- Token: 7650079003:AAFVmnP3VNojVYdmT4s1-XpFhcHPF7AOQFQ
""")