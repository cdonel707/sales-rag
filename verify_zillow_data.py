#!/usr/bin/env python3
"""
Verify the actual Zillow data indexed without search limits
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def verify_zillow_data():
    """Verify actual Zillow data indexed"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("🔍 VERIFYING ZILLOW DATA")
        print("=" * 50)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        # Test different search approaches
        print("📊 Testing different search approaches...\n")
        
        # 1. Search for "Zillow" with high limit
        print("1️⃣ Searching for 'Zillow' (limit 50):")
        zillow_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=50,  # Much higher limit
            source_filter="slack"
        )
        print(f"   Found: {len(zillow_results)} results")
        
        # 2. Search for messages from #fern-zillow specifically
        print("\n2️⃣ Searching all messages from #fern-zillow:")
        fern_zillow_results = service.embedding_service.search_similar_content(
            query="message",  # Generic query to get all messages
            n_results=50,
            source_filter="slack"
        )
        
        # Filter for #fern-zillow
        fern_zillow_only = [r for r in fern_zillow_results if r.get('metadata', {}).get('channel_name') == 'fern-zillow']
        print(f"   Found: {len(fern_zillow_only)} messages from #fern-zillow")
        
        # 3. Search for API, spec, collaboration terms
        print("\n3️⃣ Searching for API/spec/collaboration terms:")
        api_results = service.embedding_service.search_similar_content(
            query="API spec collaboration",
            n_results=50,
            source_filter="slack"
        )
        api_fern_zillow = [r for r in api_results if r.get('metadata', {}).get('channel_name') == 'fern-zillow']
        print(f"   Found: {len(api_fern_zillow)} API-related messages from #fern-zillow")
        
        # Show breakdown by channel
        print("\n📋 CHANNEL BREAKDOWN:")
        all_channels = {}
        for result in fern_zillow_results:
            metadata = result.get('metadata', {})
            channel = metadata.get('channel_name', 'unknown')
            if channel not in all_channels:
                all_channels[channel] = 0
            all_channels[channel] += 1
        
        for channel, count in sorted(all_channels.items()):
            if count > 0:
                print(f"   #{channel}: {count} messages")
        
        # Show sample #fern-zillow messages
        print(f"\n🎯 SAMPLE #fern-zillow MESSAGES:")
        count = 0
        for result in fern_zillow_results:
            metadata = result.get('metadata', {})
            if metadata.get('channel_name') == 'fern-zillow':
                content = result.get('content', '')
                ts = metadata.get('ts', 'unknown')
                indexed_from = metadata.get('indexed_from', 'unknown')
                print(f"\n   Message {count + 1} (ts: {ts}, indexed_from: {indexed_from}):")
                print(f"   {content[:150]}...")
                count += 1
                if count >= 5:  # Show first 5
                    break
        
        print(f"\n" + "=" * 50)
        print(f"📊 VERIFICATION SUMMARY:")
        print(f"   Messages mentioning 'Zillow': {len(zillow_results)}")
        print(f"   Total messages from #fern-zillow: {len(fern_zillow_only)}")
        print(f"   API-related messages from #fern-zillow: {len(api_fern_zillow)}")
        
        # Expected: Should see 32 messages from #fern-zillow if sync worked correctly
        if len(fern_zillow_only) == 32:
            print(f"   ✅ PERFECT: Found expected 32 messages from #fern-zillow")
        elif len(fern_zillow_only) > 0:
            print(f"   ⚠️ PARTIAL: Found {len(fern_zillow_only)} messages (expected 32)")
        else:
            print(f"   ❌ PROBLEM: No messages found from #fern-zillow")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(verify_zillow_data())
    sys.exit(0 if success else 1) 