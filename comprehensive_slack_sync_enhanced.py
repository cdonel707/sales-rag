#!/usr/bin/env python3
"""
Comprehensive Enhanced Slack Sync with Thread-Aware Intelligence
Applies all learnings from Zillow success to ALL Slack channels
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv
import time
import json
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def comprehensive_enhanced_slack_sync():
    """Comprehensive sync with thread-aware intelligence for ALL channels"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        logger.info("🚀 Starting ENHANCED COMPREHENSIVE Slack sync...")
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        # Get ALL channels with enhanced discovery
        print("\n1️⃣ Discovering ALL Slack channels with enhanced intelligence...")
        all_channels = []
        cursor = None
        
        while True:
            time.sleep(2)  # Rate limiting
            params = {
                'types': 'public_channel',  # Only public channels (we don't have private access)
                'limit': 200,  # Maximum allowed
                'exclude_archived': False  # Include archived channels for comprehensive data
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
        
        # Intelligent channel categorization and prioritization
        print("\n2️⃣ Categorizing channels with business intelligence...")
        
        priority_channels = []  # High business value
        company_channels = []   # Dedicated company channels
        project_channels = []   # Project/deal channels  
        general_channels = []   # General business channels
        skip_channels = []      # Low value channels
        
        # Enhanced channel categorization
        for channel in all_channels:
            channel_name = channel.get('name', '').lower()
            is_archived = channel.get('is_archived', False)
            member_count = channel.get('num_members', 0)
            
            # Skip very low-value channels
            if any(skip_word in channel_name for skip_word in [
                'random', 'test', 'bot', 'notifications', 'alerts', 'logs'
            ]) and member_count < 5:
                skip_channels.append(channel)
                continue
            
            # Identify company-specific channels (like #fern-zillow)
            if any(company in channel_name for company in [
                'zillow', 'microsoft', 'google', 'salesforce', 'hubspot', 
                'stripe', 'twilio', 'aws', 'openai', 'anthropic'
            ]) or '-' in channel_name:  # Many company channels use dashes
                company_channels.append(channel)
                channel['channel_category'] = 'company_dedicated'
            
            # High-priority business channels
            elif any(priority_word in channel_name for priority_word in [
                'sales', 'deals', 'customers', 'partnerships', 'revenue',
                'prospects', 'leads', 'contracts', 'demo', 'onboarding'
            ]):
                priority_channels.append(channel)
                channel['channel_category'] = 'high_priority_business'
            
            # Project/deal channels
            elif any(project_word in channel_name for project_word in [
                'project', 'integration', 'implementation', 'pilot', 'poc'
            ]):
                project_channels.append(channel)
                channel['channel_category'] = 'project_deal'
            
            # General business channels
            elif member_count >= 3:  # Has some activity
                general_channels.append(channel)
                channel['channel_category'] = 'general_business'
            else:
                skip_channels.append(channel)
        
        print(f"   🎯 Company-dedicated channels: {len(company_channels)}")
        print(f"   📈 High-priority business: {len(priority_channels)}")
        print(f"   🔧 Project/deal channels: {len(project_channels)}")
        print(f"   💼 General business: {len(general_channels)}")
        print(f"   ⏭️ Skipping low-value: {len(skip_channels)}")
        
        # Show discovered company channels
        if company_channels:
            print(f"\n🎯 Company channels found:")
            for ch in company_channels[:10]:  # Show first 10
                print(f"   #{ch['name']}")
        
        # Process channels in intelligent order
        ordered_channels = (
            company_channels + 
            priority_channels + 
            project_channels + 
            general_channels[:15]  # Limit general channels for now
        )
        
        print(f"\n3️⃣ Processing {len(ordered_channels)} high-value channels...")
        
        total_indexed = 0
        channel_insights = {}
        
        for i, channel in enumerate(ordered_channels):
            channel_id = channel['id']
            channel_name = channel['name']
            is_archived = channel.get('is_archived', False)
            is_member = channel.get('is_member', False)
            category = channel.get('channel_category', 'general')
            
            print(f"\n--- Channel {i+1}/{len(ordered_channels)}: #{channel_name} ({category}) ---")
            
            # Skip archived channels unless they're company-dedicated
            if is_archived and category != 'company_dedicated':
                print("   ⏭️ Skipping archived non-company channel")
                continue
            
            # Try to join channel if not a member (for active channels)
            if not is_member and not is_archived:
                try:
                    join_response = slack_client.conversations_join(channel=channel_id)
                    if join_response.get('ok'):
                        print("   ✅ Successfully joined channel")
                    else:
                        error = join_response.get('error')
                        if error not in ['already_in_channel', 'is_archived']:
                            print(f"   ❌ Could not join: {error}")
                            continue
                except Exception as e:
                    print(f"   ❌ Error joining: {e}")
                    continue
            
            # Enhanced message sync with intelligent settings
            indexed_count = await enhanced_channel_sync(
                service.embedding_service,
                slack_client,
                channel_id,
                channel_name,
                category=category
            )
            
            total_indexed += indexed_count
            channel_insights[channel_name] = {
                'category': category,
                'indexed_count': indexed_count,
                'is_archived': is_archived
            }
            
            print(f"   📝 Indexed {indexed_count} messages")
            
            # Adaptive delay based on success
            if indexed_count > 0:
                print("   ⏳ Waiting 8 seconds (successful sync)...")
                time.sleep(8)
            else:
                print("   ⏳ Waiting 5 seconds (empty channel)...")
                time.sleep(5)
        
        print(f"\n🎉 ENHANCED COMPREHENSIVE SYNC COMPLETED!")
        print(f"📊 Total indexed: {total_indexed} messages across {len(ordered_channels)} channels")
        
        # Show insights
        print(f"\n📋 CHANNEL INSIGHTS:")
        successful_channels = 0
        for channel_name, insights in channel_insights.items():
            if insights['indexed_count'] > 0:
                print(f"   #{channel_name}: {insights['indexed_count']} messages ({insights['category']})")
                successful_channels += 1
        
        print(f"\n📊 SUMMARY:")
        print(f"   Channels processed: {len(ordered_channels)}")
        print(f"   Channels with data: {successful_channels}")
        print(f"   Total messages indexed: {total_indexed}")
        
        # Test enhanced search across multiple entities
        print(f"\n4️⃣ Testing enhanced multi-entity search...")
        
        test_entities = ['Zillow', 'demo', 'contract', 'integration', 'API', 'partnership']
        
        for entity in test_entities:
            results = service.embedding_service.search_similar_content(
                query=entity,
                n_results=5,
                source_filter="slack"
            )
            print(f"   {entity}: {len(results)} results")
        
        print(f"\n✅ SUCCESS! You can now ask about ANY deal, contact, or company!")
        print(f"Try asking about: deals, partnerships, specific companies, integrations, demos, etc.")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced comprehensive sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def enhanced_channel_sync(embedding_service, slack_client, channel_id, channel_name, category="general"):
    """Enhanced channel sync with adaptive settings based on channel category"""
    try:
        from datetime import datetime, timedelta
        
        # Adaptive settings based on channel importance
        if category == 'company_dedicated':
            # Maximum settings for company channels (like #fern-zillow)
            max_pages = 15
            messages_per_page = 50
            days_back = 365  # Full year
            min_message_length = 1
            print(f"   🎯 COMPANY CHANNEL: Maximum aggressive settings")
        elif category == 'high_priority_business':
            # High settings for sales/deals channels
            max_pages = 10
            messages_per_page = 50
            days_back = 180  # 6 months
            min_message_length = 3
            print(f"   📈 HIGH PRIORITY: Aggressive settings")
        elif category == 'project_deal':
            # Good settings for project channels
            max_pages = 8
            messages_per_page = 50
            days_back = 120  # 4 months
            min_message_length = 5
            print(f"   🔧 PROJECT CHANNEL: Enhanced settings")
        else:
            # Standard settings for general channels
            max_pages = 5
            messages_per_page = 30
            days_back = 60  # 2 months
            min_message_length = 10
            print(f"   💼 GENERAL: Standard settings")
        
        # Calculate oldest timestamp
        oldest = datetime.now() - timedelta(days=days_back)
        oldest_ts = oldest.timestamp()
        
        all_messages = []
        cursor = None
        page_count = 0
        
        while page_count < max_pages:
            page_count += 1
            
            # Conservative rate limiting (learned from experience)
            time.sleep(3)
            
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
                
                if page_count <= 3:  # Show progress for first few pages
                    print(f"   📄 Page {page_count}: {len(page_messages)} messages")
                
                # Check pagination
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    break
                    
            except Exception as e:
                print(f"   ❌ Error getting page {page_count}: {e}")
                break
        
        print(f"   📊 Retrieved: {len(all_messages)} total messages")
        
        if len(all_messages) == 0:
            return 0
        
        # Enhanced message processing with intelligent tagging
        indexed_count = 0
        filtered_out = 0
        
        # Detect if this is a company-dedicated channel
        is_company_channel = category == 'company_dedicated'
        company_name = None
        
        if is_company_channel and '-' in channel_name:
            # Extract company name from channel (e.g., fern-zillow -> zillow)
            parts = channel_name.split('-')
            if len(parts) >= 2:
                company_name = parts[-1]  # Take last part as company name
        
        for message in all_messages:
            try:
                # Enhanced filtering
                if message.get('bot_id') or message.get('subtype') in ['channel_join', 'channel_leave']:
                    filtered_out += 1
                    continue
                
                text = message.get('text', '')
                if len(text) < min_message_length:
                    filtered_out += 1
                    continue
                
                # Enhanced metadata with intelligent tagging
                user_id = message.get('user')
                user_name = f"User-{user_id}" if user_id else 'Unknown User'
                
                metadata = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "user_id": user_id,
                    "user_name": user_name,
                    "ts": message.get('ts'),
                    "thread_ts": message.get('thread_ts'),
                    "channel_category": category,
                    "indexed_from": "enhanced_comprehensive_sync"
                }
                
                # Apply channel-level intelligence (learned from Zillow success)
                if is_company_channel and company_name:
                    metadata.update({
                        'channel_is_company_dedicated': True,
                        'company_context_channel': True,
                        'dedicated_company': company_name,
                        'enhanced_context': True
                    })
                
                # Extract entities from message
                entities = embedding_service.extract_entities_from_text(text)
                if entities:
                    metadata['entities_json'] = json.dumps(entities)
                    if entities.get('companies'):
                        metadata['has_company_mentions'] = True
                
                success = embedding_service.add_slack_message(
                    message_id=message.get('ts'),
                    content=text,
                    metadata=metadata
                )
                
                if success:
                    indexed_count += 1
                
            except Exception as e:
                print(f"   ⚠️ Error processing message: {e}")
                filtered_out += 1
                continue
        
        print(f"   ✅ Indexed {indexed_count} messages (filtered {filtered_out})")
        return indexed_count
        
    except Exception as e:
        print(f"   ❌ Channel sync failed: {e}")
        return 0

if __name__ == "__main__":
    print("🚀 ENHANCED COMPREHENSIVE SLACK SYNC")
    print("Applies thread-aware intelligence to ALL Slack channels")
    print("Settings: Adaptive based on channel importance")
    print("Result: Ask about ANY deal, contact, or company!")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    success = asyncio.run(comprehensive_enhanced_slack_sync())
    if success:
        print("\n🎉 SUCCESS! Comprehensive Slack data indexed with intelligence.")
        print("You can now ask about ANY company, deal, contact, or business topic!")
    else:
        print("\n❌ FAILED! Check the logs above for issues.")
    
    sys.exit(0 if success else 1) 