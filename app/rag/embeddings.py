import openai
import chromadb
from chromadb.config import Settings
import logging
from typing import List, Dict, Any, Optional
import hashlib
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self, openai_api_key: str, chroma_path: str = "./chroma_db"):
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        
        # Create collections for different data types
        self.slack_collection = self.chroma_client.get_or_create_collection(
            name="slack_messages",
            metadata={"description": "Slack messages and conversations"}
        )
        self.salesforce_collection = self.chroma_client.get_or_create_collection(
            name="salesforce_records", 
            metadata={"description": "Salesforce records and data"}
        )
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI's text-embedding-ada-002"""
        try:
            response = self.openai_client.embeddings.create(
                input=text,
                model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []
    
    def add_slack_message(self, message_id: str, content: str, metadata: Dict[str, Any]):
        """Add a Slack message to the vector database"""
        try:
            embedding = self.generate_embedding(content)
            if not embedding:
                return False
            
            # Create unique ID based on message content hash
            doc_id = hashlib.md5(f"slack_{message_id}".encode()).hexdigest()
            
            self.slack_collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    **metadata,
                    "source_type": "slack",
                    "message_id": message_id,
                    "indexed_at": datetime.utcnow().isoformat()
                }],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            logger.error(f"Error adding Slack message to vector DB: {e}")
            return False
    
    def add_salesforce_record(self, record_id: str, content: str, metadata: Dict[str, Any]):
        """Add a Salesforce record to the vector database"""
        try:
            embedding = self.generate_embedding(content)
            if not embedding:
                return False
            
            # Create unique ID based on record content hash
            doc_id = hashlib.md5(f"sf_{record_id}".encode()).hexdigest()
            
            self.salesforce_collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    **metadata,
                    "source_type": "salesforce",
                    "record_id": record_id,
                    "indexed_at": datetime.utcnow().isoformat()
                }],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            logger.error(f"Error adding Salesforce record to vector DB: {e}")
            return False
    
    def search_similar_content(self, query: str, n_results: int = 10, 
                             source_filter: Optional[str] = None,
                             channel_filter: Optional[str] = None,
                             thread_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for similar content across both collections"""
        try:
            query_embedding = self.generate_embedding(query)
            if not query_embedding:
                return []
            
            results = []
            
            # Search Slack messages with filters
            slack_where = {"source_type": "slack"}
            if channel_filter:
                slack_where["channel_id"] = channel_filter
            if thread_filter:
                slack_where["thread_ts"] = thread_filter
            
            if not source_filter or source_filter == "slack":
                slack_results = self.slack_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results // 2 if not source_filter else n_results,
                    where=slack_where if (channel_filter or thread_filter) else {"source_type": "slack"}
                )
                
                for i, doc in enumerate(slack_results['documents'][0]):
                    results.append({
                        "content": doc,
                        "metadata": slack_results['metadatas'][0][i],
                        "distance": slack_results['distances'][0][i] if 'distances' in slack_results else 0,
                        "source": "slack"
                    })
            
            # Search Salesforce records
            if not source_filter or source_filter == "salesforce":
                sf_results = self.salesforce_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results // 2 if not source_filter else n_results,
                    where={"source_type": "salesforce"}
                )
                
                for i, doc in enumerate(sf_results['documents'][0]):
                    results.append({
                        "content": doc,
                        "metadata": sf_results['metadatas'][0][i],
                        "distance": sf_results['distances'][0][i] if 'distances' in sf_results else 0,
                        "source": "salesforce"
                    })
            
            # Sort by distance (similarity)
            results.sort(key=lambda x: x['distance'])
            return results[:n_results]
            
        except Exception as e:
            logger.error(f"Error searching similar content: {e}")
            return []
    
    def get_thread_context(self, channel_id: str, thread_ts: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all messages from a specific thread for context"""
        try:
            results = self.slack_collection.query(
                query_embeddings=None,
                n_results=limit,
                where={
                    "source_type": "slack",
                    "channel_id": channel_id,
                    "thread_ts": thread_ts
                }
            )
            
            thread_messages = []
            for i, doc in enumerate(results['documents'][0]):
                thread_messages.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i],
                    "source": "slack"
                })
            
            # Sort by timestamp
            thread_messages.sort(key=lambda x: float(x['metadata'].get('ts', 0)))
            return thread_messages
            
        except Exception as e:
            logger.error(f"Error getting thread context: {e}")
            return [] 