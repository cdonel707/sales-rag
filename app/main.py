from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
import httpx
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

async def process_sales_question_async(query: str, response_url: str):
    """Process sales question asynchronously and send response to Slack"""
    try:
        # Process the sales question
        result = await sales_rag_service.search_sales_data(query=query)
        response_text = result.get('answer', 'Sorry, I could not find relevant information.')
        
        # Add sources if available
        sources = result.get('sources', [])
        if sources:
            response_text += "\n\n*Sources:*"
            for source in sources[:3]:
                if source.get('type') == 'salesforce':
                    response_text += f"\n• Salesforce {source.get('object_type', 'Record')}"
                elif source.get('type') == 'slack':
                    response_text += f"\n• Slack #{source.get('channel', 'Unknown')}"
        
        # Send response back to Slack
        async with httpx.AsyncClient() as client:
            await client.post(response_url, json={
                "response_type": "in_channel",
                "text": response_text,
                "replace_original": True
            })
            
    except Exception as e:
        logger.error(f"Error processing async sales question: {e}")
        # Send error response to Slack
        try:
            async with httpx.AsyncClient() as client:
                await client.post(response_url, json={
                    "response_type": "in_channel", 
                    "text": "Sorry, I encountered an error processing your question. Please try again.",
                    "replace_original": True
                })
        except:
            pass  # If we can't send error response, just log it

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

# Slack events endpoint - simplified version
@app.post("/slack/events")
async def slack_events(request: Request):
    """Handle Slack events"""
    if not sales_rag_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Check content type to determine how to parse the request
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            # Handle URL verification challenge (JSON format)
            body = await request.json()
            if body.get("type") == "url_verification":
                return {"challenge": body.get("challenge")}
            return {"status": "ok"}
        
        elif "application/x-www-form-urlencoded" in content_type:
            # Handle slash commands (form data format)
            form_data = await request.form()
            command = form_data.get("command")
            
            if command == "/sales":
                text = form_data.get("text", "").strip()
                if not text:
                    return {"text": "Please provide a question after the /sales command. Example: `/sales What opportunities are closing this month?`"}
                
                # Get response_url for delayed response
                response_url = form_data.get("response_url")
                
                # Immediately acknowledge the command
                response = {
                    "response_type": "in_channel",
                    "text": f"🔍 Searching for information about: *{text}*\n_Please wait while I analyze your Salesforce data..._"
                }
                
                # Process the sales question asynchronously
                if response_url:
                    asyncio.create_task(process_sales_question_async(text, response_url))
                
                return response
        
        # Handle other cases
        return {"status": "ok"}
        
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
            "search": "/search"
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