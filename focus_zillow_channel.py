#!/usr/bin/env python3
"""
Focus on #fern-zillow channel only with maximum aggressive settings
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

async def focus_zillow_sync():
    """Focus specifically on #fern-zillow channel with maximum data collection"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        from datetime import datetime, timedelta
        
        logger.info("🎯 Focusing on #fern-zillow channel...")
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Find the #fern-zillow channel
        print("🔍 Searching specifically for #fern-zillow channel...")
        
        cursor = None
        zillow_channel = None
        
        while True:
            time.sleep(2)  # Rate limiting
            params = {
                'types': 'public_channel',  # Only public channels - we don't have groups:read scope
                'limit': 200,
                'exclude_archived': False
            }
            if cursor:
                params['cursor'] = cursor
            
            channels_response = slack_client.conversations_list(**params)
            
            if not channels_response.get('ok'):
                logger.error(f"Failed to get channels: {channels_response.get('error')}")
                break
            
            channels = channels_response.get('channels', [])
            
            # Look for Zillow channel
            for channel in channels:
                channel_name = channel.get('name', '').lower()
                if 'zillow' in channel_name:
                    print(f"🎯 FOUND: #{channel['name']} (ID: {channel['id']})")
                    zillow_channel = channel
                    break
            
            if zillow_channel:
                break
            
            cursor = channels_response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
        
        if not zillow_channel:
            print("❌ Could not find any Zillow-related channels!")
            print("Available channels might include:")
            # Show first few channels for debugging
            params = {'types': 'public_channel', 'limit': 10}
            channels_response = slack_client.conversations_list(**params)
            if channels_response.get('ok'):
                for channel in channels_response.get('channels', [])[:10]:
                    print(f"   - #{channel.get('name')}")
            return False
        
        channel_id = zillow_channel['id']
        channel_name = zillow_channel['name']
        is_archived = zillow_channel.get('is_archived', False)
        is_member = zillow_channel.get('is_member', False)
        
        print(f"\n🎯 PROCESSING: #{channel_name}")
        print(f"   Channel ID: {channel_id}")
        print(f"   Archived: {is_archived}")
        print(f"   Member: {is_member}")
        
        # Try to join if not a member
        if not is_member and not is_archived:
            try:
                join_response = slack_client.conversations_join(channel=channel_id)
                if join_response.get('ok'):
                    print("   ✅ Successfully joined channel")
                else:
                    print(f"   ❌ Could not join: {join_response.get('error')}")
                    if join_response.get('error') != 'already_in_channel':
                        return False
            except Exception as e:
                print(f"   ❌ Error joining: {e}")
                return False
        
        # MAXIMUM AGGRESSIVE SETTINGS for Zillow
        max_pages = 50  # Up to 50 pages 
        messages_per_page = 200  # Maximum allowed by Slack
        days_back = 730  # 2 years of history
        min_message_length = 1  # Index almost everything
        
        print(f"   🚀 MAXIMUM AGGRESSIVE SETTINGS:")
        print(f"   - Pages: {max_pages} (up to {max_pages * messages_per_page:,} messages)")
        print(f"   - History: {days_back} days")
        print(f"   - Min length: {min_message_length} characters")
        
        # Calculate oldest timestamp
        oldest = datetime.now() - timedelta(days=days_back)
        oldest_ts = oldest.timestamp()
        
        all_messages = []
        cursor = None
        page_count = 0
        
        print(f"\n📄 Starting message retrieval...")
        
        while page_count < max_pages:
            page_count += 1
            
            # Minimal rate limiting for focused sync
            time.sleep(0.5)
            
            try:
                params = {
                    'channel': channel_id,
                    'limit': messages_per_page,
                    'oldest': str(oldest_ts)
                }
                if cursor:
                    params['cursor'] = cursor
                
                history_response = slack_client.conversations_history(**params)
                
                if not history_response.get('ok'):
                    error = history_response.get('error')
                    if error == 'ratelimited':
                        print(f"   ⏳ Rate limited, waiting 30s...")
                        time.sleep(30)
                        continue
                    else:
                        print(f"   ❌ Error: {error}")
                        break
                
                page_messages = history_response.get('messages', [])
                all_messages.extend(page_messages)
                
                print(f"   📄 Page {page_count}: {len(page_messages)} messages (total: {len(all_messages)})")
                
                # Check pagination
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    print(f"   ✅ Retrieved all available messages")
                    break
                    
            except Exception as e:
                print(f"   ❌ Error getting page {page_count}: {e}")
                break
        
        print(f"\n📊 RETRIEVED: {len(all_messages)} total messages from #{channel_name}")
        
        # Process messages with minimal filtering
        indexed_count = 0
        filtered_out = 0
        
        print(f"📝 Processing messages...")
        
        for i, message in enumerate(all_messages):
            try:
                # Ultra-minimal filtering
                if message.get('bot_id'):
                    filtered_out += 1
                    continue
                
                text = message.get('text', '')
                if len(text) < min_message_length:
                    filtered_out += 1
                    continue
                
                # Index ALL messages
                user_id = message.get('user')
                user_name = f"User-{user_id}" if user_id else 'Unknown User'
                
                metadata = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "user_id": user_id,
                    "user_name": user_name,
                    "ts": message.get('ts'),
                    "thread_ts": message.get('thread_ts'),
                    "indexed_from": "focus_zillow_sync"
                }
                
                success = service.embedding_service.add_slack_message(
                    message_id=message.get('ts'),
                    content=text,
                    metadata=metadata
                )
                
                if success:
                    indexed_count += 1
                    
                    # Show sample messages for verification
                    if indexed_count <= 5:
                        print(f"   ✅ Sample message {indexed_count}: {text[:100]}...")
                
                # Progress indicator
                if (i + 1) % 100 == 0:
                    print(f"   📝 Processed {i + 1}/{len(all_messages)} messages... (indexed: {indexed_count})")
                
            except Exception as e:
                print(f"   ⚠️ Error processing message: {e}")
                continue
        
        print(f"\n🎉 FOCUS SYNC COMPLETED!")
        print(f"📊 Indexed {indexed_count} messages from #{channel_name}")
        print(f"🗑️ Filtered out {filtered_out} messages")
        
        # Test Zillow search with new data
        if indexed_count > 0:
            print(f"\n🔍 Testing Zillow search with new data...")
            results = service.embedding_service.search_similar_content(
                query="Zillow",
                n_results=10,
                source_filter="slack"
            )
            
            print(f"📊 Found {len(results)} Slack results for Zillow:")
            for i, result in enumerate(results):
                metadata = result.get('metadata', {})
                content = result.get('content', '')
                print(f"\n   Result {i+1} from #{metadata.get('channel_name', 'unknown')}:")
                print(f"   {content[:200]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Focus sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🎯 FOCUS ZILLOW CHANNEL SYNC")
    print("This will aggressively sync ONLY the #fern-zillow channel")
    print("Maximum settings: 50 pages, 200 messages/page, 2 years history")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    success = asyncio.run(focus_zillow_sync())
    if success:
        print("\n✅ SUCCESS! Your Zillow data should now be properly indexed.")
        print("Try asking: 'What is the exact last slack message that was related to zillow'")
    else:
        print("\n❌ FAILED! Check the logs above for issues.")
    
    sys.exit(0 if success else 1) 