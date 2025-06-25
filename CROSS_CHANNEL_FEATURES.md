# Cross-Channel Slack Search Features 🔍

The Sales RAG bot now includes advanced cross-channel search capabilities that automatically discover and index relevant Slack conversations across your entire workspace.

## 🚀 How It Works

### 1. **Automatic Channel Discovery**
- Scans all public channels in your Slack workspace
- Identifies channels with company names in their titles (e.g., #zillow-project, #microsoft-deal)
- Matches channel names against your Salesforce account names

### 2. **Smart Entity Extraction**  
- Analyzes Slack messages for mentions of:
  - Company names from Salesforce
  - Contact names (FirstName LastName)
  - Opportunity names
- Only indexes messages that contain relevant business entities

### 3. **Enhanced Search Integration**
- When you ask about a company, searches both Salesforce AND relevant Slack conversations
- Prioritizes company-specific results from cross-channel data
- Provides unified answers combining structured Salesforce data with conversational Slack context

## 🎯 Key Features

### **Intelligent Message Filtering**
- Skips bot messages and system notifications
- Focuses on messages containing business-relevant entities
- Looks back 60 days for relevant conversations

### **Auto-Channel Joining**
- Bot automatically joins relevant channels when possible (requires `channels:join` permission)
- Gracefully handles private channels and access restrictions
- Falls back to available channels if join fails

### **Context-Aware Responses**
- Understands company mentions in questions like "What's the status on Zillow?"
- Connects Slack discussions to Salesforce records
- Provides sources from both systems in responses

## 📊 What Gets Indexed

### **From Slack:**
- Messages mentioning company names from Salesforce
- Messages mentioning contact names 
- Messages mentioning opportunity names
- User information (name, channel context)
- Thread context and relationships

### **Metadata Captured:**
- Channel name and ID
- User name and ID
- Message timestamp
- Thread relationships
- Entity mentions (companies, contacts, opportunities)

## 🔧 API Endpoints

### **Manual Sync Trigger**
```bash
POST /sync/slack-channels
```
Manually triggers cross-channel discovery and indexing.

### **Enhanced Search**
```bash
POST /search?query=Tell me about Zillow
```
Searches across both Salesforce and indexed Slack conversations.

### **Health Check**
```bash
GET /health
```
Now includes `cross_channel_index` status showing if entity cache is populated.

## 🧪 Testing

Run the included test script to verify functionality:

```bash
python test_cross_channel.py
```

This will:
1. Check server health
2. Trigger cross-channel indexing
3. Test company-specific searches
4. Verify Slack sources are found

## 💡 Usage Examples

### **In Slack:**
```
/sales What opportunities do we have with Zillow?
```
**Response includes:**
- Salesforce opportunity records
- Recent Slack discussions about Zillow
- Combined insights from both sources

### **Company-Specific Questions:**
```
/sales Any updates on the Microsoft deal?
```
**Searches:**
- Salesforce Microsoft account/opportunities
- #microsoft-deal channel (if exists)
- Messages mentioning "Microsoft" across channels

### **Pipeline Discussions:**
```
/sales What are people saying about our Q4 pipeline in Slack?
```
**Finds:**
- Messages mentioning opportunity names
- Discussions in sales-related channels
- Context from deal-specific conversations

## ⚙️ Configuration

### **Channel Discovery Rules:**
- Company name must be 4+ characters
- Matches against cleaned channel names (removes special chars)
- Case-insensitive matching

### **Message Indexing Limits:**
- 500 messages per channel maximum
- 60 days lookback period
- Only messages with detected entities
- 2-second delay between channels (rate limiting)

### **Entity Cache:**
- Updates on service initialization
- Includes all Salesforce accounts, contacts, opportunities
- Can be refreshed via sync endpoints

## 🔒 Privacy & Security

### **Access Control:**
- Respects Slack channel permissions
- Only indexes public channels by default
- Bot must be invited to private channels
- Handles permission errors gracefully

### **Data Storage:**
- Slack messages stored in local vector database
- Same security model as Salesforce data
- No external data transmission beyond OpenAI embeddings

## 🚨 Troubleshooting

### **No Slack Sources Found:**
1. Check if relevant channels exist with company names
2. Verify bot has `channels:join` permission
3. Ensure channels contain messages with company mentions
4. Check bot is added to private channels manually

### **Indexing Issues:**
1. Monitor logs during `/sync/slack-channels`
2. Verify Salesforce entity cache is populated
3. Check for API rate limiting errors
4. Ensure sufficient time for indexing completion

### **Search Not Finding Slack Data:**
1. Verify cross-channel indexing completed successfully
2. Check entity cache has company names loaded
3. Test with specific company names that exist in channels
4. Review search logs for filtering issues

## 📈 Performance Notes

- Initial indexing may take several minutes for large workspaces
- Vector search performance scales with indexed message count
- Rate limiting prevents Slack API overload
- Background processing avoids blocking user requests

The cross-channel search transforms your Sales RAG bot from a Salesforce-only tool into a comprehensive sales intelligence system that understands the full context of your business conversations. 