#!/usr/bin/env python3
"""
Test script for cross-channel Slack functionality with conservative rate limiting
Run this after the server is started to test cross-channel search

Note: If you get "command not found: python", use "python3" instead:
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
"""

import requests
import json
import time

# Configuration
SERVER_URL = "http://localhost:3000"

def test_health():
    """Test if the server is healthy"""
    print("🏥 Testing server health...")
    try:
        response = requests.get(f"{SERVER_URL}/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Server is healthy")
            print(f"   Cross-channel index: {'✅' if health_data['services'].get('cross_channel_index') else '❌'}")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print(f"💡 Make sure you started the server with:")
        print(f"   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload")
        return False

def trigger_cross_channel_sync():
    """Trigger comprehensive Slack indexing"""
    print("\n🔄 Triggering comprehensive Slack indexing...")
    print("🚀 NEW: Comprehensive approach - indexes ALL public channels!")
    print("   - No complex company matching needed")
    print("   - Processes 2 channels per run")
    print("   - Up to 50 messages per channel")
    print("   - 14 days lookback")
    print("   - ~8-10 minutes per run")
    print("   - Semantic search finds relevance at query time")
    
    try:
        response = requests.post(f"{SERVER_URL}/sync/slack-channels")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ {data['message']}")
            print(f"   {data['status']}")
            return True
        else:
            print(f"❌ Comprehensive indexing failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error triggering sync: {e}")
        return False

def test_company_search(company_name="Zillow"):
    """Test searching for a specific company across channels"""
    print(f"\n🔍 Testing company search for '{company_name}'...")
    try:
        response = requests.post(
            f"{SERVER_URL}/search",
            params={"query": f"Tell me about {company_name}"}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search completed")
            print(f"   Answer: {data.get('answer', 'No answer')[:100]}...")
            
            sources = data.get('sources', [])
            print(f"   Found {len(sources)} sources:")
            
            slack_sources = [s for s in sources if s.get('type') == 'slack']
            sf_sources = [s for s in sources if s.get('type') == 'salesforce']
            
            print(f"     - Slack messages: {len(slack_sources)}")
            print(f"     - Salesforce records: {len(sf_sources)}")
            
            # Show some source details
            for i, source in enumerate(sources[:3]):
                if source.get('type') == 'slack':
                    print(f"     📱 Slack #{source.get('channel', 'unknown')} by {source.get('user', 'unknown')}")
                elif source.get('type') == 'salesforce':
                    print(f"     🏢 Salesforce {source.get('object_type', 'record')}: {source.get('title', 'Unknown')}")
            
            return True
        else:
            print(f"❌ Search failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error during search: {e}")
        return False

def test_cross_channel_queries():
    """Test various cross-channel queries"""
    queries = [
        "What opportunities do we have with companies in our Slack channels?",
        "Show me any Slack discussions about deals", 
        "Any updates mentioned in relevant channels?",
    ]
    
    print(f"\n🧪 Testing {len(queries)} cross-channel queries...")
    results = []
    
    for i, query in enumerate(queries, 1):
        print(f"\n   Query {i}: {query}")
        try:
            response = requests.post(
                f"{SERVER_URL}/search",
                params={"query": query}
            )
            if response.status_code == 200:
                data = response.json()
                sources = data.get('sources', [])
                slack_count = len([s for s in sources if s.get('type') == 'slack'])
                sf_count = len([s for s in sources if s.get('type') == 'salesforce'])
                
                print(f"   ✅ Found {len(sources)} sources ({slack_count} Slack, {sf_count} Salesforce)")
                results.append({
                    'query': query,
                    'total_sources': len(sources),
                    'slack_sources': slack_count,
                    'salesforce_sources': sf_count
                })
            else:
                print(f"   ❌ Query failed: {response.status_code}")
                results.append({'query': query, 'error': True})
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({'query': query, 'error': True})
    
    return results

def main():
    """Main test function"""
    print("🚀 Sales RAG Comprehensive Slack Indexing Test")
    print("=" * 70)
    print("📋 NEW APPROACH: Index ALL public channels systematically")
    print("   - Simple & reliable")
    print("   - Comprehensive coverage")
    print("   - Better semantic search")
    print("   - Respects Slack rate limits")
    print("=" * 70)
    
    # Test server health
    if not test_health():
        print("\n❌ Server is not healthy. Please start the server first with:")
        print("   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload")
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Trigger comprehensive indexing
    if trigger_cross_channel_sync():
        print("\n⏳ Comprehensive Slack indexing is now running:")
        print("   - Processing ALL public channels systematically")
        print("   - 2 channels per run (conservative rate limiting)")
        print("   - No company filtering - indexes ALL messages")
        print("   - Semantic search handles relevance at query time")
        print("   - This run will take ~8-10 minutes for 2 channels")
        print("\n   Waiting 5 minutes for first batch to complete...")
        print("   (You can watch logs in another terminal)")
        time.sleep(300)  # Wait 5 minutes for first batch
    
    # Test searches that should work with comprehensive indexing
    test_comprehensive_searches()
    
    # Test various queries
    results = test_cross_channel_queries()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Comprehensive Indexing Test Summary")
    successful_queries = [r for r in results if not r.get('error')]
    total_slack_sources = sum(r.get('slack_sources', 0) for r in successful_queries)
    total_sf_sources = sum(r.get('salesforce_sources', 0) for r in successful_queries)
    
    print(f"✅ Successful queries: {len(successful_queries)}/{len(results)}")
    print(f"📱 Total Slack sources found: {total_slack_sources}")
    print(f"🏢 Total Salesforce sources found: {total_sf_sources}")
    
    if total_slack_sources > 0:
        print("\n🎉 Comprehensive indexing is working! Finding Slack conversations.")
        print("   The system is now indexing ALL channels systematically.")
    else:
        print("\n⚠️  No Slack sources found yet. This is normal for the new approach:")
        print("   - Comprehensive indexing takes longer but is more thorough")
        print("   - Each run processes 2 channels (rate limit compliance)")
        print("   - Run multiple times until all channels are processed")
        print("   - Check logs for 'Indexed X messages' confirmations")
    
    print(f"\n💡 Next Steps:")
    print(f"   1. Monitor logs: tail -f logs/app.log | grep 'Indexed'")
    print(f"   2. Continue indexing until all channels processed:")
    print(f"      for i in {{1..10}}; do")
    print(f"        curl -X POST {SERVER_URL}/sync/slack-channels")
    print(f"        sleep 600  # Wait 10 minutes between runs")
    print(f"      done")
    print(f"   3. Once complete, semantic search will find ALL relevant content")
    print(f"   4. Test searches: curl -X POST \"{SERVER_URL}/search?query=your_query\"")

def test_comprehensive_searches():
    """Test searches that should benefit from comprehensive indexing"""
    print("\n🧪 Testing Comprehensive Search Capabilities")
    print("-" * 50)
    
    # These searches should work better with comprehensive indexing
    comprehensive_queries = [
        "team discussions about documentation",
        "recent api changes or updates", 
        "customer feedback or issues",
        "integration challenges",
        "onboarding questions"
    ]
    
    for query in comprehensive_queries:
        print(f"\n🔍 Testing: '{query}'")
        try:
            response = requests.post(f"{SERVER_URL}/search", params={"query": query})
            if response.status_code == 200:
                data = response.json()
                slack_sources = len([s for s in data.get('sources', []) if s.get('type') == 'slack'])
                sf_sources = len([s for s in data.get('sources', []) if s.get('type') == 'salesforce'])
                print(f"   ✅ Found {slack_sources} Slack + {sf_sources} Salesforce sources")
                if slack_sources > 0:
                    print(f"   📱 Slack channels: {list(set([s.get('metadata', {}).get('channel_name', 'unknown') for s in data.get('sources', []) if s.get('type') == 'slack']))}")
            else:
                print(f"   ❌ Search failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    main() 