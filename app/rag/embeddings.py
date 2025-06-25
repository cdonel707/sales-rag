import openai
import chromadb
from chromadb.config import Settings
import logging
from typing import List, Dict, Any, Optional, Set
import hashlib
import json
import re
import time
from datetime import datetime, timedelta

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
        
        # Cache for company names and entities
        self.company_cache = set()
        self.contact_cache = set()
        self.opportunity_cache = set()
    
    def update_entity_cache(self, salesforce_client):
        """Update cache of company names, contacts, and opportunities from Salesforce"""
        try:
            # Get companies/accounts
            accounts = salesforce_client.get_accounts(limit=1000)
            if accounts:
                self.company_cache = {account.get('Name', '').lower() for account in accounts if account and account.get('Name')}
            else:
                logger.info("No accounts found in Salesforce")
                self.company_cache = set()
            
            # Get contacts  
            contacts = salesforce_client.get_contacts(limit=1000)
            if contacts:
                for contact in contacts:
                    if contact:  # Ensure contact is not None
                        if contact.get('FirstName') and contact.get('LastName'):
                            full_name = f"{contact['FirstName']} {contact['LastName']}"
                            self.contact_cache.add(full_name.lower())
                        # Safely handle Account relationship
                        account_data = contact.get('Account')
                        if account_data and account_data.get('Name'):
                            self.company_cache.add(account_data['Name'].lower())
            else:
                logger.info("No contacts found in Salesforce")
            
            # Get opportunities
            opportunities = salesforce_client.get_opportunities(limit=1000)
            if opportunities:
                for opp in opportunities:
                    if opp:  # Ensure opportunity is not None
                        if opp.get('Name'):
                            self.opportunity_cache.add(opp['Name'].lower())
                        # Safely handle Account relationship
                        account_data = opp.get('Account')
                        if account_data and account_data.get('Name'):
                            self.company_cache.add(account_data['Name'].lower())
            else:
                logger.info("No opportunities found in Salesforce")
            
            logger.info(f"Updated entity cache: {len(self.company_cache)} companies, {len(self.contact_cache)} contacts, {len(self.opportunity_cache)} opportunities")
            
        except Exception as e:
            logger.error(f"Error updating entity cache: {e}")
            # Initialize empty caches on error to prevent subsequent failures
            self.company_cache = set()
            self.contact_cache = set()
            self.opportunity_cache = set()
    
    def extract_entities_from_text(self, text: str, metadata: Dict[str, Any] = None) -> Dict[str, List[str]]:
        """Enhanced entity extraction with contextual intelligence"""
        text_lower = text.lower()
        found_entities = {
            'companies': [],
            'contacts': [], 
            'opportunities': []
        }
        
        # METHOD 1: Direct name mentions (existing behavior)
        for company in self.company_cache:
            if len(company) > 2 and company in text_lower:
                found_entities['companies'].append(company)
        
        for contact in self.contact_cache:
            if contact in text_lower:
                found_entities['contacts'].append(contact)
        
        for opp in self.opportunity_cache:
            if len(opp) > 2 and opp in text_lower:
                found_entities['opportunities'].append(opp)
        
        # METHOD 2: Enhanced contextual intelligence
        if metadata:
            # Channel-based company detection
            channel_name = metadata.get('channel_name', '').lower()
            
            # Detect company-dedicated channels
            for company in self.company_cache:
                company_clean = company.lower().replace(' ', '-').replace('.', '-')
                if (f"-{company_clean}" in channel_name or 
                    f"{company_clean}-" in channel_name or
                    channel_name == company_clean):
                    if company not in found_entities['companies']:
                        found_entities['companies'].append(company)
                        logger.debug(f"🎯 Channel context: #{channel_name} → {company}")
            
            # Email domain intelligence
            self._extract_entities_from_email_domains(text, found_entities)
            
            # User context intelligence (if we have user email from metadata)
            user_email = metadata.get('user_email', '').lower()
            if user_email:
                self._extract_entities_from_user_context(user_email, found_entities)
        
        return found_entities
    
    def _extract_entities_from_email_domains(self, text: str, found_entities: Dict[str, List[str]]):
        """Extract company entities based on email domains mentioned in text"""
        import re
        
        # Find email addresses in text
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text.lower())
        
        for email in emails:
            domain = email.split('@')[1] if '@' in email else ''
            
            # Map common domain patterns to companies
            domain_company_map = {
                'zillow.com': 'Zillow',
                'zillowgroup.com': 'Zillow',
                'microsoft.com': 'Microsoft',
                'google.com': 'Google',
                'amazon.com': 'Amazon',
                'apple.com': 'Apple',
                'salesforce.com': 'Salesforce',
                'meta.com': 'Meta',
                'facebook.com': 'Meta'
            }
            
            # Check if domain matches known companies
            for domain_pattern, company in domain_company_map.items():
                if domain == domain_pattern or domain.endswith(f'.{domain_pattern}'):
                    if company in self.company_cache and company not in found_entities['companies']:
                        found_entities['companies'].append(company)
                        logger.debug(f"📧 Email domain: {email} → {company}")
                        break
            
            # Also check against our company cache for domain matches
            for company in self.company_cache:
                company_domain = company.lower().replace(' ', '').replace('.', '') + '.com'
                if domain == company_domain:
                    if company not in found_entities['companies']:
                        found_entities['companies'].append(company)
                        logger.debug(f"📧 Inferred domain: {email} → {company}")
    
    def _extract_entities_from_user_context(self, user_email: str, found_entities: Dict[str, List[str]]):
        """Extract company entities based on user's email domain"""
        if '@' not in user_email:
            return
            
        domain = user_email.split('@')[1].lower()
        
        # Map domains to companies (same logic as email extraction)
        domain_company_map = {
            'zillow.com': 'Zillow',
            'zillowgroup.com': 'Zillow',
            'microsoft.com': 'Microsoft',
            'google.com': 'Google',
            'amazon.com': 'Amazon',
            'apple.com': 'Apple',
            'salesforce.com': 'Salesforce',
            'meta.com': 'Meta',
            'facebook.com': 'Facebook'
        }
        
        for domain_pattern, company in domain_company_map.items():
            if domain == domain_pattern:
                if company in self.company_cache and company not in found_entities['companies']:
                    found_entities['companies'].append(company)
                    logger.debug(f"👤 User context: {user_email} → {company}")
                    break
    
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
        """Add a Slack message to the vector database with entity extraction"""
        try:
            embedding = self.generate_embedding(content)
            if not embedding:
                return False
            
            # Extract entities from the message with enhanced contextual intelligence
            entities = self.extract_entities_from_text(content, metadata)
            
            # Create unique ID based on message content hash
            doc_id = hashlib.md5(f"slack_{message_id}".encode()).hexdigest()
            
            # Enhanced metadata with entities (serialize entities to JSON for ChromaDB compatibility)
            enhanced_metadata = {
                **metadata,
                "source_type": "slack",
                "message_id": message_id or "",
                "indexed_at": datetime.utcnow().isoformat(),
                "entities_json": json.dumps(entities),  # Serialize entities as JSON string
                "has_companies": len(entities['companies']) > 0,
                "has_contacts": len(entities['contacts']) > 0,
                "has_opportunities": len(entities['opportunities']) > 0
            }
            
            # Ensure no None values in metadata (ChromaDB doesn't accept None)
            cleaned_metadata = {}
            for key, value in enhanced_metadata.items():
                if value is None:
                    cleaned_metadata[key] = ""  # Convert None to empty string
                elif isinstance(value, bool):
                    cleaned_metadata[key] = value
                elif isinstance(value, (int, float)):
                    cleaned_metadata[key] = value
                else:
                    cleaned_metadata[key] = str(value)  # Ensure strings
            
            self.slack_collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[cleaned_metadata],
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
            
            # Prepare metadata
            enhanced_metadata = {
                **metadata,
                "source_type": "salesforce",
                "record_id": record_id or "",
                "indexed_at": datetime.utcnow().isoformat()
            }
            
            # Ensure no None values in metadata (ChromaDB doesn't accept None)
            cleaned_metadata = {}
            for key, value in enhanced_metadata.items():
                if value is None:
                    cleaned_metadata[key] = ""  # Convert None to empty string
                elif isinstance(value, bool):
                    cleaned_metadata[key] = value
                elif isinstance(value, (int, float)):
                    cleaned_metadata[key] = value
                else:
                    cleaned_metadata[key] = str(value)  # Ensure strings
            
            self.salesforce_collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[cleaned_metadata],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            logger.error(f"Error adding Salesforce record to vector DB: {e}")
            return False
    
    def search_similar_content(self, query: str, n_results: int = 10, 
                             source_filter: Optional[str] = None,
                             channel_filter: Optional[str] = None,
                             thread_filter: Optional[str] = None,
                             company_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for similar content across both collections with company filtering"""
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
            if company_filter:
                # This is approximate - ChromaDB doesn't support complex array searches well
                # We'll filter results post-query
                pass
            
            if not source_filter or source_filter == "slack":
                slack_results = self.slack_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results * 2 if company_filter else (n_results // 2 if not source_filter else n_results),
                    where=slack_where if (channel_filter or thread_filter) else {"source_type": "slack"}
                )
                
                for i, doc in enumerate(slack_results['documents'][0]):
                    metadata = slack_results['metadatas'][0][i]
                    
                    # Apply company filter if specified
                    if company_filter:
                        entities_json = metadata.get('entities_json', '{}')  
                        try:
                            entities = json.loads(entities_json)
                            companies = [c.lower() for c in entities.get('companies', [])]
                            if company_filter.lower() not in companies:
                                continue
                        except json.JSONDecodeError:
                            # Skip if entities can't be decoded
                            continue
                    
                    results.append({
                        "content": doc,
                        "metadata": metadata,
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
                    metadata = sf_results['metadatas'][0][i]
                    
                    # Apply company filter for Salesforce if specified
                    if company_filter:
                        # Check if the record is related to the company
                        doc_content = doc.lower()
                        if company_filter.lower() not in doc_content:
                            continue
                    
                    results.append({
                        "content": doc,
                        "metadata": metadata,
                        "distance": sf_results['distances'][0][i] if 'distances' in sf_results else 0,
                        "source": "salesforce"
                    })
            
            # Sort by distance (similarity)
            results.sort(key=lambda x: x['distance'])
            return results[:n_results]
            
        except Exception as e:
            logger.error(f"Error searching similar content: {e}")
            return []
    
    def search_by_company(self, company_name: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Search for all content related to a specific company across Slack and Salesforce"""
        try:
            results = []
            
            # Search Slack messages that mention the company
            company_embedding = self.generate_embedding(f"messages about {company_name}")
            if not company_embedding:
                logger.error(f"Failed to generate embedding for company search: {company_name}")
                return []
            
            slack_results = self.slack_collection.query(
                query_embeddings=[company_embedding],
                n_results=n_results * 2,
                where={
                    "source_type": "slack"
                }
            )
            
            # Filter for company mentions
            for i, doc in enumerate(slack_results['documents'][0]):
                metadata = slack_results['metadatas'][0][i]
                entities_json = metadata.get('entities_json', '{}')
                try:
                    entities = json.loads(entities_json)
                    companies = [c.lower() for c in entities.get('companies', [])]
                    
                    if company_name.lower() in companies or company_name.lower() in doc.lower():
                        results.append({
                            "content": doc,
                            "metadata": metadata,
                            "source": "slack",
                            "relevance": "company_mention"
                        })
                except json.JSONDecodeError:
                    # Skip if entities can't be decoded, but still check content
                    if company_name.lower() in doc.lower():
                        results.append({
                            "content": doc,
                            "metadata": metadata,
                            "source": "slack",
                            "relevance": "company_mention"
                        })
            
            # Search Salesforce records
            sf_company_embedding = self.generate_embedding(company_name)
            if sf_company_embedding:
                sf_results = self.salesforce_collection.query(
                    query_embeddings=[sf_company_embedding],
                    n_results=n_results,
                    where={"source_type": "salesforce"}
                )
                
                for i, doc in enumerate(sf_results['documents'][0]):
                    results.append({
                        "content": doc,
                        "metadata": sf_results['metadatas'][0][i],
                        "source": "salesforce",
                        "distance": sf_results['distances'][0][i] if 'distances' in sf_results else 0,
                        "relevance": "salesforce_record"
                    })
            
            return results[:n_results]
            
        except Exception as e:
            logger.error(f"Error searching by company: {e}")
            return []
    
    def find_relevant_channels(self, slack_client, company_names: List[str]) -> List[Dict[str, Any]]:
        """Find channels relevant to companies with focused filtering criteria"""
        try:
            logger.info("🔍 Finding relevant business channels...")
            
            # Get all channels with member info
            all_channels = []
            cursor = None
            
            while True:
                # Respect Slack's rate limits
                time.sleep(61)
                
                params = {
                    'types': 'public_channel',
                    'limit': 15,  # Slack's limit for non-marketplace apps
                    'exclude_archived': True  # Only active channels
                }
                if cursor:
                    params['cursor'] = cursor
                
                response = slack_client.conversations_list(**params)
                if not response.get('ok'):
                    logger.error(f"Failed to get channels: {response.get('error')}")
                    break
                
                channels = response.get('channels', [])
                all_channels.extend(channels)
                
                cursor = response.get('response_metadata', {}).get('next_cursor')
                if not cursor:
                    break
            
            logger.info(f"📊 Found {len(all_channels)} total public channels")
            
            # Filter channels based on focused criteria
            relevant_channels = []
            
            for channel in all_channels:
                channel_name = channel.get('name', '').lower()
                num_members = channel.get('num_members', 0)
                
                # Check if channel meets our criteria
                is_relevant = False
                reason = ""
                
                # Must have 5+ members
                if num_members < 5:
                    continue
                
                # Check if it's a fern- channel
                if channel_name.startswith('fern-'):
                    is_relevant = True
                    reason = f"fern- channel with {num_members} members"
                
                # Check if it's specifically sales or meeting-reports
                elif channel_name in ['sales', 'meeting-reports']:
                    is_relevant = True
                    reason = f"priority channel ({channel_name}) with {num_members} members"
                
                # Skip if not relevant
                if not is_relevant:
                    continue
                
                relevant_channels.append({
                    'id': channel['id'],
                    'name': channel['name'],
                    'num_members': num_members,
                    'reason': reason
                })
                
                logger.info(f"   ✅ #{channel['name']}: {reason}")
            
            logger.info(f"🎯 Found {len(relevant_channels)} relevant business channels")
            return relevant_channels
            
        except Exception as e:
            logger.error(f"Error finding relevant channels: {e}")
            return []
    
    def index_channel_history(self, slack_client, channel_id: str, channel_name: str, 
                            limit: int = 1000, days_back: int = 365):
        """Index message history from a specific channel with proper Slack API rate limiting"""
        try:
            # Calculate oldest timestamp (365 days back)
            oldest = datetime.now() - timedelta(days=days_back)
            oldest_ts = oldest.timestamp()
            
            # UPDATED: Respect Slack's documented rate limits for non-marketplace apps
            # Slack allows 1 request per minute with limit of 15 messages for non-marketplace apps
            max_retries = 3
            base_wait = 61  # 61 seconds between requests (1 per minute + buffer)
            
            # Always wait before making API calls to respect rate limits
            logger.info(f"⏳ Waiting {base_wait} seconds before API call (Slack rate limiting)...")
            time.sleep(base_wait)
            
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Attempting to get history for #{channel_name} (attempt {attempt + 1}/{max_retries + 1})")
                    
                    # Get channel history with Slack's documented limit for non-marketplace apps
                    history_response = slack_client.conversations_history(
                        channel=channel_id,
                        limit=15,  # Slack's limit for non-marketplace apps
                        oldest=str(oldest_ts)
                    )
                    
                    if history_response.get('ok'):
                        break  # Success, exit retry loop
                    elif history_response.get('error') == 'ratelimited':
                        if attempt < max_retries:
                            # Use Retry-After header if available, otherwise use exponential backoff
                            retry_after = self._get_retry_after_from_response(history_response)
                            if retry_after:
                                wait_time = int(retry_after) + 5  # Add 5 seconds buffer
                                logger.warning(f"Rate limited for #{channel_name}. Slack says wait {retry_after}s, waiting {wait_time}s")
                            else:
                                # Exponential backoff on top of base rate limiting: 61s, 122s, 244s
                                wait_time = base_wait * (2 ** attempt)
                                logger.warning(f"Rate limited for #{channel_name}, no Retry-After header. Waiting {wait_time}s")
                            
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"Failed to get history for #{channel_name} after {max_retries + 1} attempts")
                            return 0
                    else:
                        logger.error(f"Failed to get history for #{channel_name}: {history_response.get('error')}")
                        return 0
                        
                except Exception as e:
                    if attempt < max_retries:
                        wait_time = base_wait * (2 ** attempt)
                        logger.warning(f"Error getting history for #{channel_name}, retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Error getting history for #{channel_name} after retries: {e}")
                        return 0
            
            messages = history_response.get('messages', [])
            logger.info(f"Retrieved {len(messages)} messages from #{channel_name}")
            indexed_count = 0
            
            # Process messages with minimal rate limiting (no additional API calls)
            for i, message in enumerate(messages):
                try:
                    # Skip bot messages and system messages
                    if message.get('bot_id') or message.get('subtype'):
                        continue
                    
                    text = message.get('text', '')
                    if len(text) < 10:  # Skip very short messages
                        continue
                    
                    # Skip user info calls to avoid additional API hits
                    user_id = message.get('user')
                    user_name = f"User-{user_id}" if user_id else 'Unknown User'
                    
                    # Prepare metadata first (needed for enhanced entity extraction)
                    metadata = {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "user_id": user_id,
                        "user_name": user_name,
                        "ts": message.get('ts'),
                        "thread_ts": message.get('thread_ts'),
                        "indexed_from": "cross_channel_search"
                    }
                    
                    # Check if message contains company/contact entities (with enhanced intelligence)
                    entities = self.extract_entities_from_text(text, metadata)
                    if not any(entities.values()):  # Skip if no entities found
                        continue
                    
                    # Add to vector database
                    success = self.add_slack_message(
                        message_id=message.get('ts'),
                        content=text,
                        metadata=metadata
                    )
                    
                    if success:
                        indexed_count += 1
                    
                    # Minimal processing delay (no additional API calls)
                    if (i + 1) % 5 == 0:  # Every 5 messages
                        logger.debug(f"Processed {i + 1} messages, pausing 1 second...")
                        time.sleep(1)
                        
                except Exception as e:
                    logger.debug(f"Error processing message in #{channel_name}: {e}")
                    continue
            
            logger.info(f"Indexed {indexed_count} messages from #{channel_name}")
            return indexed_count
            
        except Exception as e:
            logger.error(f"Error indexing channel history: {e}")
            return 0
    
    def _get_retry_after_from_response(self, response):
        """Extract Retry-After header from Slack response if available"""
        try:
            # This is a simplified approach - in reality we'd need to access the raw HTTP response
            # For now, we'll return None and use fallback delays
            return None
        except Exception:
            return None
    
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
    
    def index_all_channel_messages(self, slack_client, channel_id: str, channel_name: str, 
                                  limit: int = 100, days_back: int = 365):
        """Index ALL messages from a specific channel with proper Slack API rate limiting"""
        try:
            # Calculate oldest timestamp
            oldest = datetime.now() - timedelta(days=days_back)
            oldest_ts = oldest.timestamp()
            
            # UPDATED: Respect Slack's documented rate limits for non-marketplace apps
            max_retries = 4
            base_wait = 61  # 61 seconds between requests (1 per minute + buffer)
            
            # Always wait before making API calls to respect rate limits
            logger.info(f"⏳ Waiting {base_wait} seconds before API call (Slack rate limiting)...")
            time.sleep(base_wait)
            
            all_messages = []
            cursor = None
            page_count = 0
            max_pages = 3  # Limit to prevent infinite loops
            
            # Pagination loop to get more messages
            while page_count < max_pages:
                page_count += 1
                
                for attempt in range(max_retries + 1):
                    try:
                        logger.info(f"Attempting to get ALL messages from #{channel_name} (page {page_count}, attempt {attempt + 1}/{max_retries + 1})")
                        
                        # Get channel history with pagination and Slack's documented limits
                        params = {
                            'channel': channel_id,
                            'limit': 15,  # Slack's limit for non-marketplace apps
                            'oldest': str(oldest_ts)
                        }
                        if cursor:
                            params['cursor'] = cursor
                        
                        history_response = slack_client.conversations_history(**params)
                        
                        if history_response.get('ok'):
                            break  # Success, exit retry loop
                        elif history_response.get('error') == 'ratelimited':
                            if attempt < max_retries:
                                # Exponential backoff on top of base rate limiting
                                wait_time = base_wait * (2 ** attempt)
                                logger.warning(f"Rate limited for #{channel_name}, waiting {wait_time}s")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"Failed to get history for #{channel_name} after {max_retries + 1} attempts")
                                break
                        elif history_response.get('error') == 'not_in_channel':
                            logger.warning(f"❌ Bot not in #{channel_name} - skipping (channel may be private or archived)")
                            return 0
                        else:
                            logger.error(f"Failed to get history for #{channel_name}: {history_response.get('error')}")
                            break
                            
                    except Exception as e:
                        if attempt < max_retries:
                            wait_time = base_wait * (2 ** attempt)
                            logger.warning(f"Error getting history for #{channel_name}, retrying in {wait_time}s: {e}")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"Error getting history for #{channel_name} after retries: {e}")
                            break
                
                # Check if we got a successful response
                if not history_response.get('ok'):
                    break
                
                # Get messages from this page
                page_messages = history_response.get('messages', [])
                all_messages.extend(page_messages)
                
                logger.info(f"Retrieved {len(page_messages)} messages from #{channel_name} (page {page_count})")
                
                # Check if there are more messages (has_more and cursor)
                has_more = history_response.get('has_more', False)
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                
                if not has_more or not cursor:
                    logger.info(f"No more messages available for #{channel_name}")
                    break
                
                # Wait before next page to respect rate limits
                logger.info(f"⏳ Waiting {base_wait} seconds before next page...")
                time.sleep(base_wait)
            
            logger.info(f"Retrieved total of {len(all_messages)} messages from #{channel_name} across {page_count} pages")
            
            # NEW: Index thread replies for comprehensive coverage
            self._index_thread_replies(slack_client, channel_id, channel_name, all_messages, days_back)
            
            indexed_count = 0
            filtered_out = 0
            
            # Process ALL messages (reduced filtering for better coverage)
            for i, message in enumerate(all_messages):
                try:
                    # Skip bot messages and system messages
                    if message.get('bot_id') or message.get('subtype'):
                        filtered_out += 1
                        continue
                    
                    text = message.get('text', '')
                    if len(text) < 3:  # Reduced minimum length from 10 to 3
                        filtered_out += 1
                        continue
                    
                    # Index ALL messages without entity filtering for better coverage
                    user_id = message.get('user')
                    user_name = f"User-{user_id}" if user_id else 'Unknown User'
                    
                    # Prepare metadata
                    metadata = {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "user_id": user_id,
                        "user_name": user_name,
                        "ts": message.get('ts'),
                        "thread_ts": message.get('thread_ts'),
                        "indexed_from": "comprehensive_indexing"
                    }
                    
                    # Add to vector database (this will do entity extraction internally)
                    success = self.add_slack_message(
                        message_id=message.get('ts'),
                        content=text,
                        metadata=metadata
                    )
                    
                    if success:
                        indexed_count += 1
                    
                    # Minimal processing delay (no additional API calls)
                    if (i + 1) % 10 == 0:  # Every 10 messages
                        logger.debug(f"Processed {i + 1} messages, pausing 1 second...")
                        time.sleep(1)
                        
                except Exception as e:
                    logger.debug(f"Error processing message in #{channel_name}: {e}")
                    continue
            
            logger.info(f"Indexed {indexed_count} messages from #{channel_name} (filtered out {filtered_out} messages)")
            return indexed_count
            
        except Exception as e:
            logger.error(f"Error indexing all channel messages: {e}")
            return 0
    
    def index_channel_with_smart_context(self, slack_client, channel_id: str, channel_name: str, 
                                        category: str = 'medium', limit: int = 100, days_back: int = 365):
        """Enhanced channel indexing with thread-aware intelligence and proper Slack API rate limiting"""
        try:
            logger.info(f"🧠 Starting smart context indexing for #{channel_name} ({category})")
            
            # Calculate oldest timestamp
            oldest = datetime.now() - timedelta(days=days_back)
            oldest_ts = oldest.timestamp()
            
            # UPDATED: Respect Slack's documented rate limits for non-marketplace apps
            max_retries = 5
            base_wait = 61  # 61 seconds between requests (1 per minute + buffer)
            
            logger.info(f"⏳ Waiting {base_wait} seconds before API call...")
            time.sleep(base_wait)
            
            all_messages = []
            cursor = None
            max_pages = 5 if category == 'ultra_priority' else 3
            
            # Get messages with pagination
            for page in range(max_pages):
                for attempt in range(max_retries + 1):
                    try:
                        params = {
                            'channel': channel_id,
                            'limit': 15,  # Slack's limit for non-marketplace apps
                            'oldest': str(oldest_ts)
                        }
                        if cursor:
                            params['cursor'] = cursor
                        
                        history_response = slack_client.conversations_history(**params)
                        
                        if history_response.get('ok'):
                            break
                        elif history_response.get('error') == 'ratelimited':
                            if attempt < max_retries:
                                # Exponential backoff on top of base rate limiting
                                wait_time = base_wait * (2 ** attempt)
                                logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"Rate limit exceeded after {max_retries + 1} attempts")
                                return 0
                        elif history_response.get('error') == 'not_in_channel':
                            logger.warning(f"❌ Not in #{channel_name} - may be private/archived")
                            return 0
                        else:
                            logger.error(f"API error for #{channel_name}: {history_response.get('error')}")
                            return 0
                    except Exception as e:
                        if attempt < max_retries:
                            wait_time = base_wait * (2 ** attempt)
                            logger.warning(f"Exception, retrying in {wait_time}s: {e}")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"Failed after {max_retries + 1} attempts: {e}")
                            return 0
                
                if not history_response.get('ok'):
                    break
                
                page_messages = history_response.get('messages', [])
                all_messages.extend(page_messages)
                
                # Check pagination
                cursor = history_response.get('response_metadata', {}).get('next_cursor')
                if not cursor or not history_response.get('has_more', False):
                    break
                
                # Wait before next page to respect rate limits
                logger.info(f"⏳ Waiting {base_wait} seconds before next page...")
                time.sleep(base_wait)
            
            logger.info(f"📝 Retrieved {len(all_messages)} messages from #{channel_name}")
            
            # NEW: Index thread replies for all thread_ts found in main messages
            self._index_thread_replies(slack_client, channel_id, channel_name, all_messages, days_back)
            
            # Smart processing with thread-aware intelligence
            indexed_count = 0
            thread_map = {}  # Track threads for context propagation
            company_channel_entities = set()  # For company-dedicated channels
            
            # Step 1: Pre-process to identify company-dedicated channels
            is_company_channel = any(pattern in channel_name.lower() for pattern in [
                'fern-', '-client', '-customer', '-partner', 'zillow', 'microsoft', 'pinecone'
            ])
            
            if is_company_channel:
                # Extract company name from channel
                for company in self.company_cache:
                    if company.lower() in channel_name.lower():
                        company_channel_entities.add(company)
                        logger.info(f"🏢 Company channel detected: #{channel_name} → {company}")
                        break
            
            # Step 2: First pass - identify threads with entities
            for message in all_messages:
                thread_ts = message.get('thread_ts') or message.get('ts')
                if thread_ts not in thread_map:
                    thread_map[thread_ts] = {'messages': [], 'entities': set()}
                
                text = message.get('text', '')
                if text:
                    # Extract entities from this message with basic channel context
                    basic_metadata = {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "user_id": message.get('user'),
                        "ts": message.get('ts'),
                        "thread_ts": message.get('thread_ts')
                    }
                    entities = self.extract_entities_from_text(text, basic_metadata)
                    message_entities = set()
                    
                    for entity_type, entity_list in entities.items():
                        for entity in entity_list:
                            message_entities.add(entity.lower())
                            thread_map[thread_ts]['entities'].add(entity.lower())
                    
                    # Add company channel entities to all messages
                    if company_channel_entities:
                        message_entities.update(company_channel_entities)
                        thread_map[thread_ts]['entities'].update(company_channel_entities)
                
                thread_map[thread_ts]['messages'].append({
                    'message': message,
                    'message_entities': message_entities
                })
            
            # Step 3: Process messages with thread-aware context
            for thread_ts, thread_data in thread_map.items():
                thread_entities = thread_data['entities']
                
                for msg_data in thread_data['messages']:
                    message = msg_data['message']
                    message_entities = msg_data['message_entities']
                    
                    try:
                        # Skip system messages
                        if message.get('bot_id') or message.get('subtype'):
                            continue
                        
                        text = message.get('text', '')
                        if len(text) < 3:  # Reduced from 5 to 3 for better coverage
                            continue
                        
                        # Enhanced metadata with thread-aware intelligence
                        user_id = message.get('user')
                        user_name = f"User-{user_id}" if user_id else 'Unknown'
                        
                        # Create comprehensive metadata
                        metadata = {
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "channel_category": category,
                            "user_id": user_id,
                            "user_name": user_name,
                            "ts": message.get('ts'),
                            "thread_ts": message.get('thread_ts'),
                            "is_company_channel": is_company_channel,
                            "indexed_from": "smart_context_sync"
                        }
                        
                        # Add thread-aware entity context
                        all_thread_entities = {
                            'companies': [],
                            'contacts': [],
                            'opportunities': []
                        }
                        
                        # Propagate thread entities to all messages in thread
                        for entity in thread_entities:
                            if entity in [c.lower() for c in self.company_cache]:
                                # Find original case
                                for orig_company in self.company_cache:
                                    if orig_company.lower() == entity:
                                        all_thread_entities['companies'].append(orig_company)
                                        break
                            elif entity in [c.lower() for c in self.contact_cache]:
                                for orig_contact in self.contact_cache:
                                    if orig_contact.lower() == entity:
                                        all_thread_entities['contacts'].append(orig_contact)
                                        break
                            elif entity in [o.lower() for o in self.opportunity_cache]:
                                for orig_opp in self.opportunity_cache:
                                    if orig_opp.lower() == entity:
                                        all_thread_entities['opportunities'].append(orig_opp)
                                        break
                        
                        # Clean metadata for ChromaDB compatibility
                        clean_metadata = self._clean_metadata_for_chroma({
                            **metadata,
                            "entities_json": json.dumps(all_thread_entities),
                            "has_companies": len(all_thread_entities['companies']) > 0,
                            "has_contacts": len(all_thread_entities['contacts']) > 0,
                            "has_opportunities": len(all_thread_entities['opportunities']) > 0,
                            "thread_entity_count": len(thread_entities),
                            "is_thread_root": message.get('ts') == thread_ts
                        })
                        
                        # Add to vector database
                        success = self._add_to_slack_collection(
                            message_id=message.get('ts'),
                            content=text,
                            metadata=clean_metadata
                        )
                        
                        if success:
                            indexed_count += 1
                            
                            # Log high-value discoveries
                            if all_thread_entities['companies']:
                                logger.info(f"   💼 Found message with companies: {all_thread_entities['companies'][:3]}")
                            if is_company_channel:
                                logger.info(f"   🏢 Company channel message indexed with context")
                        
                    except Exception as e:
                        logger.debug(f"Error processing message: {e}")
                        continue
                
                # Small delay between threads
                time.sleep(0.5)
            
            logger.info(f"🎉 Smart indexing completed: {indexed_count} messages from #{channel_name}")
            logger.info(f"   📊 Processed {len(thread_map)} threads with enhanced context")
            if company_channel_entities:
                logger.info(f"   🏢 Company channel entities: {list(company_channel_entities)}")
            
            return indexed_count
            
        except Exception as e:
            logger.error(f"Error in smart context indexing: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    def _index_thread_replies(self, slack_client, channel_id: str, channel_name: str, 
                             main_messages: list, days_back: int):
        """Index all thread replies for messages that have threads with proper Slack API rate limiting"""
        try:
            logger.info(f"🧵 Indexing thread replies for #{channel_name}...")
            
            # Find all unique thread timestamps from main messages
            thread_timestamps = set()
            for message in main_messages:
                thread_ts = message.get('thread_ts')
                if thread_ts:
                    thread_timestamps.add(thread_ts)
                # Also check if this message itself is a thread parent
                ts = message.get('ts')
                if ts and message.get('reply_count', 0) > 0:
                    thread_timestamps.add(ts)
            
            if not thread_timestamps:
                logger.info(f"   No threads found in #{channel_name}")
                return 0
            
            logger.info(f"   🔍 Found {len(thread_timestamps)} threads to index")
            thread_messages_indexed = 0
            
            # Calculate oldest timestamp for filtering
            oldest = datetime.now() - timedelta(days=days_back)
            oldest_ts = oldest.timestamp()
            
            # UPDATED: Respect Slack's documented rate limits for non-marketplace apps
            base_wait = 61  # 61 seconds between requests (1 per minute + buffer)
            
            # Index each thread's replies
            for i, thread_ts in enumerate(thread_timestamps):
                try:
                    if i > 0 and i % 5 == 0:  # Every 5 threads, log progress
                        logger.info(f"   📊 Processed {i}/{len(thread_timestamps)} threads...")
                    
                    # Rate limiting before each thread API call (respect Slack limits)
                    logger.info(f"   ⏳ Waiting {base_wait} seconds before thread API call...")
                    time.sleep(base_wait)
                    
                    # Get thread replies with proper rate limiting
                    max_retries = 3
                    for attempt in range(max_retries + 1):
                        try:
                            replies_response = slack_client.conversations_replies(
                                channel=channel_id,
                                ts=thread_ts,
                                oldest=str(oldest_ts),
                                limit=15  # Slack's limit for non-marketplace apps
                            )
                            
                            if replies_response.get('ok'):
                                break  # Success
                            elif replies_response.get('error') == 'ratelimited':
                                if attempt < max_retries:
                                    # Exponential backoff on top of base rate limiting
                                    wait_time = base_wait * (2 ** attempt)
                                    logger.warning(f"   Rate limited on thread {thread_ts}, waiting {wait_time}s")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    logger.error(f"   Failed to get thread {thread_ts} after retries")
                                    break
                            else:
                                logger.warning(f"   Error getting thread {thread_ts}: {replies_response.get('error')}")
                                break
                                
                        except Exception as e:
                            if attempt < max_retries:
                                wait_time = base_wait * (2 ** attempt)
                                logger.warning(f"   Exception getting thread {thread_ts}, retrying in {wait_time}s: {e}")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"   Failed to get thread {thread_ts} after retries: {e}")
                                break
                    
                    if not replies_response.get('ok'):
                        continue  # Skip this thread if we couldn't get it
                    
                    thread_messages = replies_response.get('messages', [])
                    
                    # Skip the first message (it's the parent, already indexed)
                    thread_replies = thread_messages[1:] if len(thread_messages) > 1 else []
                    
                    if not thread_replies:
                        continue  # No replies in this thread
                    
                    logger.debug(f"   🧵 Thread {thread_ts}: Found {len(thread_replies)} replies")
                    
                    # Index each reply
                    for reply in thread_replies:
                        try:
                            # Skip bot messages and system messages
                            if reply.get('bot_id') or reply.get('subtype'):
                                continue
                            
                            text = reply.get('text', '')
                            if len(text) < 3:  # Skip very short messages
                                continue
                            
                            user_id = reply.get('user')
                            user_name = f"User-{user_id}" if user_id else 'Unknown User'
                            
                            # Prepare metadata for thread reply
                            metadata = {
                                "channel_id": channel_id,
                                "channel_name": channel_name,
                                "user_id": user_id,
                                "user_name": user_name,
                                "ts": reply.get('ts'),
                                "thread_ts": thread_ts,  # THIS IS KEY - links to thread
                                "is_thread_reply": True,  # Mark as thread reply
                                "indexed_from": "thread_indexing"
                            }
                            
                            # Use enhanced entity extraction with metadata
                            entities = self.extract_entities_from_text(text, metadata)
                            
                            # Index the thread reply
                            success = self.add_slack_message(
                                message_id=reply.get('ts'),
                                content=text,
                                metadata=metadata
                            )
                            
                            if success:
                                thread_messages_indexed += 1
                                
                                # Log high-value thread discoveries
                                if entities and any(entities.values()):
                                    entity_summary = []
                                    for entity_type, entity_list in entities.items():
                                        if entity_list:
                                            entity_summary.extend(entity_list[:2])  # First 2 entities
                                    if entity_summary:
                                        logger.debug(f"     💼 Thread reply with entities: {entity_summary[:3]}")
                            
                        except Exception as e:
                            logger.debug(f"   Error indexing thread reply: {e}")
                            continue
                    
                except Exception as e:
                    logger.debug(f"   Error processing thread {thread_ts}: {e}")
                    continue
            
            logger.info(f"🧵 Thread indexing complete: {thread_messages_indexed} thread replies indexed from #{channel_name}")
            return thread_messages_indexed
            
        except Exception as e:
            logger.error(f"Error indexing thread replies for #{channel_name}: {e}")
            return 0
    
    def _add_to_slack_collection(self, message_id: str, content: str, metadata: Dict[str, Any]):
        """Helper method to add message to Slack collection with proper error handling"""
        try:
            # Generate embedding
            embedding = self.generate_embedding(content)
            if not embedding:
                return False
            
            # Add to collection
            self.slack_collection.add(
                documents=[content],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[f"slack_{message_id}"]
            )
            return True
            
        except Exception as e:
            logger.debug(f"Error adding to Slack collection: {e}")
            return False
    
    def _clean_metadata_for_chroma(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to clean metadata for ChromaDB compatibility"""
        cleaned_metadata = {}
        for key, value in metadata.items():
            if value is None:
                # Convert None to empty string for ChromaDB compatibility
                cleaned_metadata[key] = ""
            elif isinstance(value, (list, dict)):
                cleaned_metadata[key] = json.dumps(value)
            elif isinstance(value, bool):
                cleaned_metadata[key] = value  # ChromaDB supports booleans
            elif isinstance(value, (int, float)):
                cleaned_metadata[key] = value  # ChromaDB supports numbers
            else:
                # Convert everything else to string
                cleaned_metadata[key] = str(value) if value is not None else ""
        return cleaned_metadata 