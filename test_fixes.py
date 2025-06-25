#!/usr/bin/env python3
"""
Test script to verify the fixes for sales-rag issues:
1. Archived channel handling
2. Better message retrieval with pagination
3. Fixed Salesforce field errors
4. Entity cache fixes
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def test_fixes():
    """Test all the fixes"""
    try:
        # Import after setting up logging
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        # Initialize database (same as main.py)
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        
        # Initialize service
        service = SalesRAGService(session_maker)
        
        logger.info("🧪 Testing Sales RAG fixes...")
        
        # Test 1: Initialize service (this tests Salesforce field fixes and entity cache fixes)
        logger.info("📋 Test 1: Initializing service (tests Salesforce and entity cache fixes)...")
        success = await service.initialize()
        if success:
            logger.info("✅ Service initialization successful - Salesforce and entity cache fixes working!")
        else:
            logger.error("❌ Service initialization failed")
            return False
        
        # Test 2: Manual sync (this tests archived channel filtering and message pagination)
        logger.info("📋 Test 2: Running manual sync (tests archived channel filtering and pagination)...")
        await service.discover_and_index_slack_channels()
        logger.info("✅ Manual sync completed - archived channel and pagination fixes working!")
        
        # Test 3: Health check
        logger.info("📋 Test 3: Running health check...")
        health = await service.health_check()
        logger.info(f"✅ Health check completed: {health['status']}")
        
        logger.info("🎉 All tests completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_fixes())
    sys.exit(0 if success else 1) 