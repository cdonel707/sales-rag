#!/usr/bin/env python3
"""
Quick status check to see current data in vector database
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def check_data_status():
    """Check current status of indexed data"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("📊 CURRENT DATA STATUS CHECK")
        print("=" * 50)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        # Check collection stats
        try:
            collection = service.embedding_service.collection
            total_count = collection.count()
            print(f"📈 Total indexed items: {total_count}")
        except Exception as e:
            print(f"❌ Could not get total count: {e}")
            total_count = 0
        
        # Test Slack search
        print(f"\n🔍 Testing Slack searches...")
        
        # General Slack search
        slack_results = service.embedding_service.search_similar_content(
            query="message",
            n_results=10,
            source_filter="slack"
        )
        print(f"   Slack messages found: {len(slack_results)}")
        
        # Zillow-specific search
        zillow_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=10,
            source_filter="slack"
        )
        print(f"   Zillow messages found: {len(zillow_results)}")
        
        # Show channel breakdown
        if slack_results:
            channels = {}
            for result in slack_results:
                metadata = result.get('metadata', {})
                channel = metadata.get('channel_name', 'unknown')
                channels[channel] = channels.get(channel, 0) + 1
            
            print(f"\n📋 Current Slack channels indexed:")
            for channel, count in sorted(channels.items()):
                print(f"   #{channel}: {count} messages")
        
        # Show sample Zillow results
        if zillow_results:
            print(f"\n🎯 Sample Zillow results:")
            for i, result in enumerate(zillow_results[:3]):
                metadata = result.get('metadata', {})
                content = result.get('content', '')
                channel = metadata.get('channel_name', 'unknown')
                print(f"   {i+1}. #{channel}: {content[:100]}...")
        
        # Check Salesforce data
        print(f"\n💼 Testing Salesforce search...")
        sf_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=5,
            source_filter="salesforce"
        )
        print(f"   Salesforce Zillow records: {len(sf_results)}")
        
        print(f"\n" + "=" * 50)
        print(f"📊 SUMMARY:")
        print(f"   Total items: {total_count}")
        print(f"   Slack messages: {len(slack_results)}")
        print(f"   Zillow Slack messages: {len(zillow_results)}")
        print(f"   Salesforce records: {len(sf_results)}")
        
        if len(zillow_results) == 0:
            print(f"\n🚨 ISSUE: No Zillow Slack messages found!")
            print(f"   This explains why you're getting hallucinated responses.")
            print(f"   Run the sync scripts to fix this.")
        else:
            print(f"\n✅ Good! Found {len(zillow_results)} Zillow messages.")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(check_data_status())
    sys.exit(0 if success else 1) 