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

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Sales RAG Slack Bot is running",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "slack_events": "/slack/events",
            "sync_salesforce": "/sync/salesforce",
            "search": "/search",
            "write": "/write"
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