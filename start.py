#!/usr/bin/env python3
"""
Simple startup script for the Sales RAG Slack Bot
"""

import os
import sys
import uvicorn
from app.config import config

def main():
    """Main startup function"""
    print("🚀 Starting Sales RAG Slack Bot...")
    print(f"📡 Server will run on {config.HOST}:{config.PORT}")
    print(f"🔧 Debug mode: {'ON' if config.DEBUG else 'OFF'}")
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("⚠️  Warning: .env file not found!")
        print("Please create a .env file with your configuration.")
        print("See .env.example for reference.")
        return
    
    # Check for required environment variables
    required_vars = [
        'SLACK_BOT_TOKEN',
        'SLACK_SIGNING_SECRET',
        'SALESFORCE_USERNAME',
        'SALESFORCE_PASSWORD',
        'SALESFORCE_SECURITY_TOKEN',
        'OPENAI_API_KEY'
    ]
    
    # Check for optional but recommended user token
    user_token_available = getattr(config, 'SLACK_USER_TOKEN', None)
    
    missing_vars = []
    for var in required_vars:
        if not getattr(config, var, None):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease configure these in your .env file.")
        return
    
    print("✅ Configuration looks good!")
    
    # Show token configuration status
    if user_token_available:
        print("🔑 Dual-token setup detected:")
        print("   - SLACK_BOT_TOKEN: For bot interactions")
        print("   - SLACK_USER_TOKEN: For data syncing (no channel joining needed!)")
    else:
        print("⚠️  Single-token setup:")
        print("   - SLACK_BOT_TOKEN: For both interactions and syncing")
        print("   - Consider adding SLACK_USER_TOKEN for better data access")
        print("   - See README for user token setup instructions")
    
    print("🔄 Starting application...")
    
    # Start the server
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info" if not config.DEBUG else "debug"
    )

if __name__ == "__main__":
    main() 