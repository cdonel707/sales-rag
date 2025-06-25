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