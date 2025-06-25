#!/usr/bin/env python3
"""
Conservative Zillow sync that respects Slack rate limits
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

async def conservative_zillow_sync():
    """Conservative sync for #fern-zillow with heavy rate limiting"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        from datetime import datetime, timedelta
        
        logger.info("🐌 Conservative #fern-zillow sync with heavy rate limiting...")
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Find the #fern-zillow channel
        print("🔍 Finding #fern-zillow channel...")
        
        # We know it exists from previous run
        zillow_channel_id = "C08T73FB06B"  # From previous successful discovery
        channel_name = "fern-zillow"
        
        print(f"🎯 Using known channel: #{channel_name} (ID: {zillow_channel_id})")
        
        # VERY CONSERVATIVE SETTINGS to avoid rate limits
        max_pages = 5  # Start small
        messages_per_page = 20  # Much smaller batches  
        days_back = 90  # 3 months instead of 2 years
        min_message_length = 1
        wait_between_pages = 10  # 10 seconds between pages
        
        print(f"🐌 CONSERVATIVE SETTINGS:")
        print(f"   - Pages: {max_pages} (up to {max_pages * messages_per_page} messages)")
        print(f"   - Batch size: {messages_per_page} messages")
        print(f"   - History: {days_back} days")
        print(f"   - Wait between pages: {wait_between_pages} seconds")
        
        # Calculate oldest timestamp
        oldest = datetime.now() - timedelta(days=days_back)
        oldest_ts = oldest.timestamp()
        
        all_messages = []
        cursor = None
        page_count = 0
        
        print(f"\n📄 Starting conservative message retrieval...")
        
        while page_count < max_pages:
            page_count += 1
            
            # HEAVY rate limiting
            print(f"   ⏳ Waiting {wait_between_pages} seconds before page {page_count}...")
            time.sleep(wait_between_pages)
            
            try:
                params = {
                    'channel': zillow_channel_id,
                    'limit': messages_per_page,
                    'oldest': str(oldest_ts)
                }
                if cursor:
                    params['cursor'] = cursor
                
                print(f"   📥 Requesting page {page_count}...")
                history_response = slack_client.conversations_history(**params)
                
                if not history_response.get('ok'):
                    error = history_response.get('error')
                    if error == 'ratelimited':
                        print(f"   ⏳ Still rate limited, waiting 60s...")
                        time.sleep(60)
                        continue
                    else:
                        print(f"   ❌ Error: {error}")
                        break
                
                page_messages = history_response.get('messages', [])
                all_messages.extend(page_messages)
                
                print(f"   ✅ Page {page_count}: {len(page_messages)} messages (total: {len(all_messages)})")
                
                # Check pagination
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    print(f"   🏁 Retrieved all available messages")
                    break
                    
            except Exception as e:
                print(f"   ❌ Error getting page {page_count}: {e}")
                print(f"   ⏳ Waiting 30s before retrying...")
                time.sleep(30)
                page_count -= 1  # Retry this page
                continue
        
        print(f"\n📊 RETRIEVED: {len(all_messages)} total messages from #{channel_name}")
        
        if len(all_messages) == 0:
            print("❌ No messages retrieved. Possible causes:")
            print("   - Channel is empty")
            print("   - Rate limits too aggressive") 
            print("   - Permission issues")
            return False
        
        # Process messages with minimal filtering
        indexed_count = 0
        filtered_out = 0
        
        print(f"📝 Processing {len(all_messages)} messages...")
        
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
                
                # Index messages
                user_id = message.get('user')
                user_name = f"User-{user_id}" if user_id else 'Unknown User'
                
                metadata = {
                    "channel_id": zillow_channel_id,
                    "channel_name": channel_name,
                    "user_id": user_id,
                    "user_name": user_name,
                    "ts": message.get('ts'),
                    "thread_ts": message.get('thread_ts'),
                    "indexed_from": "conservative_zillow_sync"
                }
                
                success = service.embedding_service.add_slack_message(
                    message_id=message.get('ts'),
                    content=text,
                    metadata=metadata
                )
                
                if success:
                    indexed_count += 1
                    
                    # Show first few messages for verification
                    if indexed_count <= 3:
                        print(f"   ✅ Message {indexed_count}: {text[:80]}...")
                
                # Add small delay between embeddings to avoid OpenAI rate limits
                if indexed_count % 5 == 0:
                    time.sleep(1)
                
            except Exception as e:
                print(f"   ⚠️ Error processing message: {e}")
                continue
        
        print(f"\n🎉 CONSERVATIVE SYNC COMPLETED!")
        print(f"📊 Indexed {indexed_count} messages from #{channel_name}")
        print(f"🗑️ Filtered out {filtered_out} messages")
        
        # Test Zillow search with new data
        if indexed_count > 0:
            print(f"\n🔍 Testing Zillow search with new data...")
            results = service.embedding_service.search_similar_content(
                query="Zillow",
                n_results=5,
                source_filter="slack"
            )
            
            print(f"📊 Found {len(results)} Slack results for Zillow:")
            for i, result in enumerate(results):
                metadata = result.get('metadata', {})
                content = result.get('content', '')
                print(f"\n   Result {i+1} from #{metadata.get('channel_name', 'unknown')}:")
                print(f"   {content[:150]}...")
        
        return indexed_count > 0
        
    except Exception as e:
        logger.error(f"❌ Conservative sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🐌 CONSERVATIVE ZILLOW CHANNEL SYNC")
    print("This uses heavy rate limiting to work within Slack's limits")
    print("Settings: 5 pages, 20 messages/page, 10s delays, 3 months history")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    success = asyncio.run(conservative_zillow_sync())
    if success:
        print("\n✅ SUCCESS! Zillow data has been indexed.")
        print("Try asking your bot about Zillow again!")
    else:
        print("\n❌ FAILED! Check the logs above.")
    
    sys.exit(0 if success else 1) 