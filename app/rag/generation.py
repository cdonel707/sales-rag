import openai
import logging
from typing import List, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

class GenerationService:
    def __init__(self, openai_api_key: str, sf_client=None):
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.sf_client = sf_client
        self.write_parser = None
    
    def _get_write_parser(self):
        """Lazy initialization of write parser to avoid circular imports"""
        if self.write_parser is None and self.sf_client is not None:
            from app.rag.write_operations import WriteOperationParser
            self.write_parser = WriteOperationParser(self.sf_client)
        return self.write_parser
    
    def process_query(self, 
                     question: str, 
                     context_documents: List[Dict[str, Any]],
                     thread_context: Optional[List[Dict[str, Any]]] = None,
                     conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Process a query - either read (RAG) or write operation"""
        
        # Check if this is a write operation
        write_parser = self._get_write_parser()
        if write_parser:
            # Extract recent entities from context for better write operation parsing
            recent_entities = self._extract_entities_from_context(context_documents, conversation_history)
            
            # Build user context string
            user_context = ""
            if conversation_history:
                user_context = f"Recent conversation: {self._format_conversation_history(conversation_history)}"
            
            parsed_command = write_parser.parse_write_command(question, user_context, recent_entities)
            
            if parsed_command.get('is_write'):
                # Handle write operation
                if parsed_command.get('operation') == 'unclear':
                    return {
                        "answer": f"I understand you want to modify Salesforce data, but I need more information. {parsed_command.get('suggestions', '')}",
                        "is_write": True,
                        "requires_confirmation": False,
                        "sources": [],
                        "context_used": 0
                    }
                elif parsed_command.get('operation') == 'error':
                    return {
                        "answer": parsed_command.get('message', 'Sorry, I had trouble understanding that command.'),
                        "is_write": True,
                        "requires_confirmation": False,
                        "sources": [],
                        "context_used": 0
                    }
                else:
                    # Valid write operation - return confirmation request
                    return {
                        "answer": f"🤖 **Salesforce Write Operation Detected**\n\n{parsed_command.get('confirmation', 'I need to modify Salesforce data.')}\n\n**Please confirm:** Reply with 'yes' to proceed or 'no' to cancel.",
                        "is_write": True,
                        "requires_confirmation": True,
                        "parsed_command": parsed_command,
                        "sources": [],
                        "context_used": 0
                    }
        
        # Not a write operation - proceed with normal RAG response
        return self.generate_rag_response(question, context_documents, thread_context, conversation_history)
    
    def execute_confirmed_write_operation(self, parsed_command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a confirmed write operation"""
        write_parser = self._get_write_parser()
        if not write_parser:
            return {
                "answer": "❌ Write operations are not available - Salesforce client not configured.",
                "is_write": True,
                "sources": [],
                "context_used": 0
            }
        
        try:
            result = write_parser.execute_write_operation(parsed_command)
            
            return {
                "answer": result.get('message', 'Operation completed'),
                "is_write": True,
                "write_success": result.get('success', False),
                "record_id": result.get('record_id'),
                "sources": [],
                "context_used": 0
            }
        except Exception as e:
            logger.error(f"Error executing write operation: {e}")
            return {
                "answer": f"❌ Error executing write operation: {str(e)}",
                "is_write": True,
                "write_success": False,
                "sources": [],
                "context_used": 0
            }

    def generate_rag_response(self, 
                            question: str, 
                            context_documents: List[Dict[str, Any]],
                            thread_context: Optional[List[Dict[str, Any]]] = None,
                            conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Generate a RAG response using retrieved context"""
        
        try:
            # Build context from retrieved documents
            retrieved_context = self._format_retrieved_context(context_documents)
            
            # Build thread context if available
            thread_context_str = ""
            if thread_context:
                thread_context_str = self._format_thread_context(thread_context)
            
            # Build conversation history
            conversation_str = ""
            if conversation_history:
                conversation_str = self._format_conversation_history(conversation_history)
            
            # Create the prompt
            system_prompt = self._create_system_prompt()
            user_prompt = self._create_user_prompt(
                question, retrieved_context, thread_context_str, conversation_str
            )
            
            # Generate response
            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            answer = response.choices[0].message.content
            
            # Extract sources used
            sources = self._extract_sources(context_documents)
            
            return {
                "answer": answer,
                "sources": sources,
                "context_used": len(context_documents),
                "thread_context_used": len(thread_context) if thread_context else 0
            }
            
        except Exception as e:
            logger.error(f"Error generating RAG response: {e}")
            return {
                "answer": "I apologize, but I encountered an error while processing your question. Please try again.",
                "sources": [],
                "context_used": 0,
                "thread_context_used": 0
            }
    
    def _create_system_prompt(self) -> str:
        return """You are a helpful AI assistant that answers questions based on Salesforce data and Slack conversations. 

Your role is to:
1. Answer questions using the provided context from Salesforce records and Slack messages
2. Be accurate and only use information from the provided context
3. If the context doesn't contain relevant information, say so clearly
4. Prioritize thread context when answering questions in a thread
5. Provide specific details from Salesforce records when relevant (amounts, dates, names, etc.)
6. Be conversational and helpful while maintaining professionalism
7. If you reference specific data, mention the source (Salesforce record type or Slack conversation)

Guidelines:
- Always base your answers on the provided context
- Don't make up information not present in the context
- Be clear about what information is available vs. not available
- Use a helpful, professional tone suitable for business communications"""

    def _create_user_prompt(self, question: str, retrieved_context: str, 
                          thread_context: str, conversation_history: str) -> str:
        prompt_parts = [f"Question: {question}"]
        
        if thread_context:
            prompt_parts.append(f"\nThread Context (prioritize this for context-specific questions):\n{thread_context}")
        
        if conversation_history:
            prompt_parts.append(f"\nPrevious Conversation:\n{conversation_history}")
        
        if retrieved_context:
            prompt_parts.append(f"\nRelevant Information from Salesforce and Slack:\n{retrieved_context}")
        else:
            prompt_parts.append("\nNo relevant information found in the knowledge base.")
        
        prompt_parts.append("\nPlease provide a helpful answer based on the available context:")
        
        return "\n".join(prompt_parts)
    
    def _format_retrieved_context(self, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return "No relevant documents found."
        
        formatted_docs = []
        for doc in documents:
            source = doc.get('source', 'unknown')
            metadata = doc.get('metadata', {})
            content = doc.get('content', '')
            
            if source == 'salesforce':
                object_type = metadata.get('object_type', 'Unknown')
                formatted_docs.append(f"[Salesforce {object_type}] {content}")
            elif source == 'slack':
                channel_name = metadata.get('channel_name', 'Unknown Channel')
                user_name = metadata.get('user_name', 'Unknown User')
                formatted_docs.append(f"[Slack #{channel_name} - {user_name}] {content}")
            else:
                formatted_docs.append(f"[{source}] {content}")
        
        return "\n\n".join(formatted_docs)
    
    def _format_thread_context(self, thread_messages: List[Dict[str, Any]]) -> str:
        if not thread_messages:
            return ""
        
        formatted_messages = []
        for msg in thread_messages:
            metadata = msg.get('metadata', {})
            content = msg.get('content', '')
            user_name = metadata.get('user_name', 'Unknown User')
            timestamp = metadata.get('ts', '')
            
            formatted_messages.append(f"{user_name}: {content}")
        
        return "\n".join(formatted_messages)
    
    def _format_conversation_history(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return ""
        
        formatted_history = []
        for item in history[-5:]:  # Last 5 exchanges
            formatted_history.append(f"Q: {item.get('question', '')}")
            formatted_history.append(f"A: {item.get('answer', '')}")
        
        return "\n".join(formatted_history)
    
    def _extract_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        sources = []
        for doc in documents:
            metadata = doc.get('metadata', {})
            source = doc.get('source', 'unknown')
            
            if source == 'salesforce':
                sources.append({
                    "type": "salesforce",
                    "object_type": metadata.get('object_type', 'Unknown'),
                    "record_id": metadata.get('record_id', ''),
                    "title": metadata.get('title', 'Salesforce Record')
                })
            elif source == 'slack':
                sources.append({
                    "type": "slack",
                    "channel": metadata.get('channel_name', 'Unknown Channel'),
                    "user": metadata.get('user_name', 'Unknown User'),
                    "timestamp": metadata.get('ts', '')
                })
        
        return sources
    
    def _extract_entities_from_context(self, context_documents: List[Dict[str, Any]], 
                                     conversation_history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
        """Extract entities (Salesforce records) from context for write operation inference"""
        entities = []
        
        # Extract from retrieved context documents (most recent searches)
        for doc in context_documents:
            metadata = doc.get('metadata', {})
            source = doc.get('source', '')
            
            if source == 'salesforce':
                entities.append({
                    "type": "salesforce",
                    "object_type": metadata.get('object_type', 'Unknown'),
                    "title": metadata.get('title', 'Unknown'),
                    "record_id": metadata.get('record_id', ''),
                    "name": metadata.get('name', metadata.get('title', 'Unknown'))
                })
        
        # Extract from conversation history (previous Q&A about specific records)
        if conversation_history:
            for item in conversation_history[-3:]:  # Last 3 exchanges
                answer = item.get('answer', '')
                # Look for Salesforce record mentions in answers
                if 'Opportunity:' in answer or 'Account:' in answer or 'Contact:' in answer:
                    # Simple extraction - could be more sophisticated
                    lines = answer.split('\n')
                    for line in lines:
                        if 'Opportunity:' in line:
                            name = line.split('Opportunity:')[-1].strip()
                            entities.append({
                                "type": "salesforce",
                                "object_type": "Opportunity", 
                                "title": name,
                                "name": name,
                                "record_id": ""
                            })
                        elif 'Account:' in line:
                            name = line.split('Account:')[-1].strip()
                            entities.append({
                                "type": "salesforce",
                                "object_type": "Account",
                                "title": name, 
                                "name": name,
                                "record_id": ""
                            })
        
        return entities 