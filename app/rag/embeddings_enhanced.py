"""
Enhanced embedding service with thread-aware entity context
"""

import json
import logging
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

class ThreadAwareEmbeddingMixin:
    """Mixin to add thread-aware functionality to EmbeddingService"""
    
    def add_slack_message_with_thread_context(self, message_id: str, content: str, 
                                            metadata: Dict[str, Any], slack_client=None) -> bool:
        """Enhanced message indexing with automatic thread context propagation"""
        try:
            # Get basic thread information
            thread_ts = metadata.get('thread_ts')
            channel_id = metadata.get('channel_id')
            
            # If this message is part of a thread, analyze thread context
            if thread_ts and slack_client:
                thread_entities = self._analyze_thread_entities(
                    slack_client, channel_id, thread_ts, current_content=content
                )
                
                if thread_entities:
                    # Enhance metadata with thread context
                    metadata.update({
                        'thread_entities_json': json.dumps(thread_entities),
                        'thread_has_entities': True,
                        'enhanced_context': True
                    })
                    
                    # Add specific flags for important entities
                    companies = thread_entities.get('companies', [])
                    if any('zillow' in company.lower() for company in companies):
                        metadata['thread_has_zillow'] = True
                    
                    logger.info(f"Enhanced message {message_id} with thread entities: {companies[:3]}")
            
            # Use original add_slack_message method
            return self.add_slack_message(message_id, content, metadata)
            
        except Exception as e:
            logger.error(f"Error in thread-aware message indexing: {e}")
            # Fallback to regular indexing
            return self.add_slack_message(message_id, content, metadata)
    
    def _analyze_thread_entities(self, slack_client, channel_id: str, thread_ts: str, 
                               current_content: str = "") -> Dict[str, List[str]]:
        """Analyze all messages in a thread to extract entities"""
        try:
            # Get all messages in the thread
            thread_response = slack_client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=50  # Reasonable limit for thread analysis
            )
            
            if not thread_response.get('ok'):
                logger.warning(f"Could not fetch thread messages: {thread_response.get('error')}")
                return {}
            
            thread_messages = thread_response.get('messages', [])
            
            # Combine all message content including current message
            all_content = [current_content] if current_content else []
            for msg in thread_messages:
                text = msg.get('text', '')
                if text and len(text) > 5:  # Skip very short messages
                    all_content.append(text)
            
            # Extract entities from combined content
            combined_entities = {
                'companies': set(),
                'contacts': set(),
                'opportunities': set()
            }
            
            for content in all_content:
                entities = self.extract_entities_from_text(content)
                if entities:
                    if entities.get('companies'):
                        combined_entities['companies'].update(entities['companies'])
                    if entities.get('contacts'):
                        combined_entities['contacts'].update(entities['contacts'])
                    if entities.get('opportunities'):
                        combined_entities['opportunities'].update(entities['opportunities'])
            
            # Convert sets to lists
            return {
                'companies': list(combined_entities['companies']),
                'contacts': list(combined_entities['contacts']),
                'opportunities': list(combined_entities['opportunities'])
            }
            
        except Exception as e:
            logger.error(f"Error analyzing thread entities: {e}")
            return {}
    
    def search_with_thread_context(self, query: str, n_results: int = 10, 
                                 source_filter: Optional[str] = None,
                                 include_thread_context: bool = True) -> List[Dict[str, Any]]:
        """Enhanced search that includes thread context for relevant results"""
        try:
            # First, do regular search
            results = self.search_similar_content(
                query=query,
                n_results=n_results,
                source_filter=source_filter
            )
            
            if not include_thread_context:
                return results
            
            # Group results by threads to add context
            enhanced_results = []
            seen_messages = set()
            
            for result in results:
                metadata = result.get('metadata', {})
                message_id = metadata.get('ts')
                
                if message_id in seen_messages:
                    continue
                
                seen_messages.add(message_id)
                
                # If this message has thread context, include it
                thread_entities = metadata.get('thread_entities_json')
                if thread_entities:
                    try:
                        entities = json.loads(thread_entities)
                        result['thread_entities'] = entities
                        result['thread_context_available'] = True
                    except json.JSONDecodeError:
                        pass
                
                enhanced_results.append(result)
            
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Error in thread-aware search: {e}")
            return results if 'results' in locals() else []
    
    def get_thread_messages_by_entity(self, entity_name: str, 
                                    entity_type: str = "company") -> List[Dict[str, Any]]:
        """Get all messages from threads that mention a specific entity"""
        try:
            # Search for messages with thread entities
            results = self.search_similar_content(
                query=entity_name,
                n_results=100,
                source_filter="slack"
            )
            
            entity_messages = []
            for result in results:
                metadata = result.get('metadata', {})
                thread_entities_json = metadata.get('thread_entities_json')
                
                if thread_entities_json:
                    try:
                        thread_entities = json.loads(thread_entities_json)
                        entity_list = thread_entities.get(f"{entity_type}s", [])
                        
                        # Check if entity is mentioned in thread
                        if any(entity_name.lower() in entity.lower() for entity in entity_list):
                            result['matched_entity'] = entity_name
                            result['entity_type'] = entity_type
                            result['thread_entities'] = thread_entities
                            entity_messages.append(result)
                    except json.JSONDecodeError:
                        continue
            
            return entity_messages
            
        except Exception as e:
            logger.error(f"Error getting thread messages by entity: {e}")
            return []


def create_thread_aware_embedding_service(embedding_service):
    """Add thread-aware capabilities to an existing embedding service"""
    
    # Add the mixin methods to the existing service
    class ThreadAwareEmbeddingService(embedding_service.__class__, ThreadAwareEmbeddingMixin):
        pass
    
    # Create new instance with enhanced capabilities
    enhanced_service = ThreadAwareEmbeddingService()
    
    # Copy all attributes from original service
    for attr_name in dir(embedding_service):
        if not attr_name.startswith('_') and hasattr(embedding_service, attr_name):
            attr_value = getattr(embedding_service, attr_name)
            if not callable(attr_value):  # Copy non-method attributes
                setattr(enhanced_service, attr_name, attr_value)
    
    return enhanced_service 