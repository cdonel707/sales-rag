# 🔑 User Token Setup Guide

## Why Use a User Token?

The enhanced Sales RAG bot now supports **dual-client architecture**:

- **User Token (SLACK_USER_TOKEN)**: For data syncing - no channel joining needed!
- **Bot Token (SLACK_BOT_TOKEN)**: For user interactions only

## Benefits of User Token Approach

✅ **No Channel Joining**: Your personal token already has access to channels you're in
✅ **Less Intrusive**: Bot only joins channels when users explicitly interact with it  
✅ **Better Rate Limits**: User tokens often have different (better) rate limits
✅ **Cleaner Architecture**: Separate concerns for sync vs interaction

## How to Get Your User Token

### Step 1: Go to Your Slack App
- Visit [api.slack.com/apps](https://api.slack.com/apps)
- Select your Sales RAG bot app

### Step 2: Add User Token Scopes
- Go to **OAuth & Permissions** in the left sidebar
- Scroll down to **User Token Scopes**
- Add these scopes:
  - `channels:read` - Read basic channel info
  - `channels:history` - Read channel message history
  - `groups:history` - Read private channel history (if needed)

### Step 3: Install & Get Token
- Click **Install App to Workspace** (or **Reinstall** if already installed)
- Copy the **User OAuth Token** (starts with `xoxp-`)

### Step 4: Add to Environment
Add this to your `.env` file:
```
SLACK_USER_TOKEN=xoxp-your-user-token-here
```

## What This Enables

- **Data Syncing**: Bot can read all channels you're in without joining them
- **Smart Interactions**: Bot only joins channels when users use `/sales` command
- **Better Performance**: No "not_in_channel" errors during sync
- **Cleaner Logs**: No spam from joining/leaving channels

## Fallback Behavior

If you don't set `SLACK_USER_TOKEN`, the bot will use the bot token for both syncing and interactions (less efficient but still works).

## Testing the Setup

1. Start your bot: `python3 start.py`
2. Look for this message: `🔑 Dual-token setup detected`
3. Run manual sync: `POST /sync/slack-channels`
4. You should see: `📊 Syncing with user account (no joining required)`

That's it! Your bot now has intelligent, non-intrusive access to your Slack data. 🎉 