import logging
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
from datetime import datetime, timedelta

from .rag.embeddings import EmbeddingService
from .rag.generation import GenerationService
from .salesforce.client import SalesforceClient
from .slack.handlers import SlackHandler
from .database.models import SalesforceDocument
from .config import config
import json

logger = logging.getLogger(__name__)

class SalesRAGService:
    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker
        
        # Initialize Salesforce client first
        self.salesforce_client = SalesforceClient(
            username=config.SALESFORCE_USERNAME,
            password=config.SALESFORCE_PASSWORD,
            security_token=config.SALESFORCE_SECURITY_TOKEN,
            domain=config.SALESFORCE_DOMAIN
        )
        
        # Initialize embedding service
        self.embedding_service = EmbeddingService(
            openai_api_key=config.OPENAI_API_KEY,
            chroma_path="./chroma_db"
        )
        
        # Initialize generation service with salesforce client
        self.generation_service = GenerationService(
            openai_api_key=config.OPENAI_API_KEY,
            sf_client=self.salesforce_client
        )
        
        # Initialize Slack handler
        self.slack_handler = SlackHandler(
            embedding_service=self.embedding_service,
            generation_service=self.generation_service,
            salesforce_client=self.salesforce_client,
            db_session_maker=self.db_session_maker
        )
    
    async def initialize(self):
        """Initialize the service and perform initial data sync"""
        logger.info("Initializing Sales RAG Service...")
        
        # Connect to Salesforce
        if not self.salesforce_client.connect():
            logger.error("Failed to connect to Salesforce")
            return False
        
        # Perform initial data sync
        await self.sync_salesforce_data()
        
        logger.info("Sales RAG Service initialized successfully")
        return True
    
    async def sync_salesforce_data(self, force_resync: bool = False):
        """Sync Salesforce data to vector database"""
        logger.info("Starting Salesforce data sync...")
        
        try:
            with self.db_session_maker() as db_session:
                # Get accounts
                accounts = self.salesforce_client.get_accounts(limit=500)
                await self._process_salesforce_records(accounts, 'Account', db_session, force_resync)
                
                # Get opportunities
                opportunities = self.salesforce_client.get_opportunities(limit=500)
                await self._process_salesforce_records(opportunities, 'Opportunity', db_session, force_resync)
                
                # Get contacts
                contacts = self.salesforce_client.get_contacts(limit=500)
                await self._process_salesforce_records(contacts, 'Contact', db_session, force_resync)
                
                # Get cases
                cases = self.salesforce_client.get_cases(limit=500)
                await self._process_salesforce_records(cases, 'Case', db_session, force_resync)
                
                logger.info("Salesforce data sync completed successfully")
                
        except Exception as e:
            logger.error(f"Error syncing Salesforce data: {e}")
    
    async def _process_salesforce_records(self, records: list, object_type: str, 
                                        db_session: Session, force_resync: bool = False):
        """Process and embed Salesforce records"""
        logger.info(f"Processing {len(records)} {object_type} records...")
        
        for record in records:
            try:
                record_id = record.get('Id')
                if not record_id:
                    continue
                
                # Check if record already exists and is up to date
                existing_doc = db_session.query(SalesforceDocument).filter(
                    SalesforceDocument.sf_object_id == record_id
                ).first()
                
                last_modified = record.get('LastModifiedDate')
                if existing_doc and not force_resync and last_modified:
                    # Parse Salesforce datetime and make timezone-aware comparison
                    try:
                        sf_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                        # Make existing_doc.last_updated timezone-aware if it isn't
                        existing_updated = existing_doc.last_updated
                        if existing_updated.tzinfo is None:
                            from datetime import timezone
                            existing_updated = existing_updated.replace(tzinfo=timezone.utc)
                        if existing_updated >= sf_modified:
                            continue  # Skip if already up to date
                    except Exception as e:
                        logger.debug(f"Error comparing dates for record {record_id}: {e}")
                        # Continue processing if date comparison fails
                
                # Format record for embedding
                content = self.salesforce_client.format_record_for_embedding(record, object_type)
                if not content.strip():
                    continue
                
                # Prepare metadata
                metadata = {
                    "object_type": object_type,
                    "record_id": record_id,
                    "title": self._get_record_title(record, object_type),
                    "last_modified": last_modified
                }
                
                # Add to embedding service
                success = self.embedding_service.add_salesforce_record(
                    record_id=record_id,
                    content=content,
                    metadata=metadata
                )
                
                if success:
                    # Update database record
                    if existing_doc:
                        existing_doc.content = content
                        existing_doc.doc_metadata = json.dumps(metadata)
                        existing_doc.last_updated = datetime.utcnow()
                        existing_doc.is_embedded = True
                    else:
                        sf_doc = SalesforceDocument(
                            sf_object_type=object_type,
                            sf_object_id=record_id,
                            title=metadata['title'],
                            content=content,
                            doc_metadata=json.dumps(metadata),
                            is_embedded=True
                        )
                        db_session.add(sf_doc)
                    
                    db_session.commit()
                
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error processing {object_type} record {record.get('Id', 'Unknown')}: {e}")
                db_session.rollback()
                continue
    
    def _get_record_title(self, record: dict, object_type: str) -> str:
        """Get a human-readable title for a Salesforce record"""
        if object_type == 'Account':
            return record.get('Name', 'Unknown Account')
        elif object_type == 'Opportunity':
            return record.get('Name', 'Unknown Opportunity')
        elif object_type == 'Contact':
            first_name = record.get('FirstName', '')
            last_name = record.get('LastName', '')
            return f"{first_name} {last_name}".strip() or 'Unknown Contact'
        elif object_type == 'Case':
            return record.get('Subject', f"Case {record.get('CaseNumber', 'Unknown')}")
        else:
            return f"{object_type} {record.get('Id', 'Unknown')}"
    
    async def search_sales_data(self, query: str, source_filter: Optional[str] = None,
                               channel_filter: Optional[str] = None,
                               thread_filter: Optional[str] = None,
                               thread_context: Optional[list] = None,
                               conversation_history: Optional[list] = None) -> dict:
        """Search sales data using RAG or handle write operations"""
        try:
            # Search for relevant documents
            context_documents = self.embedding_service.search_similar_content(
                query=query,
                n_results=10,
                source_filter=source_filter,
                channel_filter=channel_filter,
                thread_filter=thread_filter
            )
            
            # Process query (read or write operation)
            response_data = self.generation_service.process_query(
                question=query,
                context_documents=context_documents,
                thread_context=thread_context,
                conversation_history=conversation_history
            )
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "I apologize, but I encountered an error while processing your request. Please try again.",
                "sources": [],
                "context_used": 0,
                "thread_context_used": 0
            }
    
    async def execute_write_operation(self, parsed_command: dict) -> dict:
        """Execute a confirmed write operation"""
        try:
            return self.generation_service.execute_confirmed_write_operation(parsed_command)
        except Exception as e:
            logger.error(f"Error executing write operation: {e}")
            return {
                "answer": f"❌ Error executing write operation: {str(e)}",
                "is_write": True,
                "write_success": False,
                "sources": [],
                "context_used": 0
            }
    
    def get_slack_handler(self):
        """Get the Slack request handler"""
        return self.slack_handler.get_handler()
    
    async def health_check(self) -> dict:
        """Perform health check on all services"""
        health_status = {
            "salesforce": False,
            "openai": False,
            "vector_db": False,
            "database": False
        }
        
        try:
            # Check Salesforce connection
            health_status["salesforce"] = self.salesforce_client.connect()
            
            # Check OpenAI (try a simple embedding)
            try:
                test_embedding = self.embedding_service.generate_embedding("test")
                health_status["openai"] = len(test_embedding) > 0
            except:
                health_status["openai"] = False
            
            # Check vector database
            try:
                # Try a simple search
                self.embedding_service.search_similar_content("test", n_results=1)
                health_status["vector_db"] = True
            except:
                health_status["vector_db"] = False
            
            # Check database
            try:
                with self.db_session_maker() as db_session:
                    db_session.execute("SELECT 1")
                    health_status["database"] = True
            except:
                health_status["database"] = False
            
        except Exception as e:
            logger.error(f"Error during health check: {e}")
        
        return {
            "status": "healthy" if all(health_status.values()) else "degraded",
            "services": health_status,
            "timestamp": datetime.utcnow().isoformat()
        } 