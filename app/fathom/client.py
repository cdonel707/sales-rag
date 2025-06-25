import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import re

try:
    from fathom import FathomApiClient
except ImportError:
    # Fallback if fathom-python isn't available yet
    import httpx
    
    class FathomApiClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.base_url = "https://api.fathom.ai/external/v1"
            self.headers = {
                "X-Api-Key": api_key,
                "Content-Type": "application/json"
            }
        
        async def list_meetings(self, **kwargs):
            """Fallback implementation using httpx"""
            async with httpx.AsyncClient() as client:
                params = {}
                if 'cursor' in kwargs:
                    params['cursor'] = kwargs['cursor']
                if 'limit' in kwargs:
                    params['limit'] = min(kwargs['limit'], 10)  # Max 10 per request
                if 'include_transcript' in kwargs:
                    params['include_transcript'] = kwargs['include_transcript']
                if 'created_after' in kwargs:
                    params['created_after'] = kwargs['created_after']
                if 'meeting_type' in kwargs:
                    params['meeting_type'] = kwargs['meeting_type']
                # Add email filtering for attendees with proper array parameter format
                if 'calendar_invitees[]' in kwargs:
                    params['calendar_invitees[]'] = kwargs['calendar_invitees[]']
                
                response = await client.get(
                    f"{self.base_url}/meetings",
                    headers=self.headers,
                    params=params
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    response.raise_for_status()

logger = logging.getLogger(__name__)

class FathomClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Fathom API client"""
        if not self.api_key:
            logger.warning("❌ Fathom API key not provided")
            return
        
        try:
            self.client = FathomApiClient(api_key=self.api_key)
            logger.info(f"✅ Fathom client initialized successfully with key: {self.api_key[:10]}...")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Fathom client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if Fathom client is available"""
        return self.client is not None
    
    async def search_meetings_by_salesforce_contacts(self, salesforce_client, company_name: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Enhanced workflow: Get emails from Salesforce, then search Fathom by each email individually
        Returns ALL meetings with company contacts, properly deduplicated
        """
        if not self.is_available():
            logger.warning("Fathom client not available")
            return []
        
        try:
            # Step 1: Get contact emails from Salesforce
            contact_emails = await self._get_salesforce_contact_emails(salesforce_client, company_name)
            
            if not contact_emails:
                logger.info(f"No Salesforce contacts found for company: {company_name}")
                return []
            
            logger.info(f"Found {len(contact_emails)} Salesforce contacts for {company_name}: {contact_emails[:5]}...")
            
            # Step 2: Search Fathom for each email individually
            all_meetings = []
            for email in contact_emails:  # Search ALL emails, not just first 10
                try:
                    # Get more meetings per email to ensure comprehensive coverage
                    email_meetings = await self.search_meetings_by_attendee_email(email, limit=15)
                    if email_meetings:
                        logger.info(f"Found {len(email_meetings)} meetings for {email}")
                        for meeting in email_meetings:
                            meeting['_matched_email'] = email  # Track which email matched
                            meeting['_company'] = company_name  # Track company
                        all_meetings.extend(email_meetings)
                    
                    # Small delay to be respectful to API
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Error searching meetings for email {email}: {e}")
                    continue
            
            # Step 3: Enhanced deduplication - same meeting can appear for multiple company contacts
            unique_meetings = self._deduplicate_meetings(all_meetings)
            
            # Step 4: Sort by recency and apply final limit
            unique_meetings.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            final_meetings = unique_meetings[:limit]
            
            logger.info(f"Found {len(unique_meetings)} unique meetings from {company_name} contacts (returning {len(final_meetings)})")
            
            # Log details for debugging
            if final_meetings:
                meeting_titles = [m.get('title', 'Untitled')[:30] for m in final_meetings[:3]]
                logger.info(f"Top {company_name} meetings: {meeting_titles}")
            
            return final_meetings
            
        except Exception as e:
            logger.error(f"Error in Salesforce-based meeting search for {company_name}: {e}")
            return []
    
    async def search_meetings_by_attendee_email(self, email: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for meetings by specific attendee email"""
        if not self.is_available():
            logger.warning("Fathom client not available")
            return []
        
        try:
            meetings = []
            cursor = None
            total_fetched = 0
            
            while total_fetched < limit:
                batch_size = min(10, limit - total_fetched)  # Fathom max is 10
                
                params = {
                    'include_transcript': True,  # Always include transcripts
                    'limit': batch_size,
                    'calendar_invitees[]': email  # FIXED: Use array parameter format!
                }
                if cursor:
                    params['cursor'] = cursor
                
                response = await self.client.list_meetings(**params)
                
                if isinstance(response, dict):
                    batch_meetings = response.get('items', [])
                    # Only include meetings that actually have transcripts
                    transcript_meetings = [
                        m for m in batch_meetings 
                        if m.get('transcript') and len(m.get('transcript', [])) > 0
                    ]
                    meetings.extend(transcript_meetings)
                    total_fetched += len(batch_meetings)
                    
                    cursor = response.get('next_cursor')
                    if not cursor or not batch_meetings:
                        break
                else:
                    # Handle async generator
                    async for meeting in response:
                        if meeting.get('transcript') and len(meeting.get('transcript', [])) > 0:
                            meetings.append(meeting)
                        total_fetched += 1
                        if total_fetched >= limit:
                            break
                    break
            
            return meetings[:limit]
            
        except Exception as e:
            logger.error(f"Error searching meetings for email {email}: {e}")
            return []
    
    async def search_meetings_by_company(self, company_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search for meetings related to a specific company (legacy method - still supported)"""
        if not self.is_available():
            logger.warning("Fathom client not available")
            return []
        
        try:
            # Get recent meetings and filter by company
            recent_meetings = await self._get_recent_meetings_with_transcripts(limit * 2)
            company_meetings = self._filter_meetings_by_company_mention(recent_meetings, company_name)
            
            # Also try email domain search
            company_lower = company_name.lower()
            if not any(ext in company_lower for ext in ['.com', '.org', '.net', '.io']):
                # Try common domain patterns
                domain_variations = [f"{company_lower}.com", f"{company_lower.replace(' ', '')}.com"]
                for domain in domain_variations:
                    domain_meetings = await self._search_by_email_domain(domain, limit // 2)
                    company_meetings.extend(domain_meetings)
            
            # Deduplicate and sort by recency
            unique_meetings = self._deduplicate_meetings(company_meetings)
            unique_meetings.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            logger.info(f"Found {len(unique_meetings)} meetings for company '{company_name}'")
            return unique_meetings[:limit]
            
        except Exception as e:
            logger.error(f"Error searching meetings for company {company_name}: {e}")
            return []
    
    async def search_meetings_by_query(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search for meetings based on a general query"""
        if not self.is_available():
            logger.warning("Fathom client not available")
            return []
        
        try:
            recent_meetings = await self._get_recent_meetings_with_transcripts(limit * 3)
            
            relevant_meetings = []
            query_lower = query.lower()
            
            for meeting in recent_meetings:
                relevance_score = self._calculate_meeting_relevance(meeting, query_lower)
                if relevance_score > 0:
                    meeting['_relevance_score'] = relevance_score
                    relevant_meetings.append(meeting)
            
            relevant_meetings.sort(key=lambda x: x.get('_relevance_score', 0), reverse=True)
            
            logger.info(f"Found {len(relevant_meetings)} relevant meetings for query '{query}'")
            return relevant_meetings[:limit]
            
        except Exception as e:
            logger.error(f"Error searching meetings for query {query}: {e}")
            return []
    
    async def _get_recent_meetings_with_transcripts(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent meetings with transcripts included - ALWAYS includes transcripts"""
        try:
            meetings = []
            cursor = None
            total_fetched = 0
            
            while total_fetched < limit:
                batch_size = min(10, limit - total_fetched)  # Fathom max is 10
                
                params = {
                    'include_transcript': True,  # ALWAYS include transcripts
                    'limit': batch_size
                }
                if cursor:
                    params['cursor'] = cursor
                
                response = await self.client.list_meetings(**params)
                
                if isinstance(response, dict):
                    batch_meetings = response.get('items', [])
                    # Only include meetings that actually have transcripts
                    transcript_meetings = [
                        m for m in batch_meetings 
                        if m.get('transcript') and len(m.get('transcript', [])) > 0
                    ]
                    meetings.extend(transcript_meetings)
                    total_fetched += len(batch_meetings)
                    
                    cursor = response.get('next_cursor')
                    if not cursor or not batch_meetings:
                        break
                else:
                    # Handle async generator
                    async for meeting in response:
                        if meeting.get('transcript') and len(meeting.get('transcript', [])) > 0:
                            meetings.append(meeting)
                        total_fetched += 1
                        if total_fetched >= limit:
                            break
                    break
            
            return meetings[:limit]
            
        except Exception as e:
            logger.error(f"Error getting meetings with transcripts: {e}")
            return []
    
    async def _get_salesforce_contact_emails(self, salesforce_client, company_name: str = None) -> List[str]:
        """Get contact emails from Salesforce, optionally filtered by company"""
        try:
            contact_emails = []
            
            if company_name:
                # Search for contacts at specific company
                # First, try to find the account
                accounts = salesforce_client.find_records_by_name('Account', company_name)
                
                if accounts:
                    # Get contacts for this account
                    for account in accounts[:3]:  # Limit to first 3 accounts
                        account_id = account.get('Id')
                        if account_id:
                            contacts = salesforce_client._sf.query(f"""
                                SELECT Email FROM Contact 
                                WHERE AccountId = '{account_id}' 
                                AND Email != null 
                                AND IsDeleted = false
                                LIMIT 20
                            """)
                            for contact in contacts.get('records', []):
                                email = contact.get('Email')
                                if email and email not in contact_emails:
                                    contact_emails.append(email)
                else:
                    # Fallback: search contacts by company name in account name
                    contacts = salesforce_client._sf.query(f"""
                        SELECT Email FROM Contact 
                        WHERE Account.Name LIKE '%{company_name}%' 
                        AND Email != null 
                        AND IsDeleted = false
                        LIMIT 20
                    """)
                    for contact in contacts.get('records', []):
                        email = contact.get('Email')
                        if email and email not in contact_emails:
                            contact_emails.append(email)
            else:
                # Get all recent contacts
                contacts = salesforce_client.get_contacts(limit=50)
                for contact in contacts:
                    email = contact.get('Email')
                    if email and email not in contact_emails:
                        contact_emails.append(email)
            
            logger.info(f"Found {len(contact_emails)} Salesforce contact emails")
            return contact_emails
            
        except Exception as e:
            logger.error(f"Error getting Salesforce contact emails: {e}")
            return []
    
    def _deduplicate_meetings(self, meetings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate meetings based on URL or ID"""
        seen_identifiers = set()
        unique_meetings = []
        
        for meeting in meetings:
            # Use multiple identifiers to deduplicate
            identifiers = []
            if meeting.get('url'):
                identifiers.append(meeting['url'])
            if meeting.get('share_url'):
                identifiers.append(meeting['share_url'])
            if meeting.get('id'):
                identifiers.append(str(meeting['id']))
            
            # Check if we've seen this meeting before
            is_duplicate = False
            for identifier in identifiers:
                if identifier in seen_identifiers:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                # Add all identifiers to seen set
                for identifier in identifiers:
                    seen_identifiers.add(identifier)
                unique_meetings.append(meeting)
        
        return unique_meetings
    
    def _filter_meetings_by_company_mention(self, meetings: List[Dict[str, Any]], company_name: str) -> List[Dict[str, Any]]:
        """Filter meetings that mention the company name"""
        company_meetings = []
        company_variations = self._generate_company_variations(company_name)
        
        for meeting in meetings:
            is_company_meeting = False
            
            # Check meeting title
            title = meeting.get('title', '').lower()
            meeting_title = meeting.get('meeting_title', '').lower()
            if any(var in title for var in company_variations) or any(var in meeting_title for var in company_variations):
                is_company_meeting = True
            
            # Check transcript
            if not is_company_meeting:
                transcript = meeting.get('transcript', [])
                transcript_text = ' '.join([msg.get('text', '') for msg in transcript]).lower()
                if any(var in transcript_text for var in company_variations):
                    is_company_meeting = True
            
            # Check summary
            if not is_company_meeting:
                summary = meeting.get('default_summary', {}).get('markdown_formatted', '').lower()
                if any(var in summary for var in company_variations):
                    is_company_meeting = True
            
            if is_company_meeting:
                company_meetings.append(meeting)
        
        return company_meetings
    
    def _generate_company_variations(self, company_name: str) -> List[str]:
        """Generate variations of company name for better matching"""
        variations = [company_name.lower()]
        
        # Add variations without common suffixes
        for suffix in [' inc', ' inc.', ' corp', ' corp.', ' llc', ' ltd', ' ltd.']:
            if company_name.lower().endswith(suffix):
                base_name = company_name.lower()[:-len(suffix)].strip()
                variations.append(base_name)
        
        # Add variations without spaces/punctuation
        clean_name = re.sub(r'[^\w]', '', company_name.lower())
        variations.append(clean_name)
        
        return list(set(variations))
    
    def _calculate_meeting_relevance(self, meeting: Dict[str, Any], query: str) -> float:
        """Calculate relevance score for a meeting based on query"""
        score = 0.0
        query_words = query.lower().split()
        
        # Check title/meeting title (high weight)
        title = (meeting.get('title', '') + ' ' + meeting.get('meeting_title', '')).lower()
        title_matches = sum(1 for word in query_words if word in title)
        score += title_matches * 3.0
        
        # Check summary (medium weight)
        summary = meeting.get('default_summary', {}).get('markdown_formatted', '').lower()
        summary_matches = sum(1 for word in query_words if word in summary)
        score += summary_matches * 2.0
        
        # Check transcript (lower weight but important)
        transcript = meeting.get('transcript', [])
        transcript_text = ' '.join([msg.get('text', '') for msg in transcript]).lower()
        transcript_matches = sum(1 for word in query_words if word in transcript_text)
        score += transcript_matches * 1.0
        
        # Boost score for external meetings (likely client calls)
        if meeting.get('meeting_type') == 'external':
            score *= 1.2
        
        return score
    
    def format_meeting_for_context(self, meeting: Dict[str, Any]) -> str:
        """Format meeting data for use as RAG context"""
        try:
            # Basic meeting info
            title = meeting.get('title', meeting.get('meeting_title', 'Untitled Meeting'))
            meeting_date = meeting.get('created_at', meeting.get('scheduled_start_time', ''))
            meeting_type = meeting.get('meeting_type', 'unknown')
            
            # Format date
            formatted_date = "Unknown Date"
            if meeting_date:
                try:
                    dt = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = meeting_date
            
            # Get participants
            participants = []
            for invitee in meeting.get('calendar_invitees', []):
                name = invitee.get('name', invitee.get('email', 'Unknown'))
                is_external = invitee.get('is_external', False)
                participant_type = " (External)" if is_external else " (Internal)"
                participants.append(name + participant_type)
            
            # Get summary
            summary = meeting.get('default_summary', {}).get('markdown_formatted', 'No summary available')
            
            # Get key transcript excerpts
            transcript = meeting.get('transcript', [])
            transcript_excerpts = []
            if transcript:
                # First few and last few messages for context
                for msg in transcript[:3]:
                    speaker = msg.get('speaker', {}).get('display_name', 'Unknown Speaker')
                    text = msg.get('text', '')
                    timestamp = msg.get('timestamp', '')
                    transcript_excerpts.append(f"[{timestamp}] {speaker}: {text}")
                
                if len(transcript) > 6:
                    transcript_excerpts.append("... [middle portion omitted] ...")
                    for msg in transcript[-3:]:
                        speaker = msg.get('speaker', {}).get('display_name', 'Unknown Speaker')
                        text = msg.get('text', '')
                        timestamp = msg.get('timestamp', '')
                        transcript_excerpts.append(f"[{timestamp}] {speaker}: {text}")
            
            # Get action items
            action_items = []
            for item in meeting.get('action_items', []):
                description = item.get('description', '')
                assignee = item.get('assignee', {}).get('name', 'Unassigned')
                completed = "✅" if item.get('completed', False) else "⏳"
                action_items.append(f"{completed} {description} (Assigned to: {assignee})")
            
            # Build formatted context
            context_parts = [
                f"📞 FATHOM MEETING: {title}",
                f"📅 Date: {formatted_date}",
                f"🔄 Type: {meeting_type.title()} Meeting",
                f"👥 Participants: {', '.join(participants) if participants else 'Not specified'}",
                "",
                "📋 MEETING SUMMARY:",
                summary,
                ""
            ]
            
            if transcript_excerpts:
                context_parts.extend([
                    "💬 KEY TRANSCRIPT EXCERPTS:",
                    "\n".join(transcript_excerpts),
                    ""
                ])
            
            if action_items:
                context_parts.extend([
                    "✅ ACTION ITEMS:",
                    "\n".join(action_items),
                    ""
                ])
            
            # Add meeting URL for reference
            meeting_url = meeting.get('share_url', meeting.get('url', ''))
            if meeting_url:
                context_parts.append(f"🔗 View Full Meeting: {meeting_url}")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error formatting meeting context: {e}")
            return f"Meeting: {meeting.get('title', 'Unknown')} (Error formatting details)"
    
    async def _search_by_email_domain(self, domain: str, limit: int) -> List[Dict[str, Any]]:
        """Search meetings by email domain of invitees (legacy method)"""
        try:
            # Get recent meetings and filter by email domain
            recent_meetings = await self._get_recent_meetings_with_transcripts(100)
            
            domain_meetings = []
            for meeting in recent_meetings:
                # Check calendar invitees
                invitees = meeting.get('calendar_invitees', [])
                for invitee in invitees:
                    email = invitee.get('email', '').lower()
                    if domain in email:
                        domain_meetings.append(meeting)
                        break
                
                # Also check recorded_by
                recorded_by = meeting.get('recorded_by', {})
                if recorded_by and domain in recorded_by.get('email', '').lower():
                    if meeting not in domain_meetings:
                        domain_meetings.append(meeting)
            
            return domain_meetings[:limit]
            
        except Exception as e:
            logger.error(f"Error searching by domain {domain}: {e}")
            return [] 