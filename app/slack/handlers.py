from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_sdk import WebClient
import logging
from typing import Dict, Any, Optional
import json
from datetime import datetime

from ..rag.embeddings import EmbeddingService
from ..rag.generation import GenerationService
from ..salesforce.client import SalesforceClient
from ..database.models import Conversation, SlackDocument
from ..config import config

logger = logging.getLogger(__name__)

class SlackHandler:
    def __init__(self, embedding_service: EmbeddingService, generation_service: GenerationService,
                 salesforce_client: SalesforceClient, db_session_maker):
        self.embedding_service = embedding_service
        self.generation_service = generation_service
        self.salesforce_client = salesforce_client
        self.db_session_maker = db_session_maker
        
        # Initialize Slack app
        self.app = App(
            token=config.SLACK_BOT_TOKEN,
            signing_secret=config.SLACK_SIGNING_SECRET
        )
        
        self.client = WebClient(token=config.SLACK_BOT_TOKEN)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Slack event handlers"""
        
        @self.app.command("/sales")
        def handle_sales_command(ack, respond, command):
            ack()
            logger.info(f"Received /sales command: {command}")
            
            try:
                question = command.get('text', '').strip()
                if not question:
                    respond("Please provide a question after the /sales command. Example: `/sales What opportunities are closing this month?`")
                    return
                
                channel_id = command.get('channel_id')
                user_id = command.get('user_id')
                
                # Get user info for better context
                user_info = self.client.users_info(user=user_id)
                user_name = user_info['user']['real_name'] if user_info['ok'] else 'Unknown User'
                
                # Generate response
                response_data = self._process_sales_question(
                    question=question,
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    thread_ts=None  # Initial command is not in a thread
                )
                
                # Format response
                response_text = self._format_response(response_data)
                
                # Save conversation
                self._save_conversation(
                    channel_id=channel_id,
                    user_id=user_id,
                    question=question,
                    answer=response_data['answer'],
                    sources=response_data['sources']
                )
                
                respond(response_text)
                
            except Exception as e:
                logger.error(f"Error handling /sales command: {e}")
                respond("Sorry, I encountered an error processing your request. Please try again.")
        
        @self.app.message(".*")
        def handle_message(message, say):
            """Handle direct messages and mentions for continued conversation"""
            try:
                # Only respond if bot is mentioned or in DM
                if not self._should_respond_to_message(message):
                    return
                
                text = message.get('text', '').strip()
                channel_id = message.get('channel')
                user_id = message.get('user')
                thread_ts = message.get('thread_ts')
                message_ts = message.get('ts')
                
                # Skip if this is a bot message
                if message.get('bot_id'):
                    return
                
                # Get user info
                user_info = self.client.users_info(user=user_id)
                user_name = user_info['user']['real_name'] if user_info['ok'] else 'Unknown User'
                
                # Process question
                response_data = self._process_sales_question(
                    question=text,
                    channel_id=channel_id,
                    user_id=user_id,
                    user_name=user_name,
                    thread_ts=thread_ts or message_ts
                )
                
                # Format response
                response_text = self._format_response(response_data)
                
                # Save conversation
                self._save_conversation(
                    channel_id=channel_id,
                    user_id=user_id,
                    question=text,
                    answer=response_data['answer'],
                    sources=response_data['sources'],
                    thread_ts=thread_ts
                )
                
                # Respond in thread if this was a thread message
                if thread_ts:
                    say(text=response_text, thread_ts=thread_ts)
                else:
                    say(text=response_text, thread_ts=message_ts)
                    
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                say("Sorry, I encountered an error processing your message. Please try again.")
        
        @self.app.event("message")
        def handle_message_events(event, logger):
            """Handle message events for indexing"""
            try:
                # Index Slack messages for RAG (non-bot messages only)
                if not event.get('bot_id') and event.get('text'):
                    self._index_slack_message(event)
            except Exception as e:
                logger.error(f"Error indexing message: {e}")
    
    def _should_respond_to_message(self, message: Dict[str, Any]) -> bool:
        """Determine if bot should respond to this message"""
        text = message.get('text', '').lower()
        channel_type = message.get('channel_type')
        
        # Respond to DMs
        if channel_type == 'im':
            return True
        
        # Respond if bot is mentioned
        bot_user_id = self.app.client.auth_test()['user_id']
        if f'<@{bot_user_id}>' in text:
            return True
        
        # Respond in threads where bot has participated
        thread_ts = message.get('thread_ts')
        if thread_ts:
            # Check if bot has messages in this thread
            try:
                thread_messages = self.client.conversations_replies(
                    channel=message.get('channel'),
                    ts=thread_ts
                )
                for msg in thread_messages['messages']:
                    if msg.get('bot_id') == bot_user_id:
                        return True
            except Exception:
                pass
        
        return False
    
    def _process_sales_question(self, question: str, channel_id: str, user_id: str, 
                               user_name: str, thread_ts: Optional[str] = None) -> Dict[str, Any]:
        """Process a sales question using RAG"""
        try:
            # Get thread context if in a thread
            thread_context = []
            if thread_ts:
                thread_context = self.embedding_service.get_thread_context(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    limit=10
                )
            
            # Get conversation history
            conversation_history = self._get_conversation_history(channel_id, user_id, limit=5)
            
            # Search for relevant context
            context_documents = self.embedding_service.search_similar_content(
                query=question,
                n_results=10,
                channel_filter=channel_id if thread_ts else None,
                thread_filter=thread_ts
            )
            
            # Generate response
            response_data = self.generation_service.generate_rag_response(
                question=question,
                context_documents=context_documents,
                thread_context=thread_context,
                conversation_history=conversation_history
            )
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing sales question: {e}")
            return {
                "answer": "I apologize, but I encountered an error while processing your question. Please try again.",
                "sources": [],
                "context_used": 0,
                "thread_context_used": 0
            }
    
    def _format_response(self, response_data: Dict[str, Any]) -> str:
        """Format the response for Slack"""
        answer = response_data.get('answer', '')
        sources = response_data.get('sources', [])
        
        formatted_response = answer
        
        # Add source information if available
        if sources:
            formatted_response += "\n\n*Sources:*"
            for source in sources[:3]:  # Limit to 3 sources to avoid clutter
                if source['type'] == 'salesforce':
                    formatted_response += f"\n• Salesforce {source['object_type']}: {source.get('title', 'Record')}"
                elif source['type'] == 'slack':
                    formatted_response += f"\n• Slack #{source['channel']} by {source['user']}"
        
        return formatted_response
    
    def _save_conversation(self, channel_id: str, user_id: str, question: str, 
                          answer: str, sources: list, thread_ts: Optional[str] = None):
        """Save conversation to database"""
        try:
            with self.db_session_maker() as db_session:
                conversation = Conversation(
                    slack_channel_id=channel_id,
                    slack_thread_ts=thread_ts,
                    slack_user_id=user_id,
                    question=question,
                    answer=answer,
                    sources=json.dumps(sources)
                )
                db_session.add(conversation)
                db_session.commit()
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    def _get_conversation_history(self, channel_id: str, user_id: str, limit: int = 5) -> list:
        """Get recent conversation history"""
        try:
            with self.db_session_maker() as db_session:
                conversations = db_session.query(Conversation).filter(
                    Conversation.slack_channel_id == channel_id,
                    Conversation.slack_user_id == user_id
                ).order_by(Conversation.created_at.desc()).limit(limit).all()
                
                return [
                    {"question": conv.question, "answer": conv.answer}
                    for conv in reversed(conversations)
                ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def _index_slack_message(self, event: Dict[str, Any]):
        """Index a Slack message for RAG"""
        try:
            message_id = event.get('ts')
            text = event.get('text', '')
            channel_id = event.get('channel')
            user_id = event.get('user')
            thread_ts = event.get('thread_ts')
            
            if not text or len(text) < 10:  # Skip very short messages
                return
            
            # Get channel and user info
            channel_info = self.client.conversations_info(channel=channel_id)
            user_info = self.client.users_info(user=user_id)
            
            channel_name = channel_info['channel']['name'] if channel_info['ok'] else 'Unknown'
            user_name = user_info['user']['real_name'] if user_info['ok'] else 'Unknown User'
            
            # Prepare metadata
            metadata = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "user_id": user_id,
                "user_name": user_name,
                "ts": message_id,
                "thread_ts": thread_ts
            }
            
            # Add to embedding service
            self.embedding_service.add_slack_message(
                message_id=message_id,
                content=text,
                metadata=metadata
            )
            
            # Save to database
            with self.db_session_maker() as db_session:
                slack_doc = SlackDocument(
                    channel_id=channel_id,
                    message_ts=message_id,
                    thread_ts=thread_ts,
                    user_id=user_id,
                    content=text,
                    doc_metadata=json.dumps(metadata),
                    created_at=datetime.fromtimestamp(float(message_id)),
                    is_embedded=True
                )
                db_session.add(slack_doc)
                db_session.commit()
            
        except Exception as e:
            logger.error(f"Error indexing Slack message: {e}")
    
    def get_handler(self):
        """Get the FastAPI request handler"""
        return SlackRequestHandler(self.app)
    
    async def handle_request(self, request):
        """Handle Slack request asynchronously"""
        handler = SlackRequestHandler(self.app)
        return handler.handle(request) 