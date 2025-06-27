import logging
import json
import re
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from openai import OpenAI
from app.salesforce.client import SalesforceClient

logger = logging.getLogger(__name__)

class WriteOperationParser:
    """Parse natural language commands for Salesforce write operations"""
    
    def __init__(self, sf_client: SalesforceClient):
        self.sf_client = sf_client
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def parse_write_command(self, command: str, user_context: str = "", recent_entities: List[Dict] = None) -> Dict[str, Any]:
        """Parse a natural language command to determine write operation"""
        
        # First, determine if this is a write operation
        write_keywords = [
            'create', 'add', 'new', 'make', 'update', 'change', 'modify', 
            'set', 'move', 'close', 'note', 'task', 'schedule'
        ]
        
        command_lower = command.lower()
        is_write_operation = any(keyword in command_lower for keyword in write_keywords)
        
        if not is_write_operation:
            return {'is_write': False, 'message': 'This appears to be a read operation.'}
        
        # Use AI to parse the command structure
        try:
            # Include recent entities in the prompt for better context
            recent_context = ""
            if recent_entities:
                recent_context = "Recent entities from conversation:\n"
                for entity in recent_entities[:5]:  # Use last 5 entities
                    if entity.get('type') == 'salesforce':
                        recent_context += f"- {entity.get('object_type')}: {entity.get('title', 'Unknown')} (ID: {entity.get('record_id', 'Unknown')})\n"
                recent_context += "\n"
            
            prompt = f"""
            You are a Salesforce command parser. You MUST respond with ONLY valid JSON, nothing else.
            
            Analyze this Salesforce command and extract structured information for write operations.
            
            Command: "{command}"
            User Context: "{user_context}"
            
            {recent_context}
            
            IMPORTANT: If the user refers to "the opportunity", "the account", "the contact" etc. without naming it specifically,
            use the most recent entity from the conversation context above. For example, if they just asked about "Zillow" 
            and now say "update the opportunity", they mean the Zillow opportunity.
            
            Determine:
            1. Operation type (create_account, create_opportunity, create_contact, create_task, update_opportunity, update_account, update_contact, add_note)
            2. Extract relevant field values and data
            3. Identify any records that need to be found/linked (for updates, include the record name to find)
            4. Suggest confirmation message for the user
            
            For UPDATE operations:
            - Always include the record name/identifier in needs_lookup
            - Only include fields that should be changed in data (not the record name for identification)
            
            Available Salesforce fields:
            - Account: Name, Type, Industry, Website, Phone, Description
            - Opportunity: Name, StageName, Amount, CloseDate, AccountId, Description (use Description for next steps/notes)
            - Contact: FirstName, LastName, Email, Phone, Title, AccountId
            - Task: Subject, Description, Status, Priority, ActivityDate, WhoId, WhatId
            
            OPPORTUNITY NAMING CONVENTIONS:
            - When user says "create opportunity for [Company]", the Name should be "[Company]" NOT "Opportunity for [Company]"
            - Examples:
              * "Create opportunity for Candid Health" → Name: "Candid Health"
              * "Create opportunity for Microsoft with docs" → Name: "Microsoft - Docs"
              * "Create Zillow opportunity for SDK project" → Name: "Zillow - SDK"
            - Use the company name as the base, add descriptive suffix if mentioned
            - NEVER include words like "Opportunity for" or "Opportunity with" in the Name field
            
            IMPORTANT FIELD MAPPING:
            - For "next steps" → use "next_steps" (system will find actual field)
            - For "notes" on Opportunity → use "notes" (system will find actual field)  
            - System will automatically detect correct field names in user's Salesforce org
            
            Common Opportunity Stages: Prospecting, Qualification, Needs Analysis, Value Proposition, Proposal/Price Quote, Negotiation/Review, Closed Won, Closed Lost
            
            RESPONSE FORMAT: Return ONLY valid JSON with no additional text, explanations, or formatting.
            
            For successful parsing:
            {{
                "is_write": true,
                "operation": "create_opportunity",
                "data": {{"Name": "...", "StageName": "...", ...}},
                "needs_lookup": [{{"object": "Account", "name": "..."}}, ...],
                "confirmation": "I'll create a new opportunity called '...' for account '...' with amount $... and close date ...",
                "confidence": 0.8
            }}
            
            Example for "Create opportunity for Candid Health with $50K amount":
            {{
                "is_write": true,
                "operation": "create_opportunity", 
                "data": {{"Name": "Candid Health", "Amount": 50000}},
                "needs_lookup": [{{"object": "Account", "name": "Candid Health"}}],
                "confirmation": "I'll create a new opportunity called 'Candid Health' for account 'Candid Health' with amount $50,000.",
                "confidence": 0.9
            }}
            
            For UPDATE operations (examples):
            {{
                "is_write": true,
                "operation": "update_opportunity",
                "data": {{"StageName": "Negotiation"}},
                "needs_lookup": [{{"object": "Opportunity", "name": "Zillow"}}],
                "confirmation": "I'll update the 'Zillow' opportunity to stage 'Negotiation'.",
                "confidence": 0.9
            }}
            
            For next steps (system will find correct field):
            {{
                "is_write": true,
                "operation": "update_opportunity", 
                "data": {{"next_steps": "chris testing"}},
                "needs_lookup": [{{"object": "Opportunity", "name": "Zillow"}}],
                "confirmation": "I'll update the 'Zillow' opportunity next steps to 'chris testing'.",
                "confidence": 0.9
            }}
            
            If unsure or missing critical information:
            {{
                "is_write": true,
                "operation": "unclear",
                "missing_info": ["required field names"],
                "suggestions": "Could you specify...",
                "confidence": 0.3
            }}
            
            Remember: Return ONLY the JSON object, no other text.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a Salesforce command parser. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            response_content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response for write parsing: {response_content}")
            
            if not response_content:
                logger.error("Empty response from OpenAI")
                return {
                    'is_write': True,
                    'operation': 'error',
                    'error': 'Empty response from AI parser',
                    'message': 'Sorry, I had trouble understanding that command. Could you try rephrasing it?'
                }
            
            # Try to extract JSON if response has extra content
            if not response_content.startswith('{'):
                # Look for JSON block in response
                import re
                json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
                if json_match:
                    response_content = json_match.group(0)
                else:
                    logger.error(f"No JSON found in response: {response_content}")
                    return {
                        'is_write': True,
                        'operation': 'error',
                        'error': 'Invalid response format',
                        'message': 'Sorry, I had trouble understanding that command. Could you try rephrasing it?'
                    }
            
            try:
                result = json.loads(response_content)
                return result
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}, response: {response_content}")
                return {
                    'is_write': True,
                    'operation': 'error',
                    'error': f'JSON parsing failed: {str(e)}',
                    'message': 'Sorry, I had trouble understanding that command. Could you try rephrasing it?'
                }
            
        except Exception as e:
            logger.error(f"Error parsing write command: {e}")
            return {
                'is_write': True,
                'operation': 'error',
                'error': str(e),
                'message': 'Sorry, I had trouble understanding that command. Could you try rephrasing it?'
            }
    
    def execute_write_operation(self, parsed_command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a parsed write operation"""
        
        operation = parsed_command.get('operation')
        data = parsed_command.get('data', {})
        
        if operation == 'create_account':
            return self._create_account(data)
        elif operation == 'create_opportunity':
            return self._create_opportunity(data, parsed_command.get('needs_lookup', []))
        elif operation == 'create_contact':
            return self._create_contact(data, parsed_command.get('needs_lookup', []))
        elif operation == 'create_task':
            return self._create_task(data, parsed_command.get('needs_lookup', []))
        elif operation == 'update_opportunity':
            return self._update_opportunity(data, parsed_command.get('needs_lookup', []))
        elif operation == 'update_account':
            return self._update_account(data, parsed_command.get('needs_lookup', []))
        elif operation == 'update_contact':
            return self._update_contact(data, parsed_command.get('needs_lookup', []))
        elif operation == 'add_note':
            return self._add_note(data, parsed_command.get('needs_lookup', []))
        else:
            return {
                'success': False,
                'error': f'Unsupported operation: {operation}',
                'message': 'Sorry, I don\'t know how to perform that operation yet.'
            }
    
    def _resolve_lookups(self, lookups: List[Dict[str, str]]) -> Dict[str, str]:
        """Resolve record lookups by name"""
        resolved = {}
        
        for lookup in lookups:
            object_type = lookup.get('object')
            name = lookup.get('name')
            
            if not object_type or not name:
                continue
            
            records = self.sf_client.find_records_by_name(object_type, name)
            if records:
                # Take the first match
                resolved[f"{object_type}Id"] = records[0]['Id']
                resolved[f"{object_type}Name"] = records[0].get('Name') or f"{records[0].get('FirstName', '')} {records[0].get('LastName', '')}".strip()
            else:
                logger.warning(f"Could not find {object_type} with name '{name}'")
        
        return resolved
    
    def _add_default_required_fields(self, data: Dict[str, Any], object_type: str) -> Dict[str, Any]:
        """Add default values for org-specific required fields"""
        
        if object_type.lower() == 'account':
            # Add common required fields that might exist in the org
            if 'Source__c' not in data:
                # Try to get valid picklist values for Source__c
                source_values = self.sf_client.get_picklist_values('Account', 'Source__c')
                if source_values:
                    # Use the first available value, preferring common ones
                    preferred_sources = ['Web', 'Other', 'Partner', 'Referral', 'Website', 'Online']
                    selected_source = None
                    
                    for preferred in preferred_sources:
                        if preferred in source_values:
                            selected_source = preferred
                            break
                    
                    if not selected_source:
                        selected_source = source_values[0]  # Use first available
                    
                    data['Source__c'] = selected_source
                    logger.info(f"Using Source__c value: {selected_source} (available: {source_values})")
                else:
                    # Fallback if we can't get picklist values
                    data['Source__c'] = 'Other'
                    
            if 'Additional_Sourcing_Information__c' not in data:
                data['Additional_Sourcing_Information__c'] = 'Created via Sales RAG Slack Bot'
            if 'Type' not in data:
                data['Type'] = 'Prospect'  # Default type
                
        elif object_type.lower() == 'opportunity':
            # Add defaults for opportunity required fields
            if 'StageName' not in data:
                data['StageName'] = 'Prospecting'
            if 'CloseDate' not in data:
                from datetime import datetime, timedelta
                data['CloseDate'] = (datetime.now() + timedelta(days=30)).date().isoformat()
                
        elif object_type.lower() == 'contact':
            # Add defaults for contact required fields
            if 'LastName' not in data and not data.get('LastName'):
                if 'FirstName' in data:
                    data['LastName'] = 'Unknown'  # Ensure LastName is present
                    
        return data
    
    def _create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Account"""
        try:
            # Add default required fields for this org
            data = self._add_default_required_fields(data, 'Account')
            
            result = self.sf_client.create_account(data)
            if result and result.get('success'):
                return {
                    'success': True,
                    'record_id': result.get('id'),
                    'message': f"✅ Successfully created Account '{data.get('Name')}' (ID: {result.get('id')})"
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create Account',
                    'message': '❌ Failed to create the Account. Please check the data and try again.'
                }
        except Exception as e:
            logger.error(f"Error creating account: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error creating Account: {str(e)}'
            }
    
    def _create_opportunity(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Create a new Opportunity"""
        try:
            # Resolve account lookup
            resolved = self._resolve_lookups(lookups)
            if 'AccountId' in resolved:
                data['AccountId'] = resolved['AccountId']
            
            # Format close date if provided as relative
            if 'CloseDate' in data:
                data['CloseDate'] = self._parse_date(data['CloseDate'])
            
            # Add default required fields for this org
            data = self._add_default_required_fields(data, 'Opportunity')
            
            result = self.sf_client.create_opportunity(data)
            if result and result.get('success'):
                account_info = f" for {resolved.get('AccountName', 'Unknown Account')}" if resolved.get('AccountName') else ""
                return {
                    'success': True,
                    'record_id': result.get('id'),
                    'message': f"✅ Successfully created Opportunity '{data.get('Name')}'{account_info} (ID: {result.get('id')})"
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create Opportunity',
                    'message': '❌ Failed to create the Opportunity. Please check the required fields and try again.'
                }
        except Exception as e:
            logger.error(f"Error creating opportunity: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error creating Opportunity: {str(e)}'
            }
    
    def _create_contact(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Create a new Contact"""
        try:
            # Resolve account lookup
            resolved = self._resolve_lookups(lookups)
            if 'AccountId' in resolved:
                data['AccountId'] = resolved['AccountId']
            
            # Add default required fields for this org
            data = self._add_default_required_fields(data, 'Contact')
            
            result = self.sf_client.create_contact(data)
            if result and result.get('success'):
                full_name = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip()
                account_info = f" at {resolved.get('AccountName', 'Unknown Account')}" if resolved.get('AccountName') else ""
                return {
                    'success': True,
                    'record_id': result.get('id'),
                    'message': f"✅ Successfully created Contact '{full_name}'{account_info} (ID: {result.get('id')})"
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create Contact',
                    'message': '❌ Failed to create the Contact. Please check the required fields and try again.'
                }
        except Exception as e:
            logger.error(f"Error creating contact: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error creating Contact: {str(e)}'
            }
    
    def _create_task(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Create a new Task"""
        try:
            # Resolve lookups for WhoId (Contact) and WhatId (Account/Opportunity)
            resolved = self._resolve_lookups(lookups)
            if 'ContactId' in resolved:
                data['WhoId'] = resolved['ContactId']
            if 'AccountId' in resolved:
                data['WhatId'] = resolved['AccountId']
            elif 'OpportunityId' in resolved:
                data['WhatId'] = resolved['OpportunityId']
            
            # Parse activity date
            if 'ActivityDate' in data:
                data['ActivityDate'] = self._parse_date(data['ActivityDate'])
            
            result = self.sf_client.create_task(data)
            if result and result.get('success'):
                return {
                    'success': True,
                    'record_id': result.get('id'),
                    'message': f"✅ Successfully created Task '{data.get('Subject')}' (ID: {result.get('id')})"
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create Task',
                    'message': '❌ Failed to create the Task. Please check the data and try again.'
                }
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error creating Task: {str(e)}'
            }
    
    def _update_opportunity(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Update an existing Opportunity"""
        try:
            # Try to find the opportunity to update
            opportunity_id = None
            opportunity_name = ""
            
            # Check if there's a specific opportunity mentioned in lookups
            resolved = self._resolve_lookups(lookups)
            if 'OpportunityId' in resolved:
                opportunity_id = resolved['OpportunityId']
                opportunity_name = resolved.get('OpportunityName', 'Unknown Opportunity')
            else:
                # Try to find by name in the data
                if 'Name' in data:
                    opp_records = self.sf_client.find_records_by_name('opportunity', data['Name'])
                    if opp_records:
                        opportunity_id = opp_records[0]['Id']
                        opportunity_name = opp_records[0]['Name']
                else:
                    # Look for opportunity names in lookups with different object types
                    for lookup in lookups:
                        if 'opportunity' in lookup.get('name', '').lower() or 'zillow' in lookup.get('name', '').lower():
                            opp_records = self.sf_client.find_records_by_name('opportunity', lookup['name'])
                            if opp_records:
                                opportunity_id = opp_records[0]['Id']
                                opportunity_name = opp_records[0]['Name']
                                break
            
            if not opportunity_id:
                return {
                    'success': False,
                    'message': '❌ Could not find the opportunity to update. Please specify the opportunity name more clearly.'
                }
            
            # Remove 'Name' from update data to avoid changing the opportunity name
            update_data = {k: v for k, v in data.items() if k != 'Name'}
            
            # Get existing record for append behavior
            existing_record = self.sf_client.get_record_by_id('opportunity', opportunity_id)
            
            # Smart field mapping - find actual field names in Salesforce
            mapped_data = {}
            for key, value in update_data.items():
                actual_field_name = None
                
                # Try to find actual field name for common terms
                if key.lower() in ['nextsteps', 'next_steps', 'next steps']:
                    # Search for Next Steps field variations
                    actual_field_name = self.sf_client.find_field_name('opportunity', [
                        'Next_Steps__c', 'NextSteps__c', 'Next_Step__c', 'NextStep__c',
                        'next steps', 'next_steps', 'nextsteps'
                    ])
                    if not actual_field_name:
                        logger.warning("No Next Steps field found, falling back to Description")
                        actual_field_name = 'Description'
                elif key.lower() in ['notes', 'note']:
                    actual_field_name = self.sf_client.find_field_name('opportunity', [
                        'Notes__c', 'Note__c', 'notes'
                    ]) or 'Description'
                else:
                    actual_field_name = key
                
                # Get existing field value for append behavior
                existing_value = existing_record.get(actual_field_name, '') if existing_record else ''
                
                # Append new value to existing (unless it's a stage or amount field)
                if actual_field_name.lower() in ['stagename', 'amount', 'closedate', 'probability']:
                    # Replace these fields completely
                    mapped_data[actual_field_name] = value
                else:
                    # Prepend to existing content (add at top)
                    if existing_value and existing_value.strip():
                        # Add new content with timestamp at the top
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                        mapped_data[actual_field_name] = f"[{timestamp}]: {value}\n\n{existing_value}"
                    else:
                        mapped_data[actual_field_name] = value
            
            update_data = mapped_data
            
            # Parse dates if needed
            if 'CloseDate' in update_data:
                update_data['CloseDate'] = self._parse_date(update_data['CloseDate'])
            
            # Perform the update
            result = self.sf_client.update_opportunity(opportunity_id, update_data)
            if result is not None:  # Salesforce update returns 204 on success, None on failure
                updated_fields = ", ".join([f"{k}: {v}" for k, v in update_data.items()])
                return {
                    'success': True,
                    'record_id': opportunity_id,
                    'message': f"✅ Successfully updated Opportunity '{opportunity_name}' (ID: {opportunity_id})\nUpdated: {updated_fields}"
                }
            else:
                return {
                    'success': False,
                    'message': f'❌ Failed to update Opportunity "{opportunity_name}". Please check the field values and try again.'
                }
        except Exception as e:
            logger.error(f"Error updating opportunity: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error updating Opportunity: {str(e)}'
            }
    
    def _update_account(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Update an existing Account"""
        return {
            'success': False,
            'message': '❌ Update operations need more specific record identification. Please provide the Account ID or more specific details.'
        }
    
    def _update_contact(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Update an existing Contact"""
        return {
            'success': False,
            'message': '❌ Update operations need more specific record identification. Please provide the Contact ID or more specific details.'
        }
    
    def _add_note(self, data: Dict[str, Any], lookups: List[Dict[str, str]]) -> Dict[str, Any]:
        """Add a note to a record"""
        try:
            resolved = self._resolve_lookups(lookups)
            parent_id = None
            parent_name = ""
            
            # Find the parent record ID
            for key, value in resolved.items():
                if key.endswith('Id'):
                    parent_id = value
                    parent_name = resolved.get(key.replace('Id', 'Name'), 'Unknown')
                    break
            
            if not parent_id:
                return {
                    'success': False,
                    'message': '❌ Could not find the record to add the note to. Please specify the account, opportunity, or contact name.'
                }
            
            note_content = data.get('Body') or data.get('content') or data.get('note')
            title = data.get('Title') or "Note from Slack"
            
            result = self.sf_client.add_note(parent_id, note_content, title)
            if result and result.get('success'):
                return {
                    'success': True,
                    'record_id': result.get('id'),
                    'message': f"✅ Successfully added note to {parent_name} (Note ID: {result.get('id')})"
                }
            else:
                return {
                    'success': False,
                    'message': '❌ Failed to add the note. Please try again.'
                }
        except Exception as e:
            logger.error(f"Error adding note: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'❌ Error adding note: {str(e)}'
            }
    
    def _parse_date(self, date_str: str) -> str:
        """Parse relative dates like 'next month', 'in 2 weeks' to YYYY-MM-DD format"""
        date_str = date_str.lower().strip()
        today = datetime.now().date()
        
        # Handle relative dates
        if 'today' in date_str:
            return today.isoformat()
        elif 'tomorrow' in date_str:
            return (today + timedelta(days=1)).isoformat()
        elif 'next week' in date_str:
            return (today + timedelta(weeks=1)).isoformat()
        elif 'next month' in date_str:
            return (today + timedelta(days=30)).isoformat()
        elif 'in' in date_str and 'week' in date_str:
            # Extract number of weeks
            match = re.search(r'in (\d+) weeks?', date_str)
            if match:
                weeks = int(match.group(1))
                return (today + timedelta(weeks=weeks)).isoformat()
        elif 'in' in date_str and 'day' in date_str:
            # Extract number of days
            match = re.search(r'in (\d+) days?', date_str)
            if match:
                days = int(match.group(1))
                return (today + timedelta(days=days)).isoformat()
        
        # Try to parse as actual date
        try:
            from dateutil import parser
            parsed_date = parser.parse(date_str).date()
            return parsed_date.isoformat()
        except:
            # Default to 30 days from now
            return (today + timedelta(days=30)).isoformat() 