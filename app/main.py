from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager

from .database.models import create_database, get_session_maker
from .services import SalesRAGService
from .config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global service instance
sales_rag_service = None

# Removed async function - now using full Slack Bolt integration

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global sales_rag_service
    
    logger.info("Starting Sales RAG Application...")
    
    try:
        # Initialize database
        engine = create_database(config.DATABASE_URL)
        session_maker = get_session_maker(engine)
        
        # Initialize service
        sales_rag_service = SalesRAGService(session_maker)
        
        # Initialize and sync data
        await sales_rag_service.initialize()
        
        logger.info("Application startup completed successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        raise
    finally:
        logger.info("Application shutdown completed")

# Create FastAPI app
app = FastAPI(
    title="Sales RAG Slack Bot",
    description="A Slack bot that provides RAG-based answers from Salesforce and Slack data",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    health_status = await sales_rag_service.health_check()
    
    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

# Slack events endpoint - full Slack Bolt integration
@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle all Slack events through Slack Bolt"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Get the Slack handler and delegate to it
        slack_handler = sales_rag_service.get_slack_handler()
        return await slack_handler.handle(request)
        
    except Exception as e:
        logger.error(f"Error handling Slack request: {e}")
        return {"text": "Sorry, I encountered an error processing your request. Please try again."}

# Manual data sync endpoint
@app.post("/sync/salesforce")
async def sync_salesforce_data(background_tasks: BackgroundTasks, force: bool = False):
    """Manually trigger Salesforce data sync"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    background_tasks.add_task(sales_rag_service.sync_salesforce_data, force)
    
    return {
        "message": "Salesforce data sync started",
        "force_resync": force
    }

# Cross-channel indexing endpoint
@app.post("/sync/slack-channels")
async def sync_slack_channels(background_tasks: BackgroundTasks):
    """Manual sync of Slack channels (processes small batch for testing)"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    background_tasks.add_task(sales_rag_service.discover_and_index_slack_channels)
    
    return {
        "message": "Manual Slack sync started (small batch)",
        "status": "Processes 2 channels for testing. Use /sync/slack-automated for full initial sync"
    }

# Automated initial sync endpoint
@app.post("/sync/slack-automated")
async def sync_slack_automated():
    """Start automated initial sync that processes all channels continuously"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    await sales_rag_service.start_automated_initial_sync()
    
    return {
        "message": "Automated initial Slack sync started",
        "status": "Background process will continuously sync all channels. Check logs for progress.",
        "config": {
            "channels_per_batch": 5,
            "delay_between_batches": "45 seconds",
            "messages_per_channel": 50,
            "lookback_days": 30,
            "max_channels": 100
        }
    }

# Real-time mode control
@app.post("/enable-realtime")
async def enable_realtime_mode():
    """Enable real-time indexing of new Slack messages"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Enable real-time message indexing
    sales_rag_service.slack_handler.enable_realtime_indexing()
    
    return {
        "message": "Real-time Slack indexing enabled",
        "status": "New messages will be automatically indexed as they're posted"
    }

# Search endpoint for testing
@app.post("/search")
async def search_sales_data(query: str, source_filter: str = None):
    """Search sales data (for testing purposes)"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    result = await sales_rag_service.search_sales_data(
        query=query,
        source_filter=source_filter
    )
    
    return result

# Debug endpoint for checking entity cache
@app.get("/debug/entities")
async def debug_entities():
    """Debug endpoint to check entity cache contents"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    embedding_service = sales_rag_service.embedding_service
    
    return {
        "company_cache_size": len(embedding_service.company_cache),
        "contact_cache_size": len(embedding_service.contact_cache),
        "opportunity_cache_size": len(embedding_service.opportunity_cache),
        "sample_companies": list(embedding_service.company_cache)[:10],
        "sample_contacts": list(embedding_service.contact_cache)[:5],
        "sample_opportunities": list(embedding_service.opportunity_cache)[:5]
    }

# Write operation endpoint for testing
@app.post("/write")
async def execute_write_operation(parsed_command: dict):
    """Execute a write operation (for testing purposes)"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not parsed_command:
        raise HTTPException(status_code=400, detail="Parsed command cannot be empty")
    
    result = await sales_rag_service.execute_write_operation(parsed_command)
    
    return result

# Fathom meeting search endpoints
from pydantic import BaseModel

class FathomCompanySearchRequest(BaseModel):
    company_name: str
    limit: int = 10

class FathomQuerySearchRequest(BaseModel):
    query: str
    limit: int = 10

class FathomSalesforceSearchRequest(BaseModel):
    company_name: str
    limit: int = 10

@app.post("/fathom/search-company")
async def search_fathom_by_company(request: FathomCompanySearchRequest):
    """Search Fathom meetings by company name (legacy method)"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not sales_rag_service.fathom_client.is_available():
        raise HTTPException(status_code=503, detail="Fathom integration not available")
    
    if not request.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name cannot be empty")
    
    try:
        meetings = await sales_rag_service.fathom_client.search_meetings_by_company(
            request.company_name, limit=request.limit
        )
        
        return {
            "company": request.company_name,
            "method": "legacy_company_search",
            "meetings_found": len(meetings),
            "meetings": meetings
        }
    except Exception as e:
        logger.error(f"Error searching Fathom meetings for company {request.company_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching meetings: {str(e)}")

@app.post("/fathom/search-salesforce-integrated")
async def search_fathom_by_salesforce_contacts(request: FathomSalesforceSearchRequest):
    """Search Fathom meetings using Salesforce contact emails (enhanced method)"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not sales_rag_service.fathom_client.is_available():
        raise HTTPException(status_code=503, detail="Fathom integration not available")
    
    if not request.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name cannot be empty")
    
    try:
        meetings = await sales_rag_service.fathom_client.search_meetings_by_salesforce_contacts(
            salesforce_client=sales_rag_service.salesforce_client,
            company_name=request.company_name,
            limit=request.limit
        )
        
        # Extract matched emails for debugging
        matched_emails = [m.get('_matched_email', '') for m in meetings if m.get('_matched_email')]
        
        return {
            "company": request.company_name,
            "method": "salesforce_integrated_search",
            "meetings_found": len(meetings),
            "matched_emails": list(set(matched_emails)),  # Unique emails that matched
            "meetings": meetings
        }
    except Exception as e:
        logger.error(f"Error searching Fathom meetings via Salesforce for company {request.company_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching meetings: {str(e)}")

@app.post("/fathom/search-query")
async def search_fathom_by_query(request: FathomQuerySearchRequest):
    """Search Fathom meetings by general query"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not sales_rag_service.fathom_client.is_available():
        raise HTTPException(status_code=503, detail="Fathom integration not available")
    
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        meetings = await sales_rag_service.fathom_client.search_meetings_by_query(
            request.query, limit=request.limit
        )
        
        return {
            "query": request.query,
            "meetings_found": len(meetings),
            "meetings": meetings
        }
    except Exception as e:
        logger.error(f"Error searching Fathom meetings for query {request.query}: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching meetings: {str(e)}")

# Background sync endpoint - non-blocking
@app.post("/sync/background-comprehensive")
async def start_background_comprehensive_sync():
    """Start comprehensive background sync that keeps app responsive"""
    try:
        result = await sales_rag_service.start_background_comprehensive_sync()
        return {
            "message": "🚀 Background comprehensive sync started!",
            "details": "App remains fully responsive during sync",
            "status": result["status"],
            "note": "Check logs for progress updates"
        }
    except Exception as e:
        logger.error(f"Error starting background sync: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start background sync: {str(e)}")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Sales RAG Slack Bot is running",
        "version": "3.0.0",
        "description": "Enhanced sales intelligence with smart prioritization and thread-aware context",
        "approach": "Production-ready with all learnings integrated",
        "features": {
            "smart_prioritization": "Company channels, sales channels, and business ops get priority",
            "thread_aware_intelligence": "Thread context propagation for better entity tagging",
            "enhanced_rate_limiting": "Exponential backoff with conservative delays",
            "company_channel_detection": "Automatic detection of company-dedicated channels",
            "entity_propagation": "Thread-level entity context sharing",
            "conversation_memory": "Clear history and end session capabilities",
            "dual_slack_clients": "User token for syncing + Bot token for interactions"
        },
        "dual_client_architecture": {
            "user_client": {
                "purpose": "Data syncing without channel joining",
                "token": "SLACK_USER_TOKEN (your personal token)",
                "benefits": ["No channel joining needed", "Access to all channels you're in", "Better rate limits", "Less intrusive"]
            },
            "bot_client": {
                "purpose": "User interactions only",
                "token": "SLACK_BOT_TOKEN (bot app token)", 
                "behavior": "Only joins channels when users interact with bot"
            },
            "fallback": "If no user token provided, bot token used for both (less efficient)"
        },
        "setup_instructions": {
            "get_user_token": {
                "step_1": "Go to api.slack.com/apps → Your App → OAuth & Permissions",
                "step_2": "Under 'User Token Scopes' add: channels:read, channels:history, groups:history",
                "step_3": "Click 'Install App to Workspace' → Copy 'User OAuth Token'",
                "step_4": "Add SLACK_USER_TOKEN=xoxp-your-token to .env file",
                "note": "This gives the bot access to read channels you're already in"
            }
        },
        "endpoints": {
            "health": "/health - Check system health with cross-channel and Fathom status",
            "slack_events": "/slack/events - Slack bot interactions with enhanced intelligence", 
            "sync_salesforce": "/sync/salesforce - Sync Salesforce data with entity caching",
            "sync_background": "⭐ /sync/background-comprehensive - NON-BLOCKING comprehensive sync (RECOMMENDED)",
            "sync_slack_manual": "/sync/slack-channels - Enhanced manual sync (BLOCKS app during sync)",
            "sync_slack_automated": "/sync/slack-automated - Enhanced automated sync (150 channels)",
            "enable_realtime": "/enable-realtime - Enable real-time indexing of new messages",
            "search": "/search - Test search functionality with company filtering and Fathom meetings",
            "fathom_search_company": "/fathom/search-company - Search Fathom meetings by company name (legacy)",
            "fathom_search_salesforce": "⭐ /fathom/search-salesforce-integrated - Search via Salesforce contact emails (ENHANCED)",
            "fathom_search_query": "/fathom/search-query - Search Fathom meetings by general query",
            "debug_entities": "/debug/entities - Check entity cache status"
        },
        "intelligence_features": {
            "channel_prioritization": {
                "ultra_priority": "Company channels (fern-*, *-client, *-customer, *-partner) + sales/deals/revenue",
                "high_priority": "Business ops (demo, onboarding, support, implementation, contracts, legal)",
                "medium_priority": "Active business channels (10+ members)",
                "low_priority": "Other active channels (3+ members)"
            },
            "thread_awareness": {
                "entity_propagation": "If any message in thread mentions Zillow, all messages tagged as Zillow-related",
                "company_channels": "All messages in #fern-zillow tagged as Zillow-related",
                "context_sharing": "Thread-level entity context shared across all messages"
            },
            "enhanced_sync": {
                "smart_limits": "Ultra: 200 msgs/365 days, High: 100 msgs/180 days, Medium: 50 msgs/60 days",
                "rate_limiting": "Exponential backoff: 30s → 60s → 120s → 240s → 480s",
                "batch_processing": "8 channels per batch with 60s delays"
            }
        },
        "production_workflow": {
            "recommended_setup": "⭐ 1. /sync/salesforce → 2. /sync/background-comprehensive (NON-BLOCKING)",
            "alternative_setup": "1. /sync/salesforce → 2. /sync/slack-automated (blocks until complete)",
            "production": "3. /enable-realtime → 4. New messages auto-indexed with intelligence",
            "testing": "Use /sync/slack-channels for enhanced manual testing (BLOCKS app)",
            "monitoring": "Check /health for system status and /debug/entities for cache",
            "note": "background-comprehensive keeps app responsive during sync!"
        },
        "learnings_applied": {
            "zillow_issue_resolution": "Thread-aware intelligence prevents context mixing",
            "rate_limiting_mastery": "Conservative delays prevent API failures",
            "smart_prioritization": "Company channels get priority and enhanced processing",
            "metadata_compatibility": "All ChromaDB metadata issues resolved",
            "conversation_memory": "Clear history prevents context bleed between sessions"
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info" if not config.DEBUG else "debug"
    ) 