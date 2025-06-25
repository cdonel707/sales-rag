#!/usr/bin/env python3
"""
Test script for conversation memory management features
"""

import requests
import json
import time

SERVER_URL = "http://localhost:3000"

def test_conversation_memory():
    """Test the conversation memory management features"""
    
    print("🧪 Testing Conversation Memory Management\n")
    
    # Test 1: Check if server is running
    print("1️⃣ Testing server health...")
    try:
        response = requests.get(f"{SERVER_URL}/health")
        if response.status_code == 200:
            print("   ✅ Server is running")
        else:
            print("   ❌ Server health check failed")
            return False
    except Exception as e:
        print(f"   ❌ Cannot connect to server: {e}")
        return False
    
    # Test 2: Test search functionality (to generate conversation history)
    print("\n2️⃣ Testing search to generate conversation history...")
    try:
        response = requests.post(f"{SERVER_URL}/search?query=zillow")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Search successful - found {data.get('context_used', 0)} relevant documents")
            print(f"   📝 Response: {data.get('answer', '')[:100]}...")
        else:
            print(f"   ❌ Search failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Search test failed: {e}")
        return False
    
    # Test 3: Test another search (should reference previous context)
    print("\n3️⃣ Testing second search (should have conversation context)...")
    try:
        response = requests.post(f"{SERVER_URL}/search?query=tell%20me%20more%20about%20zillow")
        if response.status_code == 200:
            data = response.json()
            answer = data.get('answer', '')
            print(f"   ✅ Second search successful")
            print(f"   📝 Response: {answer[:100]}...")
            
            # Check if response might reference previous conversation
            if 'previous' in answer.lower() or 'mentioned' in answer.lower() or 'earlier' in answer.lower():
                print("   🔍 Response appears to reference previous context")
            else:
                print("   ℹ️  Response doesn't clearly reference previous context")
        else:
            print(f"   ❌ Second search failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Second search test failed: {e}")
        return False
    
    print("\n🎯 Manual Testing Required:")
    print("   The conversation memory management features are Slack-specific and require:")
    print("   1. Using `/sales` command in Slack")
    print("   2. Asking questions through the Slack interface")
    print("   3. Testing the 'Clear History' and 'End Session' buttons")
    
    print("\n📋 Test Steps:")
    print("   1. In Slack, run: `/sales`")
    print("   2. Click 'Chat' and ask: 'Tell me about Zillow'")
    print("   3. Ask follow-up: 'What's the deal amount?'")
    print("   4. Click 'Clear History' button")
    print("   5. Ask again: 'Tell me about Zillow'")
    print("   6. Verify the response doesn't reference previous conversation")
    
    print("\n✅ Expected Behavior:")
    print("   - Before clearing: Bot references previous context")
    print("   - After clearing: Bot responds as if first time asking")
    print("   - 'End Session' should also clear conversation history")
    
    return True

def test_database_conversation_records():
    """Test if conversation records are being stored properly"""
    print("\n🗄️  Testing Database Conversation Storage:")
    print("   Note: This requires direct database access to verify")
    print("   The conversation history is stored in the 'conversations' table")
    print("   with fields: slack_channel_id, slack_user_id, question, answer")
    
    return True

if __name__ == "__main__":
    print("🚀 Starting Conversation Memory Management Tests\n")
    
    success = test_conversation_memory()
    test_database_conversation_records()
    
    if success:
        print("\n🎉 Basic tests passed!")
        print("💡 Remember to test the Slack interface features manually")
    else:
        print("\n❌ Some tests failed!")
    
    print("\n📖 See CONVERSATION_MEMORY_MANAGEMENT.md for full documentation") 