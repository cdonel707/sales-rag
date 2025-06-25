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