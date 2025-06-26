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
    
    # Check for required environment variables directly (works for both Railway and local)
    required_vars = [
        'SLACK_BOT_TOKEN',
        'SLACK_SIGNING_SECRET', 
        'SALESFORCE_USERNAME',
        'SALESFORCE_PASSWORD',
        'SALESFORCE_SECURITY_TOKEN',
        'OPENAI_API_KEY'
    ]
    
    # Check for optional but recommended variables
    optional_vars = ['SLACK_USER_TOKEN', 'FATHOM_API_KEY']
    
    missing_vars = []
    for var in required_vars:
        if not getattr(config, var, None):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        
        # Different messages for local vs Railway
        if os.path.exists('.env'):
            print("\nPlease add these variables to your .env file.")
        else:
            print("\nPlease configure these environment variables in Railway.")
        return
    
    print("✅ Required configuration found!")
    
    # Check optional services
    available_optional = []
    for var in optional_vars:
        if getattr(config, var, None):
            available_optional.append(var)
    
    if available_optional:
        print(f"🔑 Optional services enabled: {', '.join(available_optional)}")
    
    # Show token configuration status
    user_token_available = getattr(config, 'SLACK_USER_TOKEN', None)
    fathom_available = getattr(config, 'FATHOM_API_KEY', None)
    
    if user_token_available:
        print("🎯 Dual-token setup detected - optimal for data syncing!")
    
    if fathom_available:
        print("📞 Fathom integration enabled - call transcripts available!")
    
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