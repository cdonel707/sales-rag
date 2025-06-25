# 🔍 Zillow Search Issue Debug Guide

## 🚨 **The Problem**

When asking "What is the exact last slack message that was related to zillow", the bot returns a synthesized response that mentions:
- Strategic planning and management efforts for partnership with Zillow
- "testing UI" discussions
- NDA execution and next steps
- References to previous conversations that may not be about Zillow

This suggests **conversation contamination** where unrelated context is being mixed with Zillow searches.

## 🛠️ **Step-by-Step Debug Process**

### **Step 1: Clear Conversation History**
```
1. In Slack, type: /sales
2. Click: 🧹 Clear History
3. Ask again: "What is the exact last slack message that was related to zillow"
4. Check if the response is different/cleaner
```

### **Step 2: Run Debug Script**
```bash
python3 debug_zillow_search.py
```

This will show you:
- ✅ What's actually in your vector database for Zillow
- ✅ Whether there's contaminated data
- ✅ What sources are being returned (Slack vs Salesforce)
- ✅ Whether suspicious "testing UI" content exists

### **Step 3: Check Raw Data**
The debug script will help identify if:
- 🔍 **Vector Database Issue**: Non-Zillow content tagged as Zillow-related
- 🔍 **Conversation History Issue**: Old conversations bleeding into new ones
- 🔍 **Entity Recognition Issue**: Wrong company matching

## 🎯 **Expected Debug Results**

### **✅ If Working Correctly:**
```
📊 Found X results for 'Zillow':
--- Result 1 ---
Source: salesforce
Object Type: Opportunity
Title: Zillow Partnership
Content: Opportunity: Zillow Partnership, Account: Zillow...

--- Result 2 ---
Source: slack
Channel: #sales-updates
Content: Update on Zillow deal status...
```

### **🚨 If There's Contamination:**
```
--- Result 1 ---
Source: slack
Channel: #general
Content: Let's update the testing UI for better user experience...
🚨 SUSPICIOUS: This content contains 'testing UI' or 'strategic planning'
```

## 🔧 **Fixes Based on Debug Results**

### **Fix 1: Clear Contaminated Vector Data**
If debug shows contaminated data:

```python
# Clear and rebuild vector database
from app.rag.embeddings import EmbeddingService
embedding_service = EmbeddingService(openai_api_key, "./chroma_db")
# Delete collections and rebuild
```

### **Fix 2: Improve Entity Recognition** 
If wrong content is being tagged as Zillow-related:

```python
# Check entity cache
companies = list(service.embedding_service.company_cache)
zillow_companies = [c for c in companies if 'zillow' in c.lower()]
print(f"Zillow companies: {zillow_companies}")
```

### **Fix 3: Force Fresh Search**
Try a more specific query:
- Instead of: "zillow"
- Try: "Zillow slack messages channel:sales-updates"

## 🧪 **Testing Different Scenarios**

### **Test 1: Direct API Search**
```bash
curl -X POST "http://localhost:3000/search?query=zillow&source=slack" | jq '.'
```

### **Test 2: Salesforce Only**
```bash
curl -X POST "http://localhost:3000/search?query=zillow&source=salesforce" | jq '.'
```

### **Test 3: Clean Session**
1. Clear history completely
2. Ask very specific: "Show me the most recent Slack message that mentions Zillow company"

## 🎯 **Root Cause Analysis**

### **Likely Causes:**
1. **Conversation Memory**: Old "testing UI" conversations stored in database
2. **Vector Contamination**: Messages about UI testing incorrectly associated with Zillow
3. **Entity Overlap**: "Zillow" mentioned in unrelated conversations about UI
4. **Semantic Search**: OpenAI embeddings finding false similarities

### **Quick Verification:**
```sql
-- Check what's in the conversation database
SELECT * FROM conversations 
WHERE question LIKE '%zillow%' OR answer LIKE '%zillow%' 
ORDER BY created_at DESC LIMIT 5;
```

## 🚀 **Immediate Actions**

### **For User:**
1. ✅ Run the debug script first
2. ✅ Clear conversation history in Slack
3. ✅ Try asking more specific questions like "Show me Zillow Salesforce records"

### **For Developer:**
1. ✅ Check debug script output for contamination
2. ✅ Verify entity cache has correct Zillow entries
3. ✅ Consider rebuilding vector database if heavily contaminated

## 📝 **Prevention for Future**

### **Better Query Patterns:**
- ❌ "Tell me about Zillow" (too broad)
- ✅ "Show me Zillow Salesforce opportunity"
- ✅ "Find Slack messages in #sales mentioning Zillow"
- ✅ "What's the status of Zillow deal"

### **Regular Cleanup:**
- Clear conversation history regularly
- Use specific channel filters
- Verify vector database quality periodically

---

**Run the debug script and let me know what it shows - this will help pinpoint exactly what's causing the contaminated responses!** 🔍 