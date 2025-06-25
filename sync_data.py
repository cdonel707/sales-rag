#!/usr/bin/env python3
"""
Standalone script to sync Salesforce data to the vector database.
This can be run independently or as a scheduled job.
"""

import asyncio
import logging
import sys
from app.database.models import create_database, get_session_maker
from app.services import SalesRAGService
from app.config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main sync function"""
    logger.info("Starting Salesforce data sync...")
    
    try:
        # Check if required environment variables are set
        required_vars = [
            'SALESFORCE_USERNAME',
            'SALESFORCE_PASSWORD', 
            'SALESFORCE_SECURITY_TOKEN',
            'OPENAI_API_KEY'
        ]
        
        missing_vars = [var for var in required_vars if not getattr(config, var)]
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            return False
        
        # Initialize database
        logger.info("Initializing database...")
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        
        # Initialize service
        logger.info("Initializing Sales RAG service...")
        sales_rag_service = SalesRAGService(session_maker)
        
        # Connect to Salesforce
        logger.info("Connecting to Salesforce...")
        if not sales_rag_service.salesforce_client.connect():
            logger.error("Failed to connect to Salesforce")
            return False
        
        # Sync data
        force_resync = "--force" in sys.argv
        logger.info(f"Starting data sync (force_resync={force_resync})...")
        await sales_rag_service.sync_salesforce_data(force_resync=force_resync)
        
        logger.info("Data sync completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error during data sync: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 