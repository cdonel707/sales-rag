from simple_salesforce import Salesforce, SalesforceLogin
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class SalesforceClient:
    def __init__(self, username: str, password: str, security_token: str, domain: str = None):
        self.username = username
        self.password = password
        self.security_token = security_token
        self.domain = domain
        self._sf = None
        
    def connect(self):
        """Establish connection to Salesforce"""
        try:
            if self.domain:
                session_id, instance = SalesforceLogin(
                    username=self.username,
                    password=self.password,
                    security_token=self.security_token,
                    domain=self.domain
                )
                self._sf = Salesforce(instance=instance, session_id=session_id)
            else:
                self._sf = Salesforce(
                    username=self.username,
                    password=self.password,
                    security_token=self.security_token
                )
            logger.info("Successfully connected to Salesforce")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Salesforce: {e}")
            return False
    
    def get_accounts(self, limit: int = 100) -> List[Dict]:
        """Retrieve account data"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            query = f"""
            SELECT Id, Name, Type, Industry, Description, Website, Phone, 
                   BillingStreet, BillingCity, BillingState, BillingCountry,
                   AnnualRevenue, NumberOfEmployees, LastModifiedDate
            FROM Account 
            WHERE IsDeleted = false
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
            """
            result = self._sf.query(query)
            return result['records']
        except Exception as e:
            logger.error(f"Error fetching accounts: {e}")
            return []
    
    def get_opportunities(self, limit: int = 100) -> List[Dict]:
        """Retrieve opportunity data"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            query = f"""
            SELECT Id, Name, StageName, Amount, CloseDate, Probability, 
                   Type, LeadSource, Description, Account.Name, 
                   Owner.Name, LastModifiedDate
            FROM Opportunity 
            WHERE IsDeleted = false
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
            """
            result = self._sf.query(query)
            return result['records']
        except Exception as e:
            logger.error(f"Error fetching opportunities: {e}")
            return []
    
    def get_contacts(self, limit: int = 100) -> List[Dict]:
        """Retrieve contact data"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            query = f"""
            SELECT Id, FirstName, LastName, Email, Phone, Title, 
                   Department, Account.Name, MailingStreet, MailingCity, 
                   MailingState, MailingCountry, LastModifiedDate
            FROM Contact 
            WHERE IsDeleted = false
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
            """
            result = self._sf.query(query)
            return result['records']
        except Exception as e:
            logger.error(f"Error fetching contacts: {e}")
            return []
    
    def get_cases(self, limit: int = 100) -> List[Dict]:
        """Retrieve case data"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            query = f"""
            SELECT Id, CaseNumber, Subject, Status, Priority, Type, 
                   Description, Account.Name, Contact.Name, 
                   Owner.Name, CreatedDate, LastModifiedDate
            FROM Case 
            WHERE IsDeleted = false
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
            """
            result = self._sf.query(query)
            return result['records']
        except Exception as e:
            logger.error(f"Error fetching cases: {e}")
            return []
    
    def search_records(self, search_term: str, limit: int = 50) -> List[Dict]:
        """Search across multiple Salesforce objects"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            # SOSL search across multiple objects
            search_query = f"""
            FIND {{'{search_term}'}} IN ALL FIELDS
            RETURNING Account(Id, Name, Type, Industry, Description),
                     Opportunity(Id, Name, StageName, Amount, Account.Name),
                     Contact(Id, FirstName, LastName, Email, Account.Name),
                     Case(Id, CaseNumber, Subject, Status, Description)
            LIMIT {limit}
            """
            result = self._sf.search(search_query)
            return result.get('searchRecords', [])
        except Exception as e:
            logger.error(f"Error searching Salesforce: {e}")
            return []
    
    def format_record_for_embedding(self, record: Dict, object_type: str) -> str:
        """Format Salesforce record for text embedding"""
        if object_type == 'Account':
            return f"""
            Account: {record.get('Name', '')}
            Type: {record.get('Type', '')}
            Industry: {record.get('Industry', '')}
            Description: {record.get('Description', '')}
            Website: {record.get('Website', '')}
            Phone: {record.get('Phone', '')}
            Annual Revenue: {record.get('AnnualRevenue', '')}
            Employees: {record.get('NumberOfEmployees', '')}
            """
        elif object_type == 'Opportunity':
            return f"""
            Opportunity: {record.get('Name', '')}
            Account: {record.get('Account', {}).get('Name', '') if record.get('Account') else ''}
            Stage: {record.get('StageName', '')}
            Amount: {record.get('Amount', '')}
            Close Date: {record.get('CloseDate', '')}
            Description: {record.get('Description', '')}
            Owner: {record.get('Owner', {}).get('Name', '') if record.get('Owner') else ''}
            """
        elif object_type == 'Contact':
            return f"""
            Contact: {record.get('FirstName', '')} {record.get('LastName', '')}
            Email: {record.get('Email', '')}
            Phone: {record.get('Phone', '')}
            Title: {record.get('Title', '')}
            Account: {record.get('Account', {}).get('Name', '') if record.get('Account') else ''}
            Department: {record.get('Department', '')}
            """
        elif object_type == 'Case':
            return f"""
            Case: {record.get('CaseNumber', '')}
            Subject: {record.get('Subject', '')}
            Status: {record.get('Status', '')}
            Priority: {record.get('Priority', '')}
            Description: {record.get('Description', '')}
            Account: {record.get('Account', {}).get('Name', '') if record.get('Account') else ''}
            """
        else:
            return json.dumps(record, indent=2)
    
    # ====== WRITE OPERATIONS ======
    
    def create_account(self, account_data: Dict[str, Any]) -> Optional[Dict]:
        """Create a new Account in Salesforce"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            # Validate required fields
            if not account_data.get('Name'):
                raise ValueError("Account Name is required")
            
            result = self._sf.Account.create(account_data)
            logger.info(f"Created Account with ID: {result.get('id')}")
            return result
        except Exception as e:
            logger.error(f"Error creating Account: {e}")
            return None
    
    def create_opportunity(self, opportunity_data: Dict[str, Any]) -> Optional[Dict]:
        """Create a new Opportunity in Salesforce"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            # Validate required fields
            required_fields = ['Name', 'StageName', 'CloseDate']
            for field in required_fields:
                if not opportunity_data.get(field):
                    raise ValueError(f"{field} is required for Opportunity")
            
            # Set default stage if not provided
            if not opportunity_data.get('StageName'):
                opportunity_data['StageName'] = 'Prospecting'
            
            result = self._sf.Opportunity.create(opportunity_data)
            logger.info(f"Created Opportunity with ID: {result.get('id')}")
            return result
        except Exception as e:
            logger.error(f"Error creating Opportunity: {e}")
            return None
    
    def create_contact(self, contact_data: Dict[str, Any]) -> Optional[Dict]:
        """Create a new Contact in Salesforce"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            # Validate required fields
            if not contact_data.get('LastName'):
                raise ValueError("Contact LastName is required")
            
            result = self._sf.Contact.create(contact_data)
            logger.info(f"Created Contact with ID: {result.get('id')}")
            return result
        except Exception as e:
            logger.error(f"Error creating Contact: {e}")
            return None
    
    def create_task(self, task_data: Dict[str, Any]) -> Optional[Dict]:
        """Create a new Task in Salesforce"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            # Validate required fields
            if not task_data.get('Subject'):
                raise ValueError("Task Subject is required")
            
            # Set default status if not provided
            if not task_data.get('Status'):
                task_data['Status'] = 'Not Started'
            
            result = self._sf.Task.create(task_data)
            logger.info(f"Created Task with ID: {result.get('id')}")
            return result
        except Exception as e:
            logger.error(f"Error creating Task: {e}")
            return None
    
    def update_opportunity(self, opportunity_id: str, update_data: Dict[str, Any]) -> Optional[Dict]:
        """Update an existing Opportunity"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            result = self._sf.Opportunity.update(opportunity_id, update_data)
            logger.info(f"Updated Opportunity {opportunity_id}")
            return result
        except Exception as e:
            logger.error(f"Error updating Opportunity {opportunity_id}: {e}")
            return None
    
    def update_account(self, account_id: str, update_data: Dict[str, Any]) -> Optional[Dict]:
        """Update an existing Account"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            result = self._sf.Account.update(account_id, update_data)
            logger.info(f"Updated Account {account_id}")
            return result
        except Exception as e:
            logger.error(f"Error updating Account {account_id}: {e}")
            return None
    
    def update_contact(self, contact_id: str, update_data: Dict[str, Any]) -> Optional[Dict]:
        """Update an existing Contact"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            result = self._sf.Contact.update(contact_id, update_data)
            logger.info(f"Updated Contact {contact_id}")
            return result
        except Exception as e:
            logger.error(f"Error updating Contact {contact_id}: {e}")
            return None
    
    def add_note(self, parent_id: str, note_content: str, title: str = "Note from Slack") -> Optional[Dict]:
        """Add a note to a Salesforce record"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            note_data = {
                'ParentId': parent_id,
                'Title': title,
                'Body': note_content,
                'IsPrivate': False
            }
            result = self._sf.Note.create(note_data)
            logger.info(f"Added note to record {parent_id}")
            return result
        except Exception as e:
            logger.error(f"Error adding note to {parent_id}: {e}")
            return None
    
    def get_record_by_id(self, object_type: str, record_id: str) -> Optional[Dict]:
        """Get a specific record by ID"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            if object_type.lower() == 'account':
                record = self._sf.Account.get(record_id)
            elif object_type.lower() == 'opportunity':
                record = self._sf.Opportunity.get(record_id)
            elif object_type.lower() == 'contact':
                record = self._sf.Contact.get(record_id)
            elif object_type.lower() == 'case':
                record = self._sf.Case.get(record_id)
            else:
                raise ValueError(f"Unsupported object type: {object_type}")
            
            return record
        except Exception as e:
            logger.error(f"Error getting {object_type} record {record_id}: {e}")
            return None
    
    def find_records_by_name(self, object_type: str, name: str) -> List[Dict]:
        """Find records by name for linking/reference"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            if object_type.lower() == 'account':
                query = f"SELECT Id, Name FROM Account WHERE Name LIKE '%{name}%' LIMIT 10"
            elif object_type.lower() == 'contact':
                query = f"SELECT Id, FirstName, LastName, Account.Name FROM Contact WHERE (FirstName LIKE '%{name}%' OR LastName LIKE '%{name}%') LIMIT 10"
            elif object_type.lower() == 'opportunity':
                query = f"SELECT Id, Name, Account.Name FROM Opportunity WHERE Name LIKE '%{name}%' LIMIT 10"
            else:
                return []
            
            result = self._sf.query(query)
            return result['records']
        except Exception as e:
            logger.error(f"Error finding {object_type} records by name '{name}': {e}")
            return []
    
    def get_picklist_values(self, object_type: str, field_name: str) -> List[str]:
        """Get picklist values for a field"""
        if not self._sf:
            if not self.connect():
                return []
        
        try:
            if object_type.lower() == 'opportunity':
                obj_desc = self._sf.Opportunity.describe()
            elif object_type.lower() == 'account':
                obj_desc = self._sf.Account.describe()
            elif object_type.lower() == 'contact':
                obj_desc = self._sf.Contact.describe()
            else:
                return []
            
            for field in obj_desc['fields']:
                if field['name'] == field_name and field['type'] == 'picklist':
                    return [value['value'] for value in field['picklistValues'] if value['active']]
            
            return []
        except Exception as e:
            logger.error(f"Error getting picklist values for {object_type}.{field_name}: {e}")
            return []
    
    def find_field_name(self, object_type: str, search_terms: List[str]) -> Optional[str]:
        """Find actual field name by searching for common terms"""
        if not self._sf:
            if not self.connect():
                return None
        
        try:
            if object_type.lower() == 'opportunity':
                obj_desc = self._sf.Opportunity.describe()
            elif object_type.lower() == 'account':
                obj_desc = self._sf.Account.describe()
            elif object_type.lower() == 'contact':
                obj_desc = self._sf.Contact.describe()
            else:
                return None
            
            # Search through all fields for matches
            for field in obj_desc['fields']:
                field_name = field['name'].lower()
                field_label = field.get('label', '').lower()
                
                for term in search_terms:
                    term_lower = term.lower()
                    if (term_lower in field_name or 
                        term_lower in field_label or
                        field_name.replace('_', '').replace('__c', '') == term_lower.replace(' ', '').replace('_', '')):
                        logger.info(f"Found field match: {term} -> {field['name']} ({field.get('label')})")
                        return field['name']
            
            return None
        except Exception as e:
            logger.error(f"Error finding field name for {object_type}: {e}")
            return None 