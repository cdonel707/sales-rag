#!/usr/bin/env python3
"""
Debug script to check what's actually being returned when searching for Zillow
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def debug_zillow_search():
    """Debug what's actually in the vector database for Zillow"""
    try:
        from app.services import SalesRAGService
        from app.database.models import create_database, get_session_maker
        from app.config import config
        
        logger.info("🔍 Debugging Zillow search results...")
        
        # Initialize database (same as main.py)
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        
        # Initialize service
        service = SalesRAGService(session_maker)
        
        # Initialize service
        await service.initialize()
        
        # Test direct search without conversation history
        print("\n1️⃣ Testing direct Zillow search (no conversation history)...")
        
        # Search for Zillow with no filters
        results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=5,
            source_filter=None,
            company_filter="zillow"
        )
        
        print(f"\n📊 Found {len(results)} results for 'Zillow':")
        
        for i, result in enumerate(results):
            print(f"\n--- Result {i+1} ---")
            print(f"Source: {result.get('source', 'unknown')}")
            print(f"Distance: {result.get('distance', 'unknown')}")
            
            metadata = result.get('metadata', {})
            content = result.get('content', '')
            
            if result.get('source') == 'slack':
                print(f"Channel: #{metadata.get('channel_name', 'unknown')}")
                print(f"User: {metadata.get('user_name', 'unknown')}")
                print(f"Timestamp: {metadata.get('ts', 'unknown')}")
            elif result.get('source') == 'salesforce':
                print(f"Object Type: {metadata.get('object_type', 'unknown')}")
                print(f"Record ID: {metadata.get('record_id', 'unknown')}")
                print(f"Title: {metadata.get('title', 'unknown')}")
            
            print(f"Content: {content[:200]}...")
            
            # Check if this content contains the suspicious "testing UI" text
            if "testing ui" in content.lower() or "strategic planning" in content.lower():
                print("🚨 SUSPICIOUS: This content contains 'testing UI' or 'strategic planning'")
        
        # Test Salesforce-only search
        print("\n2️⃣ Testing Salesforce-only search for Zillow...")
        
        sf_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=3,
            source_filter="salesforce"
        )
        
        print(f"\n📊 Found {len(sf_results)} Salesforce results:")
        for i, result in enumerate(sf_results):
            content = result.get('content', '')
            print(f"\nSalesforce Result {i+1}: {content[:150]}...")
        
        # Test Slack-only search
        print("\n3️⃣ Testing Slack-only search for Zillow...")
        
        slack_results = service.embedding_service.search_similar_content(
            query="Zillow",
            n_results=3,
            source_filter="slack"
        )
        
        print(f"\n📊 Found {len(slack_results)} Slack results:")
        for i, result in enumerate(slack_results):
            content = result.get('content', '')
            metadata = result.get('metadata', {})
            print(f"\nSlack Result {i+1} from #{metadata.get('channel_name', 'unknown')}: {content[:150]}...")
        
        # Test company search
        print("\n4️⃣ Testing specific company search...")
        
        company_results = service.embedding_service.search_by_company("zillow", n_results=3)
        
        print(f"\n📊 Found {len(company_results)} company-specific results:")
        for i, result in enumerate(company_results):
            content = result.get('content', '')
            source = result.get('source', 'unknown')
            print(f"\nCompany Result {i+1} ({source}): {content[:150]}...")
        
        # Check entity cache
        print("\n5️⃣ Checking entity cache...")
        companies = list(service.embedding_service.company_cache)
        zillow_companies = [c for c in companies if 'zillow' in c.lower()]
        print(f"Zillow-related companies in cache: {zillow_companies}")
        
        # Test actual search as would be used in Slack
        print("\n6️⃣ Testing full search pipeline (simulating Slack query)...")
        
        full_result = await service.search_sales_data(
            query="What is the exact last slack message that was related to zillow",
            source_filter=None
        )
        
        print(f"\nFull search result:")
        print(f"Answer: {full_result.get('answer', '')[:300]}...")
        print(f"Context used: {full_result.get('context_used', 0)}")
        print(f"Sources: {len(full_result.get('sources', []))}")
        
        # Check if the answer contains suspicious content
        answer = full_result.get('answer', '').lower()
        if "testing ui" in answer or "strategic planning" in answer:
            print("🚨 FULL PIPELINE CONTAMINATION: Answer contains suspicious content!")
        
        print("\n✅ Debug completed!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(debug_zillow_search())
    sys.exit(0 if success else 1) 