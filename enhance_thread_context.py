#!/usr/bin/env python3
"""
Enhance existing Slack data with thread-aware entity context
If any message in a thread mentions entities like "Zillow", tag all messages in that thread
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv
import json
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def enhance_thread_context():
    """Enhance existing indexed messages with thread-aware entity context"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("🧵 ENHANCING THREAD-AWARE ENTITY CONTEXT")
        print("=" * 60)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        # Step 1: Get all existing Slack messages
        print("1️⃣ Retrieving all existing Slack messages...")
        all_messages = service.embedding_service.search_similar_content(
            query="message",  # Generic query to get all messages
            n_results=1000,   # Get many messages
            source_filter="slack"
        )
        
        print(f"   Found {len(all_messages)} indexed Slack messages")
        
        # Step 2: Group messages by threads
        print("\n2️⃣ Grouping messages by threads...")
        threads = defaultdict(list)
        standalone_messages = []
        
        for message in all_messages:
            metadata = message.get('metadata', {})
            thread_ts = metadata.get('thread_ts')
            channel_id = metadata.get('channel_id')
            
            if thread_ts:
                thread_key = f"{channel_id}:{thread_ts}"
                threads[thread_key].append(message)
            else:
                standalone_messages.append(message)
        
        print(f"   Found {len(threads)} threads with {sum(len(msgs) for msgs in threads.values())} threaded messages")
        print(f"   Found {len(standalone_messages)} standalone messages")
        
        # Step 3: Analyze threads for entity mentions
        print("\n3️⃣ Analyzing threads for entity mentions...")
        enhanced_count = 0
        entity_threads = []
        
        for thread_key, thread_messages in threads.items():
            channel_id, thread_ts = thread_key.split(':', 1)
            
            # Check if any message in the thread mentions entities
            thread_entities = {
                'companies': set(),
                'contacts': set(), 
                'opportunities': set()
            }
            
            thread_has_entities = False
            
            for message in thread_messages:
                content = message.get('content', '')
                # Extract entities from this message
                entities = service.embedding_service.extract_entities_from_text(content)
                
                if entities:
                    if entities.get('companies'):
                        thread_entities['companies'].update(entities['companies'])
                        thread_has_entities = True
                    if entities.get('contacts'):
                        thread_entities['contacts'].update(entities['contacts'])
                        thread_has_entities = True
                    if entities.get('opportunities'):
                        thread_entities['opportunities'].update(entities['opportunities'])
                        thread_has_entities = True
            
            if thread_has_entities:
                # Convert sets to lists for JSON serialization
                thread_entities_list = {
                    'companies': list(thread_entities['companies']),
                    'contacts': list(thread_entities['contacts']),
                    'opportunities': list(thread_entities['opportunities'])
                }
                
                entity_threads.append({
                    'thread_key': thread_key,
                    'channel_id': channel_id,
                    'thread_ts': thread_ts,
                    'entities': thread_entities_list,
                    'message_count': len(thread_messages),
                    'messages': thread_messages
                })
        
        print(f"   Found {len(entity_threads)} threads with business entities")
        
        # Show sample entity threads
        print("\n📋 Sample entity threads found:")
        for i, thread_info in enumerate(entity_threads[:5]):
            entities = thread_info['entities']
            companies = entities.get('companies', [])
            print(f"   Thread {i+1}: {thread_info['message_count']} messages")
            print(f"     Channel: {thread_info['channel_id']}")
            if companies:
                print(f"     Companies: {', '.join(companies[:3])}{'...' if len(companies) > 3 else ''}")
        
        # Step 4: Re-index messages with enhanced thread context
        print(f"\n4️⃣ Re-indexing messages with enhanced thread context...")
        
        for thread_info in entity_threads:
            thread_entities = thread_info['entities']
            
            # Check if this thread has Zillow specifically
            has_zillow = any('zillow' in company.lower() for company in thread_entities.get('companies', []))
            
            if has_zillow:
                print(f"\n🎯 ZILLOW THREAD FOUND: {thread_info['thread_key']}")
                print(f"   Companies: {thread_entities.get('companies', [])}")
                print(f"   Messages: {thread_info['message_count']}")
                
                # Re-index all messages in this thread with enhanced metadata
                for message in thread_info['messages']:
                    original_metadata = message.get('metadata', {})
                    
                    # Create enhanced metadata
                    enhanced_metadata = original_metadata.copy()
                    enhanced_metadata.update({
                        'thread_entities_json': json.dumps(thread_entities),
                        'thread_has_zillow': True,
                        'thread_has_entities': True,
                        'enhanced_context': True
                    })
                    
                    # Re-add message with enhanced metadata
                    success = service.embedding_service.add_slack_message(
                        message_id=original_metadata.get('ts'),
                        content=message.get('content'),
                        metadata=enhanced_metadata
                    )
                    
                    if success:
                        enhanced_count += 1
                        
                        # Show sample enhanced messages
                        if enhanced_count <= 3:
                            content = message.get('content', '')
                            print(f"     ✅ Enhanced message: {content[:80]}...")
            
            # Also enhance other entity threads (non-Zillow)
            elif thread_entities.get('companies') or thread_entities.get('contacts'):
                # Re-index with general entity context
                for message in thread_info['messages']:
                    original_metadata = message.get('metadata', {})
                    
                    enhanced_metadata = original_metadata.copy()
                    enhanced_metadata.update({
                        'thread_entities_json': json.dumps(thread_entities),
                        'thread_has_entities': True,
                        'enhanced_context': True
                    })
                    
                    success = service.embedding_service.add_slack_message(
                        message_id=original_metadata.get('ts'),
                        content=message.get('content'),
                        metadata=enhanced_metadata
                    )
                    
                    if success:
                        enhanced_count += 1
        
        print(f"\n🎉 ENHANCEMENT COMPLETED!")
        print(f"📊 Enhanced {enhanced_count} messages with thread context")
        print(f"🧵 Processed {len(entity_threads)} entity-rich threads")
        
        # Step 5: Test enhanced Zillow search
        print(f"\n5️⃣ Testing enhanced Zillow search...")
        
        # Search for Zillow with higher limit
        zillow_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=50,
            source_filter="slack"
        )
        
        # Count thread-enhanced results
        enhanced_results = []
        zillow_thread_results = []
        
        for result in zillow_results:
            metadata = result.get('metadata', {})
            if metadata.get('enhanced_context'):
                enhanced_results.append(result)
            if metadata.get('thread_has_zillow'):
                zillow_thread_results.append(result)
        
        print(f"📊 Zillow search results:")
        print(f"   Total results: {len(zillow_results)}")
        print(f"   Enhanced with thread context: {len(enhanced_results)}")
        print(f"   From Zillow threads: {len(zillow_thread_results)}")
        
        # Show sample enhanced results
        print(f"\n🎯 Sample enhanced Zillow thread results:")
        for i, result in enumerate(zillow_thread_results[:3]):
            metadata = result.get('metadata', {})
            content = result.get('content', '')
            thread_entities = json.loads(metadata.get('thread_entities_json', '{}'))
            companies = thread_entities.get('companies', [])
            
            print(f"\n   Result {i+1} from #{metadata.get('channel_name', 'unknown')}:")
            print(f"   Thread companies: {companies}")
            print(f"   Content: {content[:120]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhancement failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧵 THREAD-AWARE ENTITY ENHANCEMENT")
    print("This will enhance existing messages with thread-level entity context")
    print("If any message in a thread mentions Zillow, all messages in that thread become Zillow-searchable")
    print("\nStarting in 3 seconds...")
    
    import time
    time.sleep(3)
    
    success = asyncio.run(enhance_thread_context())
    if success:
        print("\n✅ SUCCESS! Thread context has been enhanced.")
        print("Now try asking: 'What is the exact last slack message that was related to zillow'")
        print("You should get more comprehensive results including thread context!")
    else:
        print("\n❌ FAILED! Check the logs above.")
    
    sys.exit(0 if success else 1) 