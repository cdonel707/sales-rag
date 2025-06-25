#!/usr/bin/env python3
"""
Test script to verify the focused Slack sync filtering
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def test_focused_sync():
    """Test the focused sync filtering"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        print("🧪 TESTING FOCUSED SLACK SYNC FILTERING")
        print("=" * 50)
        
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        slack_client = service.slack_handler.client
        
        print("\n1️⃣ Testing channel discovery with focused filtering...")
        
        # Test the new find_relevant_channels method
        relevant_channels = service.embedding_service.find_relevant_channels(
            slack_client, 
            company_names=[]  # Not using company matching anymore
        )
        
        print(f"\n📊 RESULTS:")
        print(f"   Found {len(relevant_channels)} relevant channels")
        
        if relevant_channels:
            print(f"\n✅ CHANNELS THAT WILL BE SYNCED:")
            for channel in relevant_channels:
                print(f"   - #{channel['name']}: {channel['reason']}")
        else:
            print(f"\n⚠️  No channels found matching criteria:")
            print(f"   - Must have 5+ members")
            print(f"   - Must start with 'fern-' OR be 'sales' or 'meeting-reports'")
        
        print(f"\n2️⃣ Settings Summary:")
        print(f"   - Lookback period: 365 days (1 year)")
        print(f"   - Rate limiting: 61 seconds between requests")
        print(f"   - Batch size: 15 messages per request")
        print(f"   - Member filter: 5+ members required")
        
        return len(relevant_channels) > 0
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Testing focused Slack sync filtering...")
    print("This will show which channels match the new criteria\n")
    
    success = asyncio.run(test_focused_sync())
    if success:
        print("\n✅ SUCCESS! Found relevant channels to sync.")
        print("You can now run comprehensive_slack_sync.py to index them.")
    else:
        print("\n❌ No relevant channels found or test failed.")
        print("Check if you have channels starting with 'fern-' or named 'sales'/'meeting-reports'")
    
    sys.exit(0 if success else 1) 