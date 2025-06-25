import logging
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
from datetime import datetime, timedelta
import threading
import time

from .rag.embeddings import EmbeddingService
from .rag.generation import GenerationService
from .salesforce.client import SalesforceClient
from .slack.handlers import SlackHandler
from .database.models import SalesforceDocument
from .config import config
import json

# Add Slack SDK import for user client
from slack_sdk import WebClient

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
        
        # Initialize dual Slack clients
        self._setup_slack_clients()
        
        # Initialize Slack handler (for bot interactions only)
        self.slack_handler = SlackHandler(
            embedding_service=self.embedding_service,
            generation_service=self.generation_service,
            salesforce_client=self.salesforce_client,
            db_session_maker=self.db_session_maker
        )
    
    def _setup_slack_clients(self):
        """Setup dual Slack clients: user for syncing, bot for interactions"""
        try:
            # User client for data syncing (your personal token)
            if config.SLACK_USER_TOKEN:
                self.user_slack_client = WebClient(token=config.SLACK_USER_TOKEN)
                logger.info("✅ User Slack client initialized for data syncing")
                
                # Test user client
                user_auth = self.user_slack_client.auth_test()
                if user_auth.get('ok'):
                    logger.info(f"🔑 User client authenticated as: {user_auth.get('user', 'Unknown')}")
                else:
                    logger.error("❌ User Slack client authentication failed")
                    self.user_slack_client = None
            else:
                logger.warning("⚠️ SLACK_USER_TOKEN not provided - falling back to bot client for syncing")
                self.user_slack_client = None
            
            # Bot client for interactions (handled by SlackHandler)
            logger.info("🤖 Bot Slack client will be handled by SlackHandler for interactions")
            
        except Exception as e:
            logger.error(f"Error setting up Slack clients: {e}")
            self.user_slack_client = None
    
    def _get_sync_client(self):
        """Get the appropriate client for data syncing"""
        if self.user_slack_client:
            logger.debug("Using user client for data syncing")
            return self.user_slack_client
        else:
            logger.debug("Falling back to bot client for data syncing")
            return self.slack_handler.client
    
    def _ensure_bot_joins_channel_for_interaction(self, channel_id: str, channel_name: str):
        """Ensure bot joins channel ONLY when users want to interact with it"""
        try:
            bot_client = self.slack_handler.client
            
            # Check if bot is already in channel
            members_response = bot_client.conversations_members(channel=channel_id)
            if members_response.get('ok'):
                bot_user_id = bot_client.auth_test().get('user_id')
                if bot_user_id in members_response.get('members', []):
                    logger.debug(f"Bot already in #{channel_name}")
                    return True
            
            # Try to join the channel for interaction
            join_response = bot_client.conversations_join(channel=channel_id)
            if join_response.get('ok'):
                logger.info(f"🤖 Bot joined #{channel_name} for user interaction")
                return True
            else:
                logger.warning(f"❌ Bot could not join #{channel_name}: {join_response.get('error')}")
                return False
                
        except Exception as e:
            logger.warning(f"Error ensuring bot in #{channel_name}: {e}")
            return False
    
    async def initialize(self):
        """Initialize the service and perform initial data sync"""
        logger.info("Initializing Sales RAG Service...")
        
        # Connect to Salesforce
        if not self.salesforce_client.connect():
            logger.error("Failed to connect to Salesforce")
            return False
        
        # Perform initial data sync
        await self.sync_salesforce_data()
        
        # Update entity cache for cross-channel search
        logger.info("Updating entity cache for cross-channel search...")
        self.embedding_service.update_entity_cache(self.salesforce_client)
        
        # Start background sync instead of blocking sync
        logger.info("Starting non-blocking background Slack sync...")
        await self.start_background_comprehensive_sync()
        
        logger.info("✅ Sales RAG Service initialized successfully")
        logger.info("🔄 Background Slack sync is running - app is fully responsive!")
        logger.info("💡 You can now use /sales commands while sync continues in background")
        return True
    
    async def start_automated_initial_sync(self):
        """Enhanced automated background sync with smart prioritization and intelligence"""
        def background_sync():
            """Enhanced background sync with smart channel prioritization"""
            logger.info("🤖 Starting enhanced automated initial Slack sync...")
            
            # Enhanced configuration for comprehensive processing of ALL channels
            channels_per_batch = 6  # Reasonable batch size for ALL channel processing
            delay_between_batches = 45  # Conservative rate limiting
            max_total_channels = 500  # Process ALL channels, no artificial limit
            
            processed_total = 0
            cursor = None
            prioritized_channels = []
            
            # Step 1: Get all channels and prioritize them
            logger.info("🎯 Phase 1: Channel discovery and prioritization using user account")
            try:
                # Get sync client (user client preferred, bot client fallback)
                sync_client = self._get_sync_client()
                
                # Get all channels first using user account (no joining needed!)
                all_channels_response = sync_client.conversations_list(
                    types="public_channel",
                    limit=1000,
                    exclude_archived=False  # Include for company channel detection
                )
                
                if not all_channels_response.get('ok'):
                    logger.error("Failed to get channels for prioritization")
                    return
                
                all_channels = all_channels_response.get('channels', [])
                logger.info(f"📊 Found {len(all_channels)} total channels")
                
                # Comprehensive prioritization - ALL channels with 2+ users (user requirement)
                ultra_priority = []
                high_priority = []
                medium_priority = []
                low_priority = []
                
                for channel in all_channels:
                    channel_name = channel.get('name', '').lower()
                    member_count = channel.get('num_members', 0)
                    is_archived = channel.get('is_archived', False)
                    
                    # Skip channels with less than 2 users (user requirement)
                    if member_count < 2:
                        continue
                    
                    # Skip very low value channels only if they have few members
                    if any(skip_word in channel_name for skip_word in [
                        'random', 'test', 'bot-', 'notifications', 'alerts', 'logs', 'spam', 
                        'temp', 'old', 'archive'
                    ]) and member_count < 5:
                        continue
                    
                    # ULTRA PRIORITY: User-specified prefixes (#sales, #fern, #meeting)
                    if any(channel_name.startswith(prefix) for prefix in [
                        'sales', 'fern', 'meeting'  # User's specific priority prefixes
                    ]):
                        ultra_priority.append(channel)
                        channel['sync_category'] = 'ultra_priority'
                        channel['priority_score'] = 100
                    
                    # HIGH PRIORITY: Company channels + critical business 
                    elif any(pattern in channel_name for pattern in [
                        'fern-', '-client', '-customer', '-partner'  # Company/client channels
                    ]) or any(biz_word in channel_name for biz_word in [
                        'deals', 'revenue', 'partnerships', 'customers', 'demo', 'onboarding',
                        'support', 'implementation', 'integration', 'contracts', 'legal', 'success', 'growth'
                    ]):
                        high_priority.append(channel)
                        channel['sync_category'] = 'high_priority'
                        channel['priority_score'] = 75
                    
                    # MEDIUM PRIORITY: Active channels with good activity
                    elif member_count >= 10 and not is_archived:
                        medium_priority.append(channel)
                        channel['sync_category'] = 'medium_priority'
                        channel['priority_score'] = 50
                    
                    # LOW PRIORITY: All other qualifying channels (2+ users, not archived)
                    elif not is_archived:
                        low_priority.append(channel)
                        channel['sync_category'] = 'low_priority'
                        channel['priority_score'] = 25
                
                # Sort each category by member count (more active = higher priority within category)
                ultra_priority.sort(key=lambda x: x.get('num_members', 0), reverse=True)
                high_priority.sort(key=lambda x: x.get('num_members', 0), reverse=True)
                medium_priority.sort(key=lambda x: x.get('num_members', 0), reverse=True)
                low_priority.sort(key=lambda x: x.get('num_members', 0), reverse=True)
                
                # Combine in priority order
                prioritized_channels = ultra_priority + high_priority + medium_priority + low_priority
                
                logger.info(f"📊 Comprehensive channel prioritization complete:")
                logger.info(f"   🎯 Ultra priority (#sales/#fern/#meeting): {len(ultra_priority)}")
                logger.info(f"   📈 High priority (business): {len(high_priority)}")
                logger.info(f"   💼 Medium priority (active 10+): {len(medium_priority)}")
                logger.info(f"   📝 Low priority (other 2+): {len(low_priority)}")
                logger.info(f"   🔄 TOTAL CHANNELS TO SYNC: {len(prioritized_channels)} (ALL with 2+ users)")
                
                # Show top ultra priority channels
                if ultra_priority:
                    logger.info("🎯 Top ultra priority channels:")
                    for ch in ultra_priority[:5]:
                        logger.info(f"   #{ch['name']} ({ch.get('num_members', 0)} members)")
                
            except Exception as e:
                logger.error(f"Error in channel prioritization: {e}")
                return
            
            # Step 2: Process channels in priority order
            logger.info("🔄 Phase 2: Smart channel processing")
            
            total_channels_to_process = min(len(prioritized_channels), max_total_channels)
            logger.info(f"🔄 Processing ALL {total_channels_to_process} qualifying channels (2+ users, prioritized)")
            
            # Process in batches
            for batch_start in range(0, total_channels_to_process, channels_per_batch):
                batch_end = min(batch_start + channels_per_batch, total_channels_to_process)
                batch = prioritized_channels[batch_start:batch_end]
                
                batch_num = (batch_start // channels_per_batch) + 1
                logger.info(f"🔄 Processing batch {batch_num}: channels {batch_start + 1}-{batch_end}")
                
                # Show batch composition
                batch_categories = {}
                for ch in batch:
                    cat = ch.get('sync_category', 'unknown')
                    batch_categories[cat] = batch_categories.get(cat, 0) + 1
                
                logger.info(f"   Batch composition: {batch_categories}")
                
                # Process each channel in batch
                batch_success = 0
                batch_indexed = 0
                
                for i, channel in enumerate(batch):
                    channel_id = channel['id']
                    channel_name = channel['name']
                    is_archived = channel.get('is_archived', False)
                    is_member = channel.get('is_member', False)
                    category = channel.get('sync_category', 'low')
                    
                    logger.info(f"   Processing {i+1}/{len(batch)}: #{channel_name} ({category})")
                    
                    # Skip archived unless ultra priority
                    if is_archived and category != 'ultra_priority':
                        logger.info("     ⏭️ Skipping archived non-ultra channel")
                        continue
                    
                    # NO CHANNEL JOINING NEEDED - using user account for sync!
                    logger.info(f"     📊 Syncing with user account (no joining required)")
                    
                    # Smart indexing with category-based settings using sync client
                    try:
                        indexed_count = self.embedding_service.index_channel_with_smart_context(
                            slack_client=sync_client,
                            channel_id=channel_id,
                            channel_name=channel_name,
                            category=category,
                            limit=200 if category == 'ultra_priority' else 100 if category == 'high_priority' else 50,
                            days_back=1095 if category == 'ultra_priority' else 730 if category == 'high_priority' else 365  # 3 years, 2 years, 1 year
                        )
                        
                        if indexed_count > 0:
                            batch_success += 1
                            batch_indexed += indexed_count
                            logger.info(f"     ✅ Indexed {indexed_count} messages")
                        else:
                            logger.info(f"     ⚠️ No messages indexed")
                        
                        processed_total += 1
                        
                        # Adaptive delay based on category
                        if category == 'ultra_priority':
                            time.sleep(20)  # Longer delay for important channels
                        elif category == 'high_priority':
                            time.sleep(15)
                        else:
                            time.sleep(10)
                        
                    except Exception as e:
                        logger.error(f"     ❌ Error indexing #{channel_name}: {e}")
                        continue
                
                logger.info(f"📊 Batch {batch_num} completed: {batch_success}/{len(batch)} successful, {batch_indexed} messages indexed")
                
                # Conservative delay between batches
                if batch_end < total_channels_to_process:
                    logger.info(f"⏳ Waiting {delay_between_batches} seconds before next batch...")
                    time.sleep(delay_between_batches)
            
            logger.info(f"🎉 Enhanced automated sync completed!")
            logger.info(f"📊 Final results: {processed_total} channels processed")
            logger.info("💡 Ready for real-time mode - use /enable-realtime endpoint")
        
        # Start enhanced background thread
        sync_thread = threading.Thread(target=background_sync, daemon=True)
        sync_thread.start()
        logger.info("🚀 Enhanced automated sync started with smart prioritization")
    
    async def discover_and_index_slack_channels(self):
        """Enhanced manual sync with smart prioritization and thread-aware intelligence"""
        try:
            logger.info("🧠 Enhanced manual sync triggered - applying all learnings")
            logger.info("💡 Features: Smart prioritization + Thread-aware intelligence + User account sync")
            
            # Get sync client (user client preferred, bot client fallback)
            sync_client = self._get_sync_client()
            
            # Enhanced channel discovery
            logger.info("⏳ Waiting 5 seconds before API call...")
            await asyncio.sleep(5)
            
            channels_response = sync_client.conversations_list(
                types="public_channel",
                limit=1000,  # Get ALL channels for comprehensive sync
                exclude_archived=False  # Include archived for ultra priority detection
            )
            
            if not channels_response.get('ok'):
                logger.error(f"Failed to get channels: {channels_response.get('error')}")
                return
            
            all_channels = channels_response.get('channels', [])
            logger.info(f"📊 Found {len(all_channels)} total channels")
            
            # Smart channel prioritization - ALL channels with 2+ users, prioritized by importance
            logger.info("🎯 Applying comprehensive channel prioritization...")
            
            ultra_priority = []   # User-specified priority channels
            high_priority = []    # Company/business channels  
            medium_priority = []  # General active channels
            low_priority = []     # All other qualifying channels
            
            for channel in all_channels:
                channel_name = channel.get('name', '').lower()
                member_count = channel.get('num_members', 0)
                is_archived = channel.get('is_archived', False)
                
                # Skip channels with less than 2 users (user requirement)
                if member_count < 2:
                    continue
                
                # Skip very low value channels only if they have few members
                if any(skip_word in channel_name for skip_word in [
                    'random', 'test', 'bot-', 'notifications', 'alerts', 'logs', 'spam'
                ]) and member_count < 5:
                    continue
                
                # ULTRA PRIORITY: User-specified prefixes (#sales, #fern, #meeting)
                if any(channel_name.startswith(prefix) for prefix in [
                    'sales', 'fern', 'meeting'  # User's specific priority prefixes
                ]):
                    ultra_priority.append(channel)
                    channel['sync_category'] = 'ultra_priority'
                
                # HIGH PRIORITY: Company channels + critical business 
                elif any(pattern in channel_name for pattern in [
                    'fern-', '-client', '-customer', '-partner'  # Company/client channels
                ]) or any(biz_word in channel_name for biz_word in [
                    'deals', 'revenue', 'partnerships', 'customers', 'demo', 'onboarding',
                    'support', 'implementation', 'integration', 'contracts', 'legal', 'success', 'growth'
                ]):
                    high_priority.append(channel)
                    channel['sync_category'] = 'high_priority'
                
                # MEDIUM PRIORITY: Active channels with good activity
                elif member_count >= 10 and not is_archived:
                    medium_priority.append(channel)
                    channel['sync_category'] = 'medium_priority'
                
                # LOW PRIORITY: All other qualifying channels (2+ users, not archived)
                elif not is_archived:
                    low_priority.append(channel)
                    channel['sync_category'] = 'low_priority'
            
            # Process ALL qualifying channels, just in priority order
            channels_to_process = ultra_priority + high_priority + medium_priority + low_priority
            
            logger.info(f"📊 Channel prioritization complete:")
            logger.info(f"   🎯 Ultra priority (#sales/#fern/#meeting): {len(ultra_priority)}")
            logger.info(f"   📈 High priority (business): {len(high_priority)}")
            logger.info(f"   💼 Medium priority (active 10+): {len(medium_priority)}")
            logger.info(f"   📋 Low priority (other 2+): {len(low_priority)}")
            logger.info(f"   🔄 TOTAL CHANNELS TO SYNC: {len(channels_to_process)}")
            
            # Show discovered ultra priority channels
            if ultra_priority:
                logger.info("🎯 Ultra priority channels found:")
                for ch in ultra_priority[:10]:
                    logger.info(f"   #{ch['name']} ({ch.get('num_members', 0)} members)")
            if high_priority:
                logger.info("📈 High priority channels (first 10):")
                for ch in high_priority[:10]:
                    logger.info(f"   #{ch['name']} ({ch.get('num_members', 0)} members)")
            
            if not channels_to_process:
                logger.info("No prioritized channels found to process")
                return
            
            logger.info(f"📋 Processing ALL {len(channels_to_process)} qualifying channels (2+ users, prioritized)")
            
            total_indexed = 0
            successful_channels = 0
            
            for i, channel in enumerate(channels_to_process):
                channel_id = channel['id']
                channel_name = channel['name']
                is_archived = channel.get('is_archived', False)
                is_member = channel.get('is_member', False)
                category = channel.get('sync_category', 'medium')
                
                logger.info(f"Processing channel {i+1}/{len(channels_to_process)}: #{channel_name} ({category})")
                
                # Skip archived unless ultra priority
                if is_archived and category != 'ultra_priority':
                    logger.info("   ⏭️ Skipping archived non-ultra channel")
                    continue
                
                # NO CHANNEL JOINING NEEDED - using user account!
                logger.info(f"   📊 Syncing #{channel_name} with user account (no joining required)")
                
                # Enhanced message sync with thread-aware intelligence
                indexed_count = self.embedding_service.index_channel_with_smart_context(
                    slack_client=sync_client,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    category=category,
                    limit=100 if category == 'ultra_priority' else 50,
                    days_back=1095 if category == 'ultra_priority' else 365  # 3 years, 1 year for all others
                )
                
                if indexed_count > 0:
                    total_indexed += indexed_count
                    successful_channels += 1
                    logger.info(f"✅ Indexed {indexed_count} messages from #{channel_name}")
                else:
                    logger.info(f"⚠️ No messages indexed from #{channel_name}")
                
                # Adaptive delay based on category and success
                if category == 'ultra_priority':
                    await asyncio.sleep(15)  # Longer delay for important channels
                else:
                    await asyncio.sleep(10)
            
            logger.info(f"🎉 Enhanced manual sync completed!")
            logger.info(f"📊 Results: {successful_channels}/{len(channels_to_process)} channels successful, {total_indexed} total messages")
            logger.info("💡 For comprehensive sync, use automated initial sync endpoint")
            
        except Exception as e:
            logger.error(f"Error in enhanced manual sync: {e}")
            import traceback
            traceback.print_exc()
    
    async def _ensure_bot_in_channel(self, slack_client, channel_id: str, channel_name: str):
        """Ensure bot is in channel, join if needed and possible"""
        try:
            # Check if bot is already in channel
            members_response = slack_client.conversations_members(channel=channel_id)
            if members_response.get('ok'):
                bot_user_id = slack_client.auth_test().get('user_id')
                if bot_user_id in members_response.get('members', []):
                    return True  # Already in channel
            
            # Try to join the channel
            join_response = slack_client.conversations_join(channel=channel_id)
            if join_response.get('ok'):
                logger.info(f"Successfully joined channel #{channel_name}")
                return True
            else:
                logger.warning(f"Could not join channel #{channel_name}: {join_response.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.warning(f"Error checking/joining channel #{channel_name}: {e}")
            return False
    
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
                               conversation_history: Optional[list] = None,
                               company_filter: Optional[str] = None) -> dict:
        """Search sales data using RAG with enhanced cross-channel search"""
        try:
            # Enhanced search with company filtering
            context_documents = self.embedding_service.search_similar_content(
                query=query,
                n_results=10,
                source_filter=source_filter,
                channel_filter=channel_filter,
                thread_filter=thread_filter,
                company_filter=company_filter
            )
            
            # If asking about a specific company, also get company-specific results
            if company_filter or self._contains_company_mention(query):
                company_name = company_filter or self._extract_company_from_query(query)
                if company_name:
                    company_results = self.embedding_service.search_by_company(company_name, n_results=5)
                    # Merge results, prioritizing company-specific ones
                    context_documents = company_results + context_documents
                    context_documents = context_documents[:10]  # Keep top 10
            
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
    
    def _contains_company_mention(self, query: str) -> bool:
        """Check if query mentions any known companies"""
        query_lower = query.lower()
        return any(company in query_lower for company in self.embedding_service.company_cache if len(company) > 3)
    
    def _extract_company_from_query(self, query: str) -> Optional[str]:
        """Extract company name from query if mentioned"""
        query_lower = query.lower()
        for company in self.embedding_service.company_cache:
            if len(company) > 3 and company in query_lower:
                return company
        return None
    
    async def refresh_cross_channel_index(self):
        """Refresh cross-channel index with latest Slack data"""
        logger.info("Refreshing cross-channel index...")
        
        # Update entity cache first
        self.embedding_service.update_entity_cache(self.salesforce_client)
        
        # Re-discover and index channels
        await self.discover_and_index_slack_channels()
        
        logger.info("Cross-channel index refresh completed")
    
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
            "database": False,
            "cross_channel_index": False
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
            
            # Check cross-channel index
            try:
                health_status["cross_channel_index"] = len(self.embedding_service.company_cache) > 0
            except:
                health_status["cross_channel_index"] = False
            
        except Exception as e:
            logger.error(f"Error during health check: {e}")
        
        return {
            "status": "healthy" if all(health_status.values()) else "degraded",
            "services": health_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def start_background_comprehensive_sync(self):
        """Start a truly background comprehensive sync that doesn't block the web server"""
        def run_background_sync():
            """Background sync that runs in separate thread"""
            import time
            
            logger.info("🚀 Starting truly background comprehensive sync...")
            logger.info("💡 Web server remains fully responsive during sync")
            
            try:
                # Get sync client (user account)
                sync_client = self._get_sync_client()
                
                # Step 1: Discover ALL channels
                logger.info("📊 Discovering all channels...")
                time.sleep(2)  # Small delay before starting
                
                channels_response = sync_client.conversations_list(
                    types="public_channel",
                    limit=1000,
                    exclude_archived=False
                )
                
                if not channels_response.get('ok'):
                    logger.error(f"Failed to get channels: {channels_response.get('error')}")
                    return
                
                all_channels = channels_response.get('channels', [])
                logger.info(f"📊 Found {len(all_channels)} total channels")
                
                # Step 2: Filter and prioritize (same logic as before)
                qualifying_channels = []
                ultra_priority = []
                high_priority = []
                medium_priority = []
                low_priority = []
                
                for channel in all_channels:
                    channel_name = channel.get('name', '').lower()
                    member_count = channel.get('num_members', 0)
                    is_archived = channel.get('is_archived', False)
                    
                    # Skip channels with less than 2 users
                    if member_count < 2:
                        continue
                    
                    # Skip spam channels
                    if any(skip_word in channel_name for skip_word in [
                        'random', 'test', 'bot-', 'notifications', 'alerts', 'logs', 'spam'
                    ]) and member_count < 5:
                        continue
                    
                    # Prioritize
                    if any(channel_name.startswith(prefix) for prefix in ['sales', 'fern', 'meeting']):
                        ultra_priority.append(channel)
                        channel['sync_category'] = 'ultra_priority'
                    elif any(pattern in channel_name for pattern in [
                        'fern-', '-client', '-customer', '-partner'
                    ]) or any(biz_word in channel_name for biz_word in [
                        'deals', 'revenue', 'partnerships', 'customers', 'demo', 'onboarding',
                        'support', 'implementation', 'integration', 'contracts', 'legal', 'success', 'growth'
                    ]):
                        high_priority.append(channel)
                        channel['sync_category'] = 'high_priority'
                    elif member_count >= 10 and not is_archived:
                        medium_priority.append(channel)
                        channel['sync_category'] = 'medium_priority'
                    elif not is_archived:
                        low_priority.append(channel)
                        channel['sync_category'] = 'low_priority'
                
                # Combine all qualifying channels
                qualifying_channels = ultra_priority + high_priority + medium_priority + low_priority
                
                logger.info(f"🎯 Channel breakdown:")
                logger.info(f"   Ultra: {len(ultra_priority)}, High: {len(high_priority)}")
                logger.info(f"   Medium: {len(medium_priority)}, Low: {len(low_priority)}")
                logger.info(f"   📊 TOTAL TO SYNC: {len(qualifying_channels)} channels")
                
                # Step 3: Process channels with background-friendly approach
                successful_channels = 0
                total_messages = 0
                
                for i, channel in enumerate(qualifying_channels[:200]):  # Limit to prevent overwhelming
                    channel_id = channel['id']
                    channel_name = channel['name']
                    category = channel.get('sync_category', 'low_priority')
                    is_archived = channel.get('is_archived', False)
                    
                    # Skip archived unless ultra priority
                    if is_archived and category != 'ultra_priority':
                        continue
                    
                    logger.info(f"🔄 [{i+1}/{len(qualifying_channels)}] Syncing #{channel_name} ({category})")
                    
                    try:
                        # Use the smart context indexing
                        indexed_count = self.embedding_service.index_channel_with_smart_context(
                            slack_client=sync_client,
                            channel_id=channel_id,
                            channel_name=channel_name,
                            category=category,
                            limit=100 if category in ['ultra_priority', 'high_priority'] else 50,
                            days_back=180 if category in ['ultra_priority', 'high_priority'] else 60
                        )
                        
                        if indexed_count > 0:
                            successful_channels += 1
                            total_messages += indexed_count
                            logger.info(f"   ✅ Indexed {indexed_count} messages")
                        else:
                            logger.info(f"   ⚠️ No messages indexed")
                        
                        # Background-friendly delays (longer to avoid blocking)
                        if category == 'ultra_priority':
                            time.sleep(25)  # Longer delays for background processing
                        elif category == 'high_priority':
                            time.sleep(20)
                        else:
                            time.sleep(15)
                            
                    except Exception as e:
                        logger.error(f"   ❌ Error syncing #{channel_name}: {e}")
                        time.sleep(10)  # Wait before continuing on error
                        continue
                
                logger.info(f"🎉 Background sync completed!")
                logger.info(f"📊 Results: {successful_channels} channels, {total_messages} messages indexed")
                logger.info("💡 Bot is now ready with comprehensive Slack data!")
                
            except Exception as e:
                logger.error(f"Background sync error: {e}")
                import traceback
                traceback.print_exc()
        
        # Start in truly separate daemon thread
        sync_thread = threading.Thread(target=run_background_sync, daemon=True)
        sync_thread.start()
        
        logger.info("🚀 Background comprehensive sync started!")
        logger.info("💡 Web server remains fully responsive")
        return {"status": "started", "message": "Background sync running - app remains usable"} 