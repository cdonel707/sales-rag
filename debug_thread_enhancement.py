#!/usr/bin/env python3
"""
Debug thread enhancement to see why Zillow threads weren't detected
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

async def debug_thread_enhancement():
    """Debug why Zillow threads weren't detected"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("🔍 DEBUGGING THREAD ENHANCEMENT")
        print("=" * 50)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        # Get all messages from #fern-zillow specifically
        print("1️⃣ Getting all #fern-zillow messages...")
        all_messages = service.embedding_service.search_similar_content(
            query="message",
            n_results=100,
            source_filter="slack"
        )
        
        # Filter for #fern-zillow
        zillow_channel_messages = [
            msg for msg in all_messages 
            if msg.get('metadata', {}).get('channel_name') == 'fern-zillow'
        ]
        
        print(f"   Found {len(zillow_channel_messages)} messages from #fern-zillow")
        
        # Check each message for Zillow mentions
        print("\n2️⃣ Analyzing each message for Zillow mentions...")
        
        threads = defaultdict(list)
        standalone_messages = []
        
        for i, message in enumerate(zillow_channel_messages):
            metadata = message.get('metadata', {})
            content = message.get('content', '')
            thread_ts = metadata.get('thread_ts')
            ts = metadata.get('ts')
            
            print(f"\n   Message {i+1}:")
            print(f"     Content: {content[:100]}...")
            print(f"     Thread TS: {thread_ts}")
            print(f"     TS: {ts}")
            
            # Check for Zillow mentions (case insensitive)
            has_zillow = 'zillow' in content.lower()
            print(f"     Contains 'zillow': {has_zillow}")
            
            # Check entity extraction
            entities = service.embedding_service.extract_entities_from_text(content)
            print(f"     Extracted entities: {entities}")
            
            if thread_ts:
                thread_key = f"C08T73FB06B:{thread_ts}"  # fern-zillow channel ID
                threads[thread_key].append({
                    'message': message,
                    'has_zillow': has_zillow,
                    'entities': entities
                })
            else:
                standalone_messages.append({
                    'message': message,
                    'has_zillow': has_zillow,
                    'entities': entities
                })
        
        print(f"\n3️⃣ Thread Analysis:")
        print(f"   Threads found: {len(threads)}")
        print(f"   Standalone messages: {len(standalone_messages)}")
        
        # Analyze threads for Zillow
        zillow_threads = []
        for thread_key, thread_messages in threads.items():
            print(f"\n   Thread: {thread_key}")
            thread_has_zillow = any(msg['has_zillow'] for msg in thread_messages)
            print(f"     Messages: {len(thread_messages)}")
            print(f"     Has Zillow: {thread_has_zillow}")
            
            if thread_has_zillow:
                zillow_threads.append(thread_key)
                print(f"     🎯 ZILLOW THREAD FOUND!")
                for j, msg in enumerate(thread_messages):
                    content = msg['message'].get('content', '')
                    print(f"       Msg {j+1}: {content[:60]}... (zillow: {msg['has_zillow']})")
        
        # Check standalone messages
        print(f"\n4️⃣ Standalone Message Analysis:")
        standalone_zillow = [msg for msg in standalone_messages if msg['has_zillow']]
        print(f"   Standalone messages with Zillow: {len(standalone_zillow)}")
        
        for i, msg in enumerate(standalone_zillow[:5]):
            content = msg['message'].get('content', '')
            print(f"     {i+1}. {content[:80]}...")
        
        # Manual Zillow enhancement
        print(f"\n5️⃣ Manual Zillow Enhancement...")
        enhanced_count = 0
        
        # First, enhance all messages that explicitly mention Zillow
        all_zillow_messages = [msg for msg in zillow_channel_messages if 'zillow' in msg.get('content', '').lower()]
        
        print(f"   Found {len(all_zillow_messages)} messages explicitly mentioning Zillow")
        
        for message in all_zillow_messages:
            original_metadata = message.get('metadata', {})
            content = message.get('content', '')
            
            enhanced_metadata = original_metadata.copy()
            enhanced_metadata.update({
                'explicitly_mentions_zillow': True,
                'zillow_enhanced': True,
                'enhanced_context': True
            })
            
            success = service.embedding_service.add_slack_message(
                message_id=original_metadata.get('ts'),
                content=content,
                metadata=enhanced_metadata
            )
            
            if success:
                enhanced_count += 1
                print(f"     ✅ Enhanced: {content[:60]}...")
        
        # Now enhance ALL messages from #fern-zillow with Zillow context
        # Since this is the dedicated Zillow channel
        print(f"\n6️⃣ Enhancing ALL #fern-zillow messages as Zillow-related...")
        
        for message in zillow_channel_messages:
            original_metadata = message.get('metadata', {})
            content = message.get('content', '')
            
            # Skip if already enhanced
            if original_metadata.get('zillow_enhanced'):
                continue
            
            enhanced_metadata = original_metadata.copy()
            enhanced_metadata.update({
                'channel_is_zillow_dedicated': True,
                'zillow_context_channel': True,
                'enhanced_context': True
            })
            
            success = service.embedding_service.add_slack_message(
                message_id=original_metadata.get('ts'),
                content=content,
                metadata=enhanced_metadata
            )
            
            if success:
                enhanced_count += 1
        
        print(f"\n🎉 MANUAL ENHANCEMENT COMPLETED!")
        print(f"📊 Enhanced {enhanced_count} messages with Zillow context")
        print(f"🎯 All #fern-zillow messages now tagged as Zillow-related")
        
        # Test enhanced search
        print(f"\n7️⃣ Testing enhanced Zillow search...")
        zillow_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=20,
            source_filter="slack"
        )
        
        enhanced_results = [
            r for r in zillow_results 
            if r.get('metadata', {}).get('enhanced_context')
        ]
        
        print(f"📊 Enhanced search results:")
        print(f"   Total Zillow results: {len(zillow_results)}")
        print(f"   Enhanced results: {len(enhanced_results)}")
        
        # Show sample enhanced results
        print(f"\n🎯 Sample enhanced results:")
        for i, result in enumerate(enhanced_results[:5]):
            metadata = result.get('metadata', {})
            content = result.get('content', '')
            explicitly_mentions = metadata.get('explicitly_mentions_zillow', False)
            channel_dedicated = metadata.get('channel_is_zillow_dedicated', False)
            
            print(f"\n   Result {i+1} from #{metadata.get('channel_name', 'unknown')}:")
            print(f"     Content: {content[:100]}...")
            print(f"     Explicit mention: {explicitly_mentions}")
            print(f"     Channel dedicated: {channel_dedicated}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(debug_thread_enhancement())
    sys.exit(0 if success else 1) 