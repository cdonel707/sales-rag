#!/usr/bin/env python3
"""
Comprehensive Slack Sync Script
Gets ALL historical messages from ALL channels, especially targeting #fern-zillow
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

async def comprehensive_slack_sync():
    """Sync ALL Slack messages with much more aggressive settings"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        logger.info("🚀 Starting COMPREHENSIVE Slack sync...")
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Get ALL channels (not just 10)
        print("\n1️⃣ Discovering ALL Slack channels...")
        all_channels = []
        cursor = None
        
        while True:
            time.sleep(2)  # Rate limiting
            params = {
                'types': 'public_channel',  # Only public channels - we don't have groups:read scope
                'limit': 200,  # Maximum allowed
                'exclude_archived': False  # Include archived channels too
            }
            if cursor:
                params['cursor'] = cursor
            
            channels_response = slack_client.conversations_list(**params)
            
            if not channels_response.get('ok'):
                logger.error(f"Failed to get channels: {channels_response.get('error')}")
                break
            
            batch_channels = channels_response.get('channels', [])
            all_channels.extend(batch_channels)
            
            cursor = channels_response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
        
        print(f"📊 Found {len(all_channels)} total channels")
        
        # Find and prioritize the #fern-zillow channel
        zillow_channel = None
        priority_channels = []
        other_channels = []
        
        for channel in all_channels:
            channel_name = channel.get('name', '').lower()
            if 'zillow' in channel_name:
                print(f"🎯 FOUND ZILLOW CHANNEL: #{channel['name']}")
                if zillow_channel is None:
                    zillow_channel = channel
                priority_channels.append(channel)
            elif any(keyword in channel_name for keyword in ['sales', 'customer', 'deal', 'prospect']):
                priority_channels.append(channel)
            else:
                other_channels.append(channel)
        
        # Process channels in priority order
        channels_to_process = priority_channels + other_channels[:20]  # Limit to reasonable number
        
        print(f"\n2️⃣ Processing {len(channels_to_process)} channels (prioritizing Zillow and sales channels)")
        
        if zillow_channel:
            print(f"🎯 PRIORITIZING: #{zillow_channel['name']} (ID: {zillow_channel['id']})")
        
        total_indexed = 0
        
        for i, channel in enumerate(channels_to_process):
            channel_id = channel['id']
            channel_name = channel['name']
            is_archived = channel.get('is_archived', False)
            is_member = channel.get('is_member', False)
            
            print(f"\n--- Channel {i+1}/{len(channels_to_process)}: #{channel_name} ---")
            print(f"   Archived: {is_archived}, Member: {is_member}")
            
            # Skip archived channels unless it's the Zillow channel
            if is_archived and 'zillow' not in channel_name.lower():
                print("   ⏭️ Skipping archived channel")
                continue
            
            # Try to join channel if not a member
            if not is_member and not is_archived:
                try:
                    join_response = slack_client.conversations_join(channel=channel_id)
                    if join_response.get('ok'):
                        print("   ✅ Successfully joined channel")
                    else:
                        print(f"   ❌ Could not join: {join_response.get('error')}")
                        if join_response.get('error') != 'already_in_channel':
                            continue
                except Exception as e:
                    print(f"   ❌ Error joining: {e}")
                    continue
            
            # Get messages with MUCH more aggressive settings
            indexed_count = await comprehensive_channel_sync(
                service.embedding_service, 
                slack_client, 
                channel_id, 
                channel_name,
                is_zillow_channel='zillow' in channel_name.lower()
            )
            
            total_indexed += indexed_count
            print(f"   📝 Indexed {indexed_count} messages")
            
            # Shorter delay between channels for faster processing
            if i < len(channels_to_process) - 1:
                print("   ⏳ Waiting 10 seconds...")
                time.sleep(10)
        
        print(f"\n🎉 COMPREHENSIVE SYNC COMPLETED!")
        print(f"📊 Total indexed: {total_indexed} messages across {len(channels_to_process)} channels")
        
        # Test Zillow search again
        if total_indexed > 0:
            print(f"\n3️⃣ Testing Zillow search with new data...")
            results = service.embedding_service.search_similar_content(
                query="Zillow",
                n_results=5,
                source_filter="slack"
            )
            
            print(f"📊 Found {len(results)} Slack results for Zillow:")
            for i, result in enumerate(results):
                metadata = result.get('metadata', {})
                content = result.get('content', '')
                print(f"\n   Result {i+1} from #{metadata.get('channel_name', 'unknown')}: {content[:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Comprehensive sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def comprehensive_channel_sync(embedding_service, slack_client, channel_id, channel_name, is_zillow_channel=False):
    """Aggressively sync a single channel with much higher limits"""
    try:
        from datetime import datetime, timedelta
        
        # More aggressive settings for comprehensive sync
        if is_zillow_channel:
            # Extra aggressive for Zillow channel
            max_pages = 20  # Up to 20 pages (1000 messages)
            messages_per_page = 200  # Maximum allowed by Slack
            days_back = 365  # Full year of history
            min_message_length = 1  # Index almost everything
            print(f"   🎯 ZILLOW CHANNEL: Using maximum aggressive settings")
        else:
            # Still aggressive for other channels
            max_pages = 10  # Up to 10 pages (500 messages)
            messages_per_page = 100
            days_back = 180  # 6 months
            min_message_length = 3
        
        # Calculate oldest timestamp
        oldest = datetime.now() - timedelta(days=days_back)
        oldest_ts = oldest.timestamp()
        
        all_messages = []
        cursor = None
        page_count = 0
        
        while page_count < max_pages:
            page_count += 1
            
            # Rate limiting - but faster than before
            time.sleep(1)
            
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
                
                print(f"   📄 Page {page_count}: {len(page_messages)} messages")
                
                # Check pagination
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    print(f"   ✅ Retrieved all available messages")
                    break
                    
            except Exception as e:
                print(f"   ❌ Error getting page {page_count}: {e}")
                break
        
        print(f"   📊 Total retrieved: {len(all_messages)} messages")
        
        # Process messages with minimal filtering
        indexed_count = 0
        filtered_out = 0
        
        for i, message in enumerate(all_messages):
            try:
                # Minimal filtering for comprehensive sync
                if message.get('bot_id') or message.get('subtype') in ['channel_join', 'channel_leave']:
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
                    "indexed_from": "comprehensive_sync"
                }
                
                success = embedding_service.add_slack_message(
                    message_id=message.get('ts'),
                    content=text,
                    metadata=metadata
                )
                
                if success:
                    indexed_count += 1
                
                # Progress indicator for large channels
                if (i + 1) % 50 == 0:
                    print(f"   📝 Processed {i + 1}/{len(all_messages)} messages...")
                
            except Exception as e:
                print(f"   ⚠️ Error processing message: {e}")
                continue
        
        print(f"   ✅ Indexed {indexed_count} messages (filtered {filtered_out})")
        return indexed_count
        
    except Exception as e:
        print(f"   ❌ Channel sync failed: {e}")
        return 0

if __name__ == "__main__":
    print("🚀 COMPREHENSIVE SLACK SYNC")
    print("This will aggressively index ALL channels with much higher limits")
    print("Prioritizing #fern-zillow and sales-related channels")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    success = asyncio.run(comprehensive_slack_sync())
    sys.exit(0 if success else 1) 