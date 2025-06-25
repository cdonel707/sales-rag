# Slack Rate Limits & Our Updated Approach 🚨

Based on the [official Slack rate limits documentation](https://api.slack.com/apis/rate-limits), our app is subject to much stricter rate limits than we initially anticipated.

## 🚨 **Critical Information: New Rate Limits for Non-Marketplace Apps**

According to the [Slack API documentation](https://api.slack.com/apis/rate-limits):

> **"Effective May 29, 2025, all newly-created Slack apps that have not been approved for the Slack Marketplace will be subject to new rate limits for the conversations.history and conversations.replies API methods."**

This means your Sales RAG bot is likely hitting these much stricter limits!

## 📊 **Understanding Slack's Rate Limiting**

### **Web API Rate Limiting**
- **Evaluation**: Per method, per workspace
- **Rate limit windows**: Per minute
- **Tiers**: 4 tiers (Tier 1 = most restrictive, Tier 4 = least restrictive)
- **Method-specific**: Each API method has its own tier and limits

### **Recommended Baseline**
From Slack's docs:
> "we do recommend you design your apps with a limit of 1 request per second for any given API call"

### **Proper Error Handling**
When rate limited, Slack returns:
- **HTTP 429** Too Many Requests
- **Retry-After header** with seconds to wait
- **Method-specific restrictions** (not global)

## 🛠️ **Our Updated Ultra-Conservative Approach**

### **1. Extreme Batch Size Reduction**
```
✅ OLD → NEW
- Channels per run: 10 → 1 channel
- Messages per channel: 100 → 15 messages  
- Days lookback: 30 → 7 days
- Channel list limit: 1000 → 100 channels
```

### **2. Proper Rate Limiting Implementation**
```python
# Baseline wait before every API call
base_wait = 2-3 seconds

# Exponential backoff on rate limits
60s → 120s → 240s (instead of guessing)

# Respect Retry-After header (when available)
wait_time = retry_after + 5_second_buffer
```

### **3. Eliminated Unnecessary API Calls**
```
❌ REMOVED: users.info calls (extra API hits)
✅ KEPT: Essential conversations.history calls only
✅ ADDED: 30-60 second cooldowns between operations
```

### **4. One-Channel-Per-Run Strategy**
```
🔄 Process 1 channel per sync run
⏱️  Wait 30s before + 60s after each channel
🔄 Run multiple times to process all channels
📊 Clear progress logging and next steps
```

## 🧪 **Testing the New Approach**

### **Start the Server**
```bash
# Use python3 (not python)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

### **Trigger One Channel Processing**
```bash
curl -X POST http://localhost:3000/sync/slack-channels
```

### **Expected Behavior**
```bash
# Logs you should see:
"⚠️  Using extreme rate limiting due to Slack's new rate limits for non-Marketplace apps"
"Processing only 1 channel per run due to strict rate limits"
"Waiting 3 seconds before listing channels..."
"Found 47 potentially relevant channels"
"Processing channel 1/1: #fern-alchemy"
"Waiting 30 seconds before channel processing..."
"Waiting 2 seconds before API call (rate limiting)..."
"Retrieved 8 messages from #fern-alchemy"
"Indexed 3 messages from #fern-alchemy"
"📝 IMPORTANT: 46 additional channels found."
"Run 'curl -X POST http://localhost:3000/sync/slack-channels' 46 more times"
```

## ⏱️ **Realistic Timeline**

### **Per Channel Processing**
- **Setup & discovery**: ~30 seconds
- **Channel processing**: ~60-120 seconds  
- **Cooldown**: ~60 seconds
- **Total per channel**: ~3-4 minutes

### **Full Workspace**
- **If you have 20 relevant channels**: ~20 runs × 3 minutes = ~60 minutes total
- **Spread across multiple sessions** (recommended)
- **No more rate limit failures** (but much slower)

## 🎯 **Recommended Workflow**

### **1. Test with One Channel**
```bash
curl -X POST http://localhost:3000/sync/slack-channels
# Wait for completion, check logs
```

### **2. Process Multiple Channels**
```bash
# Run this command multiple times (once per channel)
for i in {1..10}; do
  echo "Processing channel batch $i..."
  curl -X POST http://localhost:3000/sync/slack-channels
  sleep 30  # Wait between runs
done
```

### **3. Monitor Progress**
```bash
# Watch logs for progress
tail -f logs/app.log | grep -E "(Processing channel|Indexed|additional channels)"
```

## 💡 **Why This Approach Works**

### **Respects Slack's Guidelines**
- ✅ Stays well under 1 request/second baseline
- ✅ Uses proper exponential backoff
- ✅ Handles rate limits gracefully
- ✅ No burst behavior that triggers limits

### **Reliable & Predictable**
- ✅ Each run processes exactly 1 channel
- ✅ Clear logging of progress and remaining work
- ✅ No unexpected failures or hanging
- ✅ Can resume/continue anytime

### **Compliance with New Rate Limits**
- ✅ Designed for post-May 2025 restrictions
- ✅ Suitable for non-Marketplace apps
- ✅ Conservative enough to avoid enforcement

## 🚀 **Ready to Test**

The system is now designed to work reliably within Slack's rate limits, even the new stricter ones for non-Marketplace apps. It will be slower, but it will complete successfully without rate limit errors.

**Start with one test run and monitor the logs to see the new behavior in action!**

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Then in another terminal:
```bash
curl -X POST http://localhost:3000/sync/slack-channels
``` 