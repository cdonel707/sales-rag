from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_sdk import WebClient
import logging
from typing import Dict, Any, Optional
import json
from datetime import datetime
import os

from ..rag.embeddings import EmbeddingService
from ..rag.generation import GenerationService
from ..salesforce.client import SalesforceClient
from ..database.models import Conversation, SlackDocument

logger = logging.getLogger(__name__)

# In-memory stores (in production, use Redis or database)
pending_write_operations = {}
active_sessions = {}  # Track ongoing conversations

def clear_stale_sessions():
    """Clear any stale active sessions to prevent auto-responding issues"""
    global active_sessions
    logger.info(f"Clearing {len(active_sessions)} active sessions to prevent auto-responding")
    active_sessions.clear()
    logger.info("✅ All active sessions cleared")

class SlackHandler:
    def __init__(self, embedding_service: EmbeddingService, generation_service: GenerationService,
                 salesforce_client: SalesforceClient, db_session_maker, sales_rag_service=None):
        self.embedding_service = embedding_service
        self.generation_service = generation_service
        self.salesforce_client = salesforce_client
        self.db_session_maker = db_session_maker
        self.sales_rag_service = sales_rag_service  # Store reference to parent service
        
        # Real-time indexing control
        self.realtime_indexing_enabled = False
        
        # Clear any stale sessions on startup
        self.clear_all_active_sessions()
        
        # Initialize Slack app
        self.app = App(
            token=os.getenv("SLACK_BOT_TOKEN"),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
            process_before_response=True
        )
        self.client = self.app.client
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Slack event handlers"""
        
        @self.app.command("/sales")
        def handle_sales_command(ack, respond, command):
            ack()
            logger.info(f"Received /sales command: {command}")
            
            try:
                question = command.get('text', '').strip()
                channel_id = command.get('channel_id')
                user_id = command.get('user_id')
                
                # Ensure bot is in channel for interaction (if it's a channel, not DM)
                if channel_id and not channel_id.startswith('D'):  # Not a DM
                    channel_info = self.client.conversations_info(channel=channel_id)
                    if channel_info.get('ok'):
                        channel_name = channel_info['channel']['name']
                        self._ensure_bot_in_channel_for_interaction(channel_id, channel_name)
                
                # Start or continue session
                session_key = f"{channel_id}:{user_id}"
                
                if not question:
                    # Show ephemeral interface
                    self._show_sales_interface(respond, session_key)
                else:
                    # Process the question directly
                    self._handle_sales_query(question, channel_id, user_id, respond)
                
            except Exception as e:
                logger.error(f"Error handling /sales command: {e}")
                respond({
                    "response_type": "ephemeral",
                    "text": "Sorry, I encountered an error processing your request. Please try again."
                })
        
        @self.app.message(".*")
        def handle_message(message, say, client):
            """Handle direct messages and mentions for continued conversation"""
            try:
                logger.debug(f"Received message: {message}")
                
                # Only respond if bot is mentioned or in DM or user has active session
                text = message.get('text', '').strip()
                channel_id = message.get('channel')
                user_id = message.get('user')
                thread_ts = message.get('thread_ts')
                message_ts = message.get('ts')
                
                # Skip if this is a bot message
                if message.get('bot_id'):
                    logger.debug("Skipping bot message")
                    return
                
                # Check if user has active session for ephemeral responses
                session_key = f"{channel_id}:{user_id}"
                has_active_session = session_key in active_sessions
                
                # Determine if we should respond - ONLY respond when explicitly mentioned or in DMs
                should_respond = self._should_respond_to_message(message)
                
                if not should_respond:
                    logger.debug("Not responding to this message - bot not mentioned and not a DM")
                    return
                
                logger.info(f"Processing message: text='{text}', channel={channel_id}, user={user_id}, thread={thread_ts}, has_session={has_active_session}")
                
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
                
                # Save conversation
                self._save_conversation(
                    channel_id=channel_id,
                    user_id=user_id,
                    question=text,
                    answer=response_data['answer'],
                    sources=response_data['sources'],
                    thread_ts=thread_ts
                )
                
                # Determine response method based on session and write operations
                if has_active_session:
                    # Respond ephemerally for users with active sessions
                    if response_data.get('is_write') and response_data.get('requires_confirmation'):
                        # Show ephemeral confirmation UI for write operations
                        self._send_ephemeral_write_confirmation(client, channel_id, user_id, response_data)
                    else:
                        # Send ephemeral response
                        self._send_ephemeral_response(client, channel_id, user_id, response_data)
                else:
                    # Normal public response behavior
                    response_text = self._format_response(response_data)
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
                # Real-time indexing if enabled
                if self.realtime_indexing_enabled:
                    if not event.get('bot_id') and event.get('text') and len(event.get('text', '')) >= 10:
                        logger.info(f"🔄 Real-time indexing message from #{event.get('channel', 'unknown')}")
                        indexed = self._index_slack_message_realtime(event)
                        if indexed:
                            logger.info(f"✅ Real-time indexed message: {event.get('text', '')[:50]}...")
                        else:
                            logger.debug(f"⏭️ Skipped indexing message (no relevant entities)")
                else:
                    # Legacy behavior - basic indexing for RAG during manual sync
                    if not event.get('bot_id') and event.get('text'):
                        self._index_slack_message(event)
            except Exception as e:
                logger.error(f"Error in message event handler: {e}")
        
        # Button interaction handlers (removed search_records, update_record, create_new)
        @self.app.action("end_session")
        def handle_end_session(ack, body, respond):
            ack()
            try:
                # Get session key from button value
                session_key = body['actions'][0]['value']
                
                # Clear the session
                if session_key in active_sessions:
                    del active_sessions[session_key]
                
                respond({
                    "response_type": "ephemeral",
                    "text": "✅ Session ended. Use `/sales` to start a new session.",
                    "replace_original": True
                })
            except Exception as e:
                logger.error(f"Error ending session: {e}")
                respond({
                    "response_type": "ephemeral",
                    "text": "❌ Error ending session"
                })
        
        @self.app.action("clear_history")
        def handle_clear_history(ack, body, respond):
            ack()
            session_key = body['actions'][0]['value']
            
            # Clear conversation history from database but keep session active
            try:
                channel_id, user_id = session_key.split(':')
                self._clear_conversation_history(channel_id, user_id)
                logger.info(f"Cleared conversation history for user {user_id} in channel {channel_id}")
                
                respond({
                    "response_type": "ephemeral",
                    "text": "🧹 Conversation history cleared! Your next question will start a fresh conversation."
                })
            except Exception as e:
                logger.error(f"Error clearing conversation history: {e}")
                respond({
                    "response_type": "ephemeral",
                    "text": "❌ Error clearing conversation history. Please try again."
                })
        
        @self.app.action("confirm_write")
        def handle_confirm_write(ack, body, respond):
            ack()
            try:
                # Parse the command data from button value
                parsed_command = json.loads(body['actions'][0]['value'])
                
                # Execute the write operation
                result = self.generation_service.execute_confirmed_write_operation(parsed_command)
                
                respond({
                    "response_type": "ephemeral",
                    "text": self._format_response(result)
                })
                
            except Exception as e:
                logger.error(f"Error executing confirmed write: {e}")
                respond({
                    "response_type": "ephemeral",
                    "text": f"❌ Error executing operation: {str(e)}"
                })
        
        @self.app.action("cancel_write")
        def handle_cancel_write(ack, body, respond):
            ack()
            respond({
                "response_type": "ephemeral",
                "text": "❌ Write operation cancelled. No changes were made to Salesforce."
            })
        
        @self.app.action("edit_write")
        def handle_edit_write(ack, body, respond):
            ack()
            respond({
                "response_type": "ephemeral",
                "text": "✏️ To modify the operation, please use `/sales` with your updated request."
            })
        
        @self.app.action("open_chat")
        def handle_open_chat(ack, body, client):
            ack()
            try:
                # Get session info from button value
                button_value = body['actions'][0]['value']
                
                # Handle different button value formats
                if button_value.startswith('{'):
                    # JSON format
                    parsed_value = json.loads(button_value)
                    session_key = parsed_value.get('session_key', button_value)
                else:
                    # Direct session key format
                    session_key = button_value
                
                # Open modal for chat input
                client.views_open(
                    trigger_id=body['trigger_id'],
                    view={
                        "type": "modal",
                        "callback_id": "chat_modal",
                        "title": {"type": "plain_text", "text": "💬 Sales Chat"},
                        "submit": {"type": "plain_text", "text": "Send"},
                        "private_metadata": session_key,
                        "blocks": [
                            {
                                "type": "input",
                                "block_id": "chat_input",
                                "element": {
                                    "type": "plain_text_input",
                                    "action_id": "message",
                                    "multiline": True,
                                    "placeholder": {
                                        "type": "plain_text",
                                        "text": "Ask me anything about your Salesforce data..."
                                    }
                                },
                                "label": {"type": "plain_text", "text": "Your Question"}
                            }
                        ]
                    }
                )
            except Exception as e:
                logger.error(f"Error opening chat modal: {e}")
        
        @self.app.view("chat_modal")
        def handle_chat_modal_submission(ack, body, view, client):
            # Acknowledge the modal submission first
            ack()
            
            try:
                # Get the question from modal
                question = view['state']['values']['chat_input']['message']['value']
                session_key = view['private_metadata']
                
                # Parse session key to get channel and user
                channel_id, user_id = session_key.split(':')
                
                # Process the question in the background and send response
                def process_and_respond():
                    try:
                        # Get user info
                        user_info = client.users_info(user=user_id)
                        user_name = user_info['user']['real_name'] if user_info['ok'] else 'Unknown User'
                        
                        # Process the question
                        response_data = self._process_sales_question(
                            question=question,
                            channel_id=channel_id,
                            user_id=user_id,
                            user_name=user_name,
                            thread_ts=None
                        )
                        
                        # Save conversation
                        self._save_conversation(
                            channel_id=channel_id,
                            user_id=user_id,
                            question=question,
                            answer=response_data['answer'],
                            sources=response_data['sources']
                        )
                        
                        # Send response based on type
                        if response_data.get('is_write') and response_data.get('requires_confirmation'):
                            self._send_ephemeral_write_confirmation(client, channel_id, user_id, response_data)
                        else:
                            self._send_ephemeral_response(client, channel_id, user_id, response_data)
                            
                    except Exception as e:
                        logger.error(f"Error processing modal question: {e}")
                        # Send error message
                        client.chat_postEphemeral(
                            channel=channel_id,
                            user=user_id,
                            text="❌ Sorry, I encountered an error processing your question. Please try again."
                        )
                
                # Process in background thread so modal can close immediately
                import threading
                threading.Thread(target=process_and_respond).start()
                
            except Exception as e:
                logger.error(f"Error handling chat modal submission: {e}")
    
    def _should_respond_to_message(self, message: Dict[str, Any]) -> bool:
        """Determine if bot should respond to this message - CONSERVATIVE approach"""
        text = message.get('text', '').lower()
        channel_type = message.get('channel_type')
        thread_ts = message.get('thread_ts')
        
        logger.debug(f"Checking if should respond to message: text='{text}', channel_type='{channel_type}', thread_ts='{thread_ts}'")
        
        # ONLY respond to DMs
        if channel_type == 'im':
            logger.debug("Responding because it's a DM")
            return True
        
        # ONLY respond if bot is directly mentioned
        try:
            bot_user_id = self.app.client.auth_test()['user_id']
            if f'<@{bot_user_id}>' in text:
                logger.debug("Responding because bot is mentioned")
                return True
        except Exception as e:
            logger.error(f"Error getting bot user ID: {e}")
            return False
        
        # DO NOT auto-respond in threads - require explicit mention
        # This prevents the bot from auto-responding to every message in threads it has participated in
        logger.debug("Not responding to this message - not a DM and bot not mentioned")
        return False
    
    def _process_sales_question(self, question: str, channel_id: str, user_id: str, 
                               user_name: str, thread_ts: Optional[str] = None) -> Dict[str, Any]:
        """Process a sales question using RAG or handle write operations"""
        try:
            # Check if this is a confirmation response
            question_lower = question.lower().strip()
            logger.debug(f"Processing question: '{question_lower}' for user {user_id} in channel {channel_id}, thread {thread_ts}")
            
            if question_lower in ['yes', 'y', 'confirm', 'ok', 'proceed']:
                logger.info(f"Detected confirmation 'yes' from user {user_id}")
                return self._handle_write_confirmation(channel_id, user_id, thread_ts, True)
            elif question_lower in ['no', 'n', 'cancel', 'abort', 'stop']:
                logger.info(f"Detected confirmation 'no' from user {user_id}")
                return self._handle_write_confirmation(channel_id, user_id, thread_ts, False)
            
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
            
            # Extract potential company mentions from the question for enhanced search
            company_filter = self._extract_company_from_question(question)
            
            # Enhanced search for relevant context with cross-channel capabilities AND Fathom integration
            search_query = self._enhance_search_query(question, company_filter)
            
            # Use the enhanced search with Fathom integration via the stored service reference
            if self.sales_rag_service and hasattr(self.sales_rag_service, 'search_sales_data'):
                try:
                    import asyncio
                    
                    # Handle async call - check if we're already in an event loop
                    try:
                        # Try to get the running loop
                        loop = asyncio.get_running_loop()
                        # If we're in a loop, we need to run in a thread
                        import concurrent.futures
                        import threading
                        
                        def run_search():
                            return asyncio.run(self.sales_rag_service.search_sales_data(
                                query=search_query,
                                source_filter=None
                            ))
                        
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(run_search)
                            enhanced_result = future.result(timeout=30)
                            
                    except RuntimeError:
                        # No running loop, safe to use asyncio.run
                        enhanced_result = asyncio.run(self.sales_rag_service.search_sales_data(
                            query=search_query,
                            source_filter=None  # Let it search all sources
                        ))
                    
                    # Extract context documents from the enhanced result
                    context_documents = enhanced_result.get('context_documents', [])
                    
                    # Log Fathom integration status
                    debug_info = enhanced_result.get('debug_info', {})
                    fathom_meetings_found = debug_info.get('fathom_meetings_found', 0)
                    logger.info(f"🎯 Slack handler: Enhanced search found {fathom_meetings_found} Fathom meetings")
                    
                except Exception as e:
                    logger.error(f"Error using enhanced search, falling back to basic search: {e}")
                    # Fallback to basic search
                    context_documents = self.embedding_service.search_similar_content(
                        query=search_query,
                        n_results=10,
                        channel_filter=channel_id if thread_ts else None,
                        thread_filter=thread_ts,
                        company_filter=company_filter
                    )
            else:
                # Fallback if service not available
                logger.warning("Sales RAG service not available, using basic search")
                context_documents = self.embedding_service.search_similar_content(
                    query=search_query,
                    n_results=10,
                    channel_filter=channel_id if thread_ts else None,
                    thread_filter=thread_ts,
                    company_filter=company_filter
                )
            
            # Process query (read or write operation)
            response_data = self.generation_service.process_query(
                question=question,
                context_documents=context_documents,
                thread_context=thread_context,
                conversation_history=conversation_history
            )
            
            # Add the original question to response_data for formatting
            response_data['question'] = question
            
            # If this is a write operation requiring confirmation, store it
            if response_data.get('requires_confirmation'):
                self._store_pending_write_operation(channel_id, user_id, thread_ts, response_data.get('parsed_command'))
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing sales question: {e}")
            return {
                "answer": "I apologize, but I encountered an error while processing your question. Please try again.",
                "sources": [],
                "context_used": 0,
                "thread_context_used": 0,
                "question": question
            }
    
    def _store_pending_write_operation(self, channel_id: str, user_id: str, 
                                      thread_ts: Optional[str], parsed_command: Dict[str, Any]):
        """Store a pending write operation for confirmation"""
        key = f"{channel_id}:{user_id}:{thread_ts or 'direct'}"
        pending_write_operations[key] = {
            'parsed_command': parsed_command,
            'timestamp': datetime.utcnow(),
            'channel_id': channel_id,
            'user_id': user_id,
            'thread_ts': thread_ts
        }
        logger.info(f"Stored pending write operation for {key}")

    def _handle_write_confirmation(self, channel_id: str, user_id: str, 
                                  thread_ts: Optional[str], confirmed: bool) -> Dict[str, Any]:
        """Handle write operation confirmation"""
        key = f"{channel_id}:{user_id}:{thread_ts or 'direct'}"
        logger.info(f"Handling write confirmation for key: {key}, confirmed: {confirmed}")
        logger.debug(f"Current pending operations: {list(pending_write_operations.keys())}")
        
        if key not in pending_write_operations:
            logger.warning(f"No pending operation found for key: {key}")
            return {
                "answer": "I don't have any pending operations to confirm. Please start with a new command.",
                "sources": [],
                "context_used": 0,
                "question": "Confirmation response"
            }
        
        pending_op = pending_write_operations.pop(key)
        logger.info(f"Found and removed pending operation for key: {key}")
        
        if not confirmed:
            logger.info("Write operation cancelled by user")
            return {
                "answer": "❌ Write operation cancelled. No changes were made to Salesforce.",
                "sources": [],
                "context_used": 0,
                "question": "Write operation cancellation"
            }
        
        # Execute the write operation
        try:
            result = self.generation_service.execute_confirmed_write_operation(
                pending_op['parsed_command']
            )
            # Add question for formatting
            result['question'] = "Write operation confirmation"
            return result
        except Exception as e:
            logger.error(f"Error executing confirmed write operation: {e}")
            return {
                "answer": f"❌ Error executing write operation: {str(e)}",
                "sources": [],
                "context_used": 0,
                "question": "Write operation execution"
            }

    def _format_response(self, response_data: Dict[str, Any]) -> str:
        """Format the response for Slack with user's prompt at the top"""
        answer = response_data.get('answer', '')
        sources = response_data.get('sources', [])
        is_write = response_data.get('is_write', False)
        question = response_data.get('question', '')  # Get the original question
        
        # Start with the prompt if available
        formatted_response = ""
        if question:
            formatted_response = f"**Prompt:** {question}\n\n"
        
        # Add the answer
        if is_write:
            if response_data.get('write_success'):
                formatted_response += f"**Answer:** ✅ {answer}"
            elif response_data.get('requires_confirmation'):
                formatted_response += f"**Answer:** ⚠️ {answer}"
            elif not response_data.get('write_success', True):  # Failed write operation
                formatted_response += f"**Answer:** ❌ {answer}"
        else:
            formatted_response += f"**Answer:** {answer}"
        
        # Sources section removed per user request
        
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
    
    def _clear_conversation_history(self, channel_id: str, user_id: str):
        """Clear conversation history for a specific user and channel"""
        try:
            with self.db_session_maker() as db_session:
                # Delete all conversation records for this user/channel combination
                deleted_count = db_session.query(Conversation).filter(
                    Conversation.slack_channel_id == channel_id,
                    Conversation.slack_user_id == user_id
                ).delete()
                
                db_session.commit()
                logger.info(f"Cleared {deleted_count} conversation records for user {user_id} in channel {channel_id}")
                
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            raise
    
    def _extract_company_from_question(self, question: str) -> Optional[str]:
        """Enhanced company extraction from question with contextual intelligence"""
        if not hasattr(self.embedding_service, 'company_cache'):
            return None
            
        question_lower = question.lower()
        
        # METHOD 1: Direct company name mentions
        for company in self.embedding_service.company_cache:
            if len(company) > 3 and company.lower() in question_lower:  # Make case-insensitive
                logger.info(f"🎯 Slack handler: Company detected: '{company}' (from query: '{question}')")
                return company
        
        # METHOD 2: Enhanced contextual patterns
        # Look for phrases that indicate company discussions
        company_patterns = {
            'zillow': ['zillow', 'zillowgroup', 'zillow group', 'discussions with zillow', 'zillow in slack'],
            'microsoft': ['microsoft', 'msft', 'discussions with microsoft', 'microsoft in slack'],
            'meta': ['meta', 'facebook', 'discussions with meta', 'meta in slack'],
            'google': ['google', 'alphabet', 'discussions with google', 'google in slack'],
            'amazon': ['amazon', 'aws', 'discussions with amazon', 'amazon in slack']
        }
        
        for company, patterns in company_patterns.items():
            if company in [c.lower() for c in self.embedding_service.company_cache]:
                for pattern in patterns:
                    if pattern in question_lower:
                        # Find the original cased company name
                        for orig_company in self.embedding_service.company_cache:
                            if orig_company.lower() == company:
                                logger.debug(f"🎯 Enhanced company detection: '{pattern}' → {orig_company}")
                                return orig_company
        
        return None
    
    def _enhance_search_query(self, question: str, company_filter: Optional[str] = None) -> str:
        """Create enhanced search query that preserves company detection"""
        question_lower = question.lower()
        
        # MINIMAL enhancement that preserves original semantic meaning
        # Don't heavily modify the query as it breaks company detection
        
        if company_filter:
            # For company-specific queries, keep the original question but add company context
            if any(pattern in question_lower for pattern in [
                'conversations', 'discussed', 'talked about', 'meetings', 'calls'
            ]):
                # Add minimal context without changing the core query
                enhanced_query = f"{question} {company_filter}"
                logger.debug(f"🔍 Minimally enhanced search query: '{question}' → '{enhanced_query}'")
                return enhanced_query
        
        # For all other cases, return the original question to preserve semantic meaning
        logger.debug(f"🔍 Using original query (no enhancement): '{question}'")
        return question
    
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
    
    def _index_slack_message_realtime(self, event: Dict[str, Any]) -> bool:
        """Real-time indexing of Slack messages (only index if they contain relevant entities)"""
        try:
            message_id = event.get('ts')
            text = event.get('text', '')
            channel_id = event.get('channel')
            user_id = event.get('user')
            thread_ts = event.get('thread_ts')
            
            if not text or len(text) < 10:  # Skip very short messages
                return False
            
            # Pre-check: Only index if message contains relevant entities (for efficiency)
            entities = self.embedding_service.extract_entities_from_text(text)
            has_entities = any(entities.values()) if entities else False
            
            if not has_entities:
                return False  # Skip indexing - no relevant business entities found
            
            # Get channel and user info (with caching for real-time performance)
            try:
                channel_info = self.client.conversations_info(channel=channel_id)
                channel_name = channel_info['channel']['name'] if channel_info['ok'] else f"Channel-{channel_id}"
            except Exception:
                channel_name = f"Channel-{channel_id}"
            
            try:
                user_info = self.client.users_info(user=user_id)
                user_name = user_info['user']['real_name'] if user_info['ok'] else f"User-{user_id}"
            except Exception:
                user_name = f"User-{user_id}"
            
            # Prepare metadata
            metadata = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "user_id": user_id,
                "user_name": user_name,
                "ts": message_id,
                "thread_ts": thread_ts,
                "indexed_from": "realtime"
            }
            
            # Add to embedding service (with entity awareness)
            success = self.embedding_service.add_slack_message(
                message_id=message_id,
                content=text,
                metadata=metadata
            )
            
            # Save to database if successful
            if success:
                try:
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
                    logger.error(f"Error saving real-time message to database: {e}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in real-time message indexing: {e}")
            return False
    
    def _show_sales_interface(self, respond, session_key):
        """Show the main sales interface (ephemeral)"""
        # Start a new session
        active_sessions[session_key] = {
            'started': datetime.utcnow(),
            'context': []
        }
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🤖 *Sales Assistant* (Only visible to you)"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Chat"},
                        "action_id": "open_chat",
                        "value": session_key,
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🧹 Clear History"},
                        "action_id": "clear_history",
                        "value": session_key
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔚 End Session"},
                        "action_id": "end_session",
                        "value": session_key,
                        "style": "danger"
                    }
                ]
            }
        ]
        
        respond({
            "response_type": "ephemeral",
            "blocks": blocks
        })
    
    def _handle_sales_query(self, question, channel_id, user_id, respond):
        """Handle a direct sales query"""
        try:
            # Get user info for better context
            user_info = self.client.users_info(user=user_id)
            user_name = user_info['user']['real_name'] if user_info['ok'] else 'Unknown User'
            
            # Generate response
            response_data = self._process_sales_question(
                question=question,
                channel_id=channel_id,
                user_id=user_id,
                user_name=user_name,
                thread_ts=None
            )
            
            # Save conversation
            self._save_conversation(
                channel_id=channel_id,
                user_id=user_id,
                question=question,
                answer=response_data['answer'],
                sources=response_data['sources']
            )
            
            # Handle write operations specially
            if response_data.get('is_write'):
                if response_data.get('requires_confirmation'):
                    # Show ephemeral confirmation for write operations
                    self._show_write_confirmation(respond, response_data)
                else:
                    # Show result ephemerally
                    respond({
                        "response_type": "ephemeral",
                        "text": self._format_response(response_data)
                    })
            else:
                # Show read results ephemerally
                respond({
                    "response_type": "ephemeral", 
                    "text": self._format_response(response_data)
                })
                
        except Exception as e:
            logger.error(f"Error handling sales query: {e}")
            respond({
                "response_type": "ephemeral",
                "text": "Sorry, I encountered an error processing your question. Please try again."
            })
    
    def _show_write_confirmation(self, respond, response_data):
        """Show ephemeral confirmation for write operations"""
        # Get session key from parsed command if available
        parsed_command = response_data.get('parsed_command', {})
        channel_id = parsed_command.get('channel_id', '')
        user_id = parsed_command.get('user_id', '')
        session_key = f"{channel_id}:{user_id}"
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Salesforce Write Operation* (Only visible to you)\n\n{response_data.get('answer', '')}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Confirm"},
                        "action_id": "confirm_write",
                        "style": "primary",
                        "value": json.dumps(parsed_command)
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Cancel"},
                        "action_id": "cancel_write",
                        "style": "danger"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✏️ Edit"},
                        "action_id": "edit_write"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Chat"},
                        "action_id": "open_chat",
                        "value": session_key
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🧹 Clear History"},
                        "action_id": "clear_history",
                        "value": session_key
                    }
                ]
            }
        ]
        
        respond({
            "response_type": "ephemeral",
            "blocks": blocks
        })
    
    def _send_ephemeral_response(self, client, channel_id, user_id, response_data):
        """Send an ephemeral response to a user in a channel, fallback to DM if bot not in channel"""
        try:
            response_text = self._format_response(response_data)
            session_key = f"{channel_id}:{user_id}"
            
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🤖 {response_text}\n\n_This message is only visible to you._"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "💬 Continue Chat"},
                            "action_id": "open_chat",
                            "value": session_key,
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🧹 Clear History"},
                            "action_id": "clear_history",
                            "value": session_key
                        }
                    ]
                }
            ]
            
            try:
                # Try ephemeral message first
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=f"🤖 {response_text}\n\n_This message is only visible to you._",
                    blocks=blocks
                )
            except Exception as ephemeral_error:
                logger.info(f"Ephemeral message failed (likely bot not in channel), sending DM instead: {ephemeral_error}")
                
                # Fallback to DM
                try:
                    # Open DM conversation with user
                    dm_response = client.conversations_open(users=[user_id])
                    if dm_response['ok']:
                        dm_channel = dm_response['channel']['id']
                        
                        # Send DM with response
                        client.chat_postMessage(
                            channel=dm_channel,
                            text=f"🤖 {response_text}\n\n_Response to your question in #{channel_id}_",
                            blocks=[
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"🤖 {response_text}\n\n_Response to your question in the channel_"
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "💬 Continue Chat"},
                                            "action_id": "open_chat",
                                            "value": session_key,
                                            "style": "primary"
                                        },
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "🧹 Clear History"},
                                            "action_id": "clear_history",
                                            "value": session_key
                                        }
                                    ]
                                }
                            ]
                        )
                    else:
                        logger.error(f"Failed to open DM with user {user_id}")
                        
                except Exception as dm_error:
                    logger.error(f"Failed to send DM: {dm_error}")
            
        except Exception as e:
            logger.error(f"Error sending response: {e}")
    
    def _send_ephemeral_write_confirmation(self, client, channel_id, user_id, response_data):
        """Send an ephemeral write confirmation to a user in a channel, fallback to DM if bot not in channel"""
        try:
            session_key = f"{channel_id}:{user_id}"
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Salesforce Write Operation* (Only visible to you)\n\n{response_data.get('answer', '')}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✅ Confirm"},
                            "action_id": "confirm_write",
                            "style": "primary",
                            "value": json.dumps(response_data.get('parsed_command', {}))
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ Cancel"},
                            "action_id": "cancel_write",
                            "style": "danger"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✏️ Edit"},
                            "action_id": "edit_write"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "💬 Chat"},
                            "action_id": "open_chat",
                            "value": session_key
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🧹 Clear History"},
                            "action_id": "clear_history",
                            "value": session_key
                        }
                    ]
                }
            ]
            
            try:
                # Try ephemeral message first
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="⚠️ Salesforce Write Operation Confirmation",
                    blocks=blocks
                )
            except Exception as ephemeral_error:
                logger.info(f"Ephemeral confirmation failed (likely bot not in channel), sending DM instead: {ephemeral_error}")
                
                # Fallback to DM
                try:
                    # Open DM conversation with user
                    dm_response = client.conversations_open(users=[user_id])
                    if dm_response['ok']:
                        dm_channel = dm_response['channel']['id']
                        
                        # Send DM with confirmation
                        client.chat_postMessage(
                            channel=dm_channel,
                            text="⚠️ Salesforce Write Operation Confirmation",
                            blocks=[
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"⚠️ *Salesforce Write Operation*\n\n{response_data.get('answer', '')}\n\n_Response to your question in the channel_"
                                    }
                                },
                                {
                                    "type": "actions",
                                    "elements": [
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "✅ Confirm"},
                                            "action_id": "confirm_write",
                                            "style": "primary",
                                            "value": json.dumps(response_data.get('parsed_command', {}))
                                        },
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "❌ Cancel"},
                                            "action_id": "cancel_write",
                                            "style": "danger"
                                        },
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "💬 Chat"},
                                            "action_id": "open_chat",
                                            "value": session_key
                                        },
                                        {
                                            "type": "button",
                                            "text": {"type": "plain_text", "text": "🧹 Clear History"},
                                            "action_id": "clear_history",
                                            "value": session_key
                                        }
                                    ]
                                }
                            ]
                        )
                    else:
                        logger.error(f"Failed to open DM with user {user_id}")
                        
                except Exception as dm_error:
                    logger.error(f"Failed to send DM: {dm_error}")
            
        except Exception as e:
            logger.error(f"Error sending write confirmation: {e}")

    def get_handler(self):
        """Get the FastAPI request handler"""
        return SlackRequestHandler(self.app)
    
    async def handle_request(self, request):
        """Handle Slack request asynchronously"""
        handler = SlackRequestHandler(self.app)
        return handler.handle(request)

    def enable_realtime_indexing(self):
        """Enable real-time indexing of new messages"""
        self.realtime_indexing_enabled = True
        logger.info("🚀 Real-time Slack message indexing ENABLED")
    
    def disable_realtime_indexing(self):
        """Disable real-time indexing of new messages"""
        self.realtime_indexing_enabled = False
        logger.info("⏸️ Real-time Slack message indexing DISABLED")

    def _ensure_bot_in_channel_for_interaction(self, channel_id, channel_name):
        """Ensure the bot is in the channel for interaction (only when user explicitly uses it)"""
        try:
            # Check if bot is already in channel
            members_response = self.client.conversations_members(channel=channel_id)
            if members_response.get('ok'):
                bot_user_id = self.client.auth_test().get('user_id')
                if bot_user_id in members_response.get('members', []):
                    logger.debug(f"Bot already in #{channel_name}")
                    return True
            
            # Try to join the channel since user wants to interact
            join_response = self.client.conversations_join(channel=channel_id)
            if join_response.get('ok'):
                logger.info(f"🤖 Bot joined #{channel_name} for user interaction")
                return True
            else:
                logger.warning(f"❌ Bot could not join #{channel_name}: {join_response.get('error')}")
                return False
                
        except Exception as e:
            logger.warning(f"Error ensuring bot in #{channel_name}: {e}")
            return False

    def _show_sales_interface(self, respond, session_key):
        """Show the main sales interface (ephemeral)"""
        # Start a new session
        active_sessions[session_key] = {
            'started': datetime.utcnow(),
            'context': []
        }
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🤖 *Sales Assistant* (Only visible to you)"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Chat"},
                        "action_id": "open_chat",
                        "value": session_key,
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🧹 Clear History"},
                        "action_id": "clear_history",
                        "value": session_key
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔚 End Session"},
                        "action_id": "end_session",
                        "value": session_key,
                        "style": "danger"
                    }
                ]
            }
        ]
        
        respond({
            "response_type": "ephemeral",
            "blocks": blocks
        })

    def clear_all_active_sessions(self):
        """Clear all active sessions"""
        logger.info("Clearing all active sessions")
        active_sessions.clear()
        logger.info("✅ All active sessions cleared") 