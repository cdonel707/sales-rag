import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Slack Configuration
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # For bot interactions
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")  # For data syncing (your personal token)
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
    
    # Salesforce Configuration
    SALESFORCE_USERNAME = os.getenv("SALESFORCE_USERNAME")
    SALESFORCE_PASSWORD = os.getenv("SALESFORCE_PASSWORD")
    SALESFORCE_SECURITY_TOKEN = os.getenv("SALESFORCE_SECURITY_TOKEN")
    SALESFORCE_DOMAIN = os.getenv("SALESFORCE_DOMAIN")
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Application Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 3000))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sales_rag.db")

config = Config() 