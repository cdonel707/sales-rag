#!/usr/bin/env python3
"""
Smart Comprehensive Sync - Rate-limit friendly approach
Gets maximum data from ALL channels while respecting Slack's limits
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv
import time
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def smart_comprehensive_sync():
    """Smart comprehensive sync that works around rate limits"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        logger.info("🧠 Starting SMART COMPREHENSIVE Slack sync...")
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Get ALL channels but be smart about processing
        print("\n1️⃣ Smart channel discovery...")
        all_channels = []
        cursor = None
        
        while True:
            time.sleep(5)  # More conservative rate limiting
            params = {
                'types': 'public_channel',
                'limit': 200,
                'exclude_archived': False
            }
            if cursor:
                params['cursor'] = cursor
            
            channels_response = slack_client.conversations_list(**params)
            
            if not channels_response.get('ok'):
                error = channels_response.get('error')
                if error == 'ratelimited':
                    print("   ⏳ Rate limited on channel discovery, waiting 60s...")
                    time.sleep(60)
                    continue
                logger.error(f"Failed to get channels: {error}")
                break
            
            batch_channels = channels_response.get('channels', [])
            all_channels.extend(batch_channels)
            
            cursor = channels_response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
        
        print(f"📊 Found {len(all_channels)} total channels")
        
        # Ultra-smart prioritization (focus on highest value)
        print("\n2️⃣ Ultra-smart channel prioritization...")
        
        ultra_priority = []   # Company channels + high business value
        high_priority = []    # Sales/deals/partnerships  
        medium_priority = []  # General business with activity
        
        for channel in all_channels:
            channel_name = channel.get('name', '').lower()
            member_count = channel.get('num_members', 0)
            is_archived = channel.get('is_archived', False)
            
            # Skip very low value channels entirely
            if any(skip_word in channel_name for skip_word in [
                'random', 'test', 'bot-', 'notifications', 'alerts', 'logs', 'spam'
            ]) and member_count < 5:
                continue
            
            # ULTRA PRIORITY: Company channels + critical business
            if any(pattern in channel_name for pattern in [
                'fern-', '-client', '-customer', '-partner'  # Company/client channels
            ]) or any(biz_word in channel_name for biz_word in [
                'sales', 'deals', 'revenue', 'partnerships', 'customers'
            ]):
                ultra_priority.append(channel)
                channel['sync_category'] = 'ultra_priority'
            
            # HIGH PRIORITY: Business operations
            elif any(priority_word in channel_name for priority_word in [
                'demo', 'onboarding', 'support', 'implementation', 'integration',
                'contracts', 'legal', 'success', 'growth'
            ]) and member_count >= 3:
                high_priority.append(channel)
                channel['sync_category'] = 'high_priority'
            
            # MEDIUM PRIORITY: Active general channels
            elif member_count >= 5 and not is_archived:
                medium_priority.append(channel)
                channel['sync_category'] = 'medium_priority'
        
        print(f"   🎯 Ultra priority (company/sales): {len(ultra_priority)}")
        print(f"   📈 High priority (business ops): {len(high_priority)}")
        print(f"   💼 Medium priority (active general): {len(medium_priority)}")
        
        # Show ultra priority channels
        if ultra_priority:
            print(f"\n🎯 Ultra priority channels:")
            for ch in ultra_priority[:15]:
                print(f"   #{ch['name']} ({ch.get('num_members', 0)} members)")
        
        # Process in ultra-smart order with rate-limit management
        channels_to_process = ultra_priority + high_priority[:10] + medium_priority[:5]
        
        print(f"\n3️⃣ Processing {len(channels_to_process)} highest-value channels...")
        print(f"   Strategy: Ultra-conservative rate limiting for maximum success")
        
        total_indexed = 0
        successful_channels = 0
        rate_limited_count = 0
        
        for i, channel in enumerate(channels_to_process):
            channel_id = channel['id']
            channel_name = channel['name']
            is_archived = channel.get('is_archived', False)
            is_member = channel.get('is_member', False)
            category = channel.get('sync_category', 'medium')
            
            print(f"\n--- Channel {i+1}/{len(channels_to_process)}: #{channel_name} ({category}) ---")
            
            # Skip archived unless ultra priority
            if is_archived and category != 'ultra_priority':
                print("   ⏭️ Skipping archived non-ultra channel")
                continue
            
            # Smart channel joining with error handling
            if not is_member and not is_archived:
                try:
                    time.sleep(3)  # Pre-join delay
                    join_response = slack_client.conversations_join(channel=channel_id)
                    if join_response.get('ok'):
                        print("   ✅ Joined channel")
                    else:
                        error = join_response.get('error')
                        if error == 'ratelimited':
                            print("   ⏳ Rate limited on join, waiting 30s...")
                            time.sleep(30)
                            rate_limited_count += 1
                            continue
                        elif error not in ['already_in_channel', 'is_archived']:
                            print(f"   ❌ Could not join: {error}")
                            continue
                except Exception as e:
                    print(f"   ❌ Join error: {e}")
                    continue
            
            # Ultra-smart message sync with adaptive settings
            indexed_count = await ultra_smart_channel_sync(
                service.embedding_service,
                slack_client,
                channel_id,
                channel_name,
                category=category
            )
            
            if indexed_count > 0:
                total_indexed += indexed_count
                successful_channels += 1
                print(f"   ✅ Success: {indexed_count} messages")
                
                # Adaptive delay based on success
                if category == 'ultra_priority':
                    time.sleep(15)  # Longer delay for important channels
                else:
                    time.sleep(10)
            else:
                print(f"   ⚠️ No messages indexed")
                time.sleep(5)  # Shorter delay for failed channels
            
            # Rate limit management
            if rate_limited_count > 3:
                print(f"   🛑 Hit rate limits {rate_limited_count} times, taking longer break...")
                time.sleep(120)  # 2 minute break
                rate_limited_count = 0
        
        print(f"\n🎉 SMART COMPREHENSIVE SYNC COMPLETED!")
        print(f"📊 Results:")
        print(f"   Channels processed: {len(channels_to_process)}")
        print(f"   Successful channels: {successful_channels}")
        print(f"   Total messages indexed: {total_indexed}")
        print(f"   Rate limit hits: {rate_limited_count}")
        
        # Enhanced multi-entity test
        print(f"\n4️⃣ Testing enhanced search capabilities...")
        
        test_queries = [
            "demo", "partnership", "integration", "contract", "deal",
            "Elevenlabs", "Deno", "Box", "Zillow", "API", "implementation"
        ]
        
        search_results = {}
        for query in test_queries:
            results = service.embedding_service.search_similar_content(
                query=query,
                n_results=10,
                source_filter="slack"
            )
            search_results[query] = len(results)
            
        print(f"📊 Search capability test:")
        for query, count in search_results.items():
            print(f"   '{query}': {count} results")
        
        print(f"\n✅ SUCCESS! You can now ask about deals, companies, and business topics!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Smart comprehensive sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def ultra_smart_channel_sync(embedding_service, slack_client, channel_id, channel_name, category="medium"):
    """Ultra-smart channel sync with adaptive rate limiting"""
    try:
        from datetime import datetime, timedelta
        
        # Ultra-smart adaptive settings
        if category == 'ultra_priority':
            max_pages = 10      # Get substantial data
            messages_per_page = 30  # Conservative batch size
            days_back = 180     # 6 months
            min_length = 1      # Index almost everything
            page_delay = 8      # Longer delays between pages
        elif category == 'high_priority':
            max_pages = 6
            messages_per_page = 25
            days_back = 90      # 3 months
            min_length = 3
            page_delay = 6
        else:
            max_pages = 3
            messages_per_page = 20
            days_back = 30      # 1 month
            min_length = 5
            page_delay = 4
        
        print(f"   🧠 Smart settings: {max_pages} pages, {messages_per_page} msgs/page, {days_back} days")
        
        # Calculate timestamp
        oldest = datetime.now() - timedelta(days=days_back)
        oldest_ts = oldest.timestamp()
        
        all_messages = []
        cursor = None
        page_count = 0
        consecutive_rate_limits = 0
        
        while page_count < max_pages:
            page_count += 1
            
            # Smart rate limiting with exponential backoff
            base_delay = page_delay + (consecutive_rate_limits * 5)
            time.sleep(base_delay)
            
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
                        consecutive_rate_limits += 1
                        wait_time = min(60 * consecutive_rate_limits, 300)  # Max 5 minutes
                        print(f"   ⏳ Rate limited (#{consecutive_rate_limits}), waiting {wait_time}s...")
                        time.sleep(wait_time)
                        page_count -= 1  # Retry this page
                        continue
                    else:
                        print(f"   ❌ API Error: {error}")
                        break
                
                # Success - reset rate limit counter
                consecutive_rate_limits = 0
                
                page_messages = history_response.get('messages', [])
                all_messages.extend(page_messages)
                
                print(f"   📄 Page {page_count}: {len(page_messages)} messages")
                
                # Check pagination
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    break
                    
            except Exception as e:
                print(f"   ❌ Exception on page {page_count}: {e}")
                break
        
        if len(all_messages) == 0:
            print(f"   📊 No messages retrieved")
            return 0
        
        print(f"   📊 Total retrieved: {len(all_messages)} messages")
        
        # Smart message processing
        indexed_count = 0
        filtered_out = 0
        
        # Extract company name for company channels
        company_name = None
        if 'fern-' in channel_name:
            company_name = channel_name.replace('fern-', '')
        
        for message in all_messages:
            try:
                # Smart filtering
                if message.get('bot_id') or message.get('subtype') in ['channel_join', 'channel_leave']:
                    filtered_out += 1
                    continue
                
                text = message.get('text', '')
                if len(text) < min_length:
                    filtered_out += 1
                    continue
                
                # Enhanced metadata with smart tagging
                user_id = message.get('user')
                user_name = f"User-{user_id}" if user_id else 'Unknown User'
                
                metadata = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "user_id": user_id,
                    "user_name": user_name,
                    "ts": message.get('ts'),
                    "thread_ts": message.get('thread_ts'),
                    "sync_category": category,
                    "indexed_from": "smart_comprehensive_sync"
                }
                
                # Apply smart company tagging
                if company_name:
                    metadata.update({
                        'channel_is_company_dedicated': True,
                        'dedicated_company': company_name,
                        'company_context_channel': True,
                        'enhanced_context': True
                    })
                
                # Entity extraction
                entities = embedding_service.extract_entities_from_text(text)
                if entities:
                    metadata['entities_json'] = json.dumps(entities)
                
                success = embedding_service.add_slack_message(
                    message_id=message.get('ts'),
                    content=text,
                    metadata=metadata
                )
                
                if success:
                    indexed_count += 1
                
            except Exception as e:
                filtered_out += 1
                continue
        
        print(f"   ✅ Indexed: {indexed_count}, Filtered: {filtered_out}")
        return indexed_count
        
    except Exception as e:
        print(f"   ❌ Channel sync failed: {e}")
        return 0

if __name__ == "__main__":
    print("🧠 SMART COMPREHENSIVE SLACK SYNC")
    print("Rate-limit friendly approach for maximum data collection")
    print("Focus: Ultra-priority channels (company/sales) + smart rate limiting")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    success = asyncio.run(smart_comprehensive_sync())
    if success:
        print("\n🎉 SUCCESS! Smart comprehensive sync completed.")
        print("You can now ask about ANY company, deal, or business topic!")
        print("Try: 'What demos have we done?' or 'Show me Elevenlabs discussions'")
    else:
        print("\n❌ FAILED! Check the logs above for issues.")
    
    sys.exit(0 if success else 1) 