import openai
import logging
from typing import List, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

class GenerationService:
    def __init__(self, openai_api_key: str):
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
    
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