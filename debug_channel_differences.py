#!/usr/bin/env python3
"""
Debug script to investigate why different channels are getting different amounts of data
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def debug_channel_differences():
    """Debug why some channels are getting more data than others"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("🔍 DEBUGGING CHANNEL SYNC DIFFERENCES")
        print("=" * 60)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Test specific channels with detailed analysis
        test_channels = [
            'fern-zillow',
            'fern-elevenlabs', 
            'fern-deno',
            'fern-box'
        ]
        
        print("1️⃣ Checking current indexed data for test channels...")
        all_messages = service.embedding_service.search_similar_content(
            query="message",
            n_results=200,
            source_filter="slack"
        )
        
        # Group by channel
        channel_data = {}
        for message in all_messages:
            metadata = message.get('metadata', {})
            channel_name = metadata.get('channel_name')
            if channel_name in test_channels:
                if channel_name not in channel_data:
                    channel_data[channel_name] = []
                channel_data[channel_name].append(message)
        
        print("\n📊 Current indexed data:")
        for channel in test_channels:
            count = len(channel_data.get(channel, []))
            print(f"   #{channel}: {count} messages indexed")
        
        # Now let's check what's actually available in Slack for these channels
        print("\n2️⃣ Checking actual Slack data availability...")
        
        # Find channel IDs
        channels_response = slack_client.conversations_list(
            types='public_channel',
            limit=200
        )
        
        channel_id_map = {}
        if channels_response.get('ok'):
            for channel in channels_response.get('channels', []):
                channel_name = channel.get('name')
                if channel_name in test_channels:
                    channel_id_map[channel_name] = channel['id']
        
        print(f"   Found channel IDs for: {list(channel_id_map.keys())}")
        
        # Test each channel with the same settings as our comprehensive sync
        for channel_name, channel_id in channel_id_map.items():
            print(f"\n--- Testing #{channel_name} (ID: {channel_id}) ---")
            
            try:
                # Use same settings as comprehensive sync for company channels
                time.sleep(3)  # Rate limiting
                
                # Test with recent data first (last 7 days)
                from datetime import datetime, timedelta
                recent_oldest = datetime.now() - timedelta(days=7)
                recent_oldest_ts = recent_oldest.timestamp()
                
                params = {
                    'channel': channel_id,
                    'limit': 50,
                    'oldest': str(recent_oldest_ts)
                }
                
                print(f"   🔍 Checking last 7 days with limit 50...")
                history_response = slack_client.conversations_history(**params)
                
                if not history_response.get('ok'):
                    error = history_response.get('error')
                    print(f"   ❌ Error: {error}")
                    continue
                
                recent_messages = history_response.get('messages', [])
                print(f"   📊 Last 7 days: {len(recent_messages)} messages available")
                
                # Show sample message details
                if recent_messages:
                    print(f"   📄 Sample recent messages:")
                    for i, msg in enumerate(recent_messages[:3]):
                        text = msg.get('text', '')[:60]
                        ts = msg.get('ts', '')
                        user = msg.get('user', 'unknown')
                        subtype = msg.get('subtype')
                        bot_id = msg.get('bot_id')
                        
                        print(f"     {i+1}. {text}... (user: {user}, subtype: {subtype}, bot: {bool(bot_id)})")
                
                # Now test with our comprehensive sync settings (365 days for company channels)
                print(f"   🔍 Checking full year with comprehensive sync settings...")
                
                full_oldest = datetime.now() - timedelta(days=365)
                full_oldest_ts = full_oldest.timestamp()
                
                params = {
                    'channel': channel_id,
                    'limit': 50,
                    'oldest': str(full_oldest_ts)
                }
                
                time.sleep(3)
                full_history_response = slack_client.conversations_history(**params)
                
                if full_history_response.get('ok'):
                    full_messages = full_history_response.get('messages', [])
                    print(f"   📊 Full year: {len(full_messages)} messages available")
                    
                    # Count messages that would pass our filters
                    valid_messages = 0
                    for msg in full_messages:
                        if not msg.get('bot_id') and msg.get('subtype') not in ['channel_join', 'channel_leave']:
                            text = msg.get('text', '')
                            if len(text) >= 1:  # Company channel minimum length
                                valid_messages += 1
                    
                    print(f"   ✅ Messages that would pass filters: {valid_messages}")
                    
                    # Compare with what we actually indexed
                    indexed_count = len(channel_data.get(channel_name, []))
                    print(f"   📊 Currently indexed: {indexed_count}")
                    print(f"   📈 Potential improvement: {valid_messages - indexed_count} more messages")
                
            except Exception as e:
                print(f"   ❌ Error testing {channel_name}: {e}")
        
        print(f"\n3️⃣ Diagnosis and Recommendations...")
        
        # Check if the issue is in our sync logic
        print(f"\n💡 POTENTIAL ISSUES IDENTIFIED:")
        print(f"   1. Rate limiting might be too aggressive")
        print(f"   2. Pagination might not be working correctly")
        print(f"   3. Different indexing approaches between channels")
        print(f"   4. Time range filtering might be too restrictive")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(debug_channel_differences())
    sys.exit(0 if success else 1) 