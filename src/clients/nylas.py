"""
Nylas email client for core email operations.
Extracted and cleaned from nylas_client.py
"""

import os
from typing import Dict, List, Optional, Union
from nylas import Client
from nylas.models.messages import Message
from loguru import logger

class Email:
    """Email data model with improved constructor."""
    
    def __init__(
        self, 
        email: Optional[Message] = None,
        id: Optional[str] = None,
        senders: Optional[List[Dict[str, str]]] = None,
        recipients: Optional[List[Dict[str, str]]] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        date: Optional[int] = None
    ):
        # Initialize with defaults
        self.id = id or ""
        self.senders = senders or []
        self.recipients = recipients or []
        self.subject = subject or ""
        self.body = body or ""
        self.date = date or 0
        
        # If Nylas Message provided, extract data
        if email:
            self.id = email.id or ""
            self.senders = email.from_ or []
            self.recipients = []
            
            # Combine all recipient types
            if email.to:
                self.recipients.extend(email.to)
            if email.cc:
                self.recipients.extend(email.cc)
            if email.bcc:
                self.recipients.extend(email.bcc)
                
            self.subject = email.subject or ""
            self.body = email.body or ""
            self.date = email.date or 0
    
    def get_reply_recipients(self) -> List[Dict[str, str]]:
        """Returns the original senders for reply."""
        return self.senders
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'senders': self.senders[0]['email'] if self.senders else '',
            'recipients': self.recipients[0]['email'] if self.recipients else '',
            'subject': self.subject,
            'body': self.body,
            'date': self.date
        }
    
    def __str__(self) -> str:
        """Human-readable representation."""
        sender = self.senders[0].get('email', 'Unknown') if self.senders else 'Unknown'
        return f"Email from {sender}: {self.subject}"


class NylasClient:
    """Client for Nylas email operations."""
    
    def __init__(self, grant_id: str, api_key: Optional[str] = None, api_uri: Optional[str] = None):
        """
        Initialize Nylas client.
        
        Args:
            grant_id: Nylas grant ID for the user
            api_key: Optional API key (defaults to env var)
            api_uri: Optional API URI (defaults to env var)
        """
        self.grant_id = grant_id
        self.api_key = api_key or os.getenv('NYLAS_API_KEY')
        self.api_uri = api_uri or os.getenv('NYLAS_API_URI', 'https://api.nylas.com')
        
        if not self.api_key:
            raise ValueError('NYLAS_API_KEY not provided or set in environment')
        
        self.client = Client(self.api_key, self.api_uri)
        logger.info(f"Initialized Nylas client for grant: {grant_id}")
    
    def send_email(
        self, 
        to: Union[List[Dict[str, str]], str], 
        subject: str, 
        body: str,
        cc: Optional[List[Dict[str, str]]] = None,
        bcc: Optional[List[Dict[str, str]]] = None
    ) -> bool:
        """
        Send an email.
        
        Args:
            to: Recipient(s) - either email string or list of dicts with 'name' and 'email'
            subject: Email subject
            body: Email body (plain text)
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            
        Returns:
            bool: True if sent successfully
        """
        try:
            # Handle string input for 'to'
            if isinstance(to, str):
                to = [{'name': to.split('@')[0], 'email': to}]
            
            logger.info(f"Sending email to: {to[0]['email']}")
            
            # Create draft
            draft_request = {
                "to": to,
                "subject": subject,
                "body": body
            }
            
            if cc:
                draft_request["cc"] = cc
            if bcc:
                draft_request["bcc"] = bcc
            
            draft_response = self.client.drafts.create(
                identifier=self.grant_id,
                request_body=draft_request
            )
            
            if not draft_response or not draft_response.data:
                logger.error("Failed to create draft")
                return False
            
            draft_id = draft_response.data.id
            logger.debug(f"Created draft with ID: {draft_id}")
            
            # Send the draft
            sent_message = self.client.drafts.send(
                identifier=self.grant_id, 
                draft_id=draft_id
            )
            
            if sent_message:
                logger.info(f"Email sent successfully to {to[0]['email']}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def read_emails(
        self, 
        limit: int = 100,
        unread_only: bool = False,
        folder: Optional[str] = None
    ) -> List[Email]:
        """
        Read emails from inbox.
        
        Args:
            limit: Maximum number of emails to fetch
            unread_only: Only fetch unread emails
            folder: Specific folder to read from
            
        Returns:
            List of Email objects
        """
        try:
            emails = []
            next_cursor = None
            
            while len(emails) < limit:
                query_params = {
                    'limit': min(100, limit - len(emails))
                }
                
                if next_cursor:
                    query_params['page_token'] = next_cursor
                
                if unread_only:
                    query_params['unread'] = True
                    
                if folder:
                    query_params['in'] = folder
                
                response = self.client.messages.list(
                    identifier=self.grant_id,
                    query_params=query_params
                )
                
                if not response.data:
                    break
                
                # Convert Nylas messages to Email objects
                for msg in response.data:
                    emails.append(Email(email=msg))
                
                next_cursor = response.next_cursor
                if not next_cursor:
                    break
            
            logger.info(f"Fetched {len(emails)} emails")
            return emails[:limit]
            
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            return []
    
    def search_emails(
        self,
        query: str,
        search_field: str = "subject",
        limit: int = 20
    ) -> List[Email]:
        """
        Search emails using Nylas search.
        
        Args:
            query: Search query
            search_field: Field to search in ('subject', 'from', 'to', 'body')
            limit: Maximum results
            
        Returns:
            List of matching Email objects
        """
        try:
            query_params = {
                'limit': limit
            }
            
            # Map search field to Nylas query parameter
            if search_field == "subject":
                query_params['subject'] = query
            elif search_field == "from":
                query_params['from'] = query
            elif search_field == "to":
                query_params['to'] = query
            elif search_field == "body":
                # Nylas doesn't have direct body search, use general search
                query_params['search'] = query
            else:
                query_params['search'] = query
            
            response = self.client.messages.list(
                identifier=self.grant_id,
                query_params=query_params
            )
            
            emails = []
            if response.data:
                for msg in response.data:
                    emails.append(Email(email=msg))
            
            logger.info(f"Found {len(emails)} emails matching '{query}'")
            return emails
            
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return []
    
    def get_email_by_id(self, email_id: str) -> Optional[Email]:
        """
        Fetch a specific email by ID.
        
        Args:
            email_id: Nylas message ID
            
        Returns:
            Email object or None if not found
        """
        try:
            message = self.client.messages.find(
                identifier=self.grant_id,
                message_id=email_id
            )
            
            if message and message.data:
                return Email(email=message.data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching email {email_id}: {e}")
            return None
    
    def reply_to_email(
        self,
        email_id: str,
        body: str,
        reply_all: bool = False
    ) -> bool:
        """
        Reply to an email.
        
        Args:
            email_id: ID of email to reply to
            body: Reply body
            reply_all: Whether to reply to all recipients
            
        Returns:
            bool: True if sent successfully
        """
        try:
            # Get original email
            original = self.get_email_by_id(email_id)
            if not original:
                logger.error(f"Could not find email {email_id}")
                return False
            
            # Determine recipients
            to = original.get_reply_recipients()
            cc = None
            
            if reply_all and original.recipients:
                # TODO: Filter out self from CC list
                cc = [r for r in original.recipients if r not in to]
            
            # Create subject
            subject = original.subject
            if not subject.lower().startswith('re:'):
                subject = f"Re: {subject}"
            
            # Send reply
            return self.send_email(to, subject, body, cc=cc)
            
        except Exception as e:
            logger.error(f"Error replying to email: {e}")
            return False
    
    def mark_as_read(self, email_id: str) -> bool:
        """
        Mark an email as read.
        
        Args:
            email_id: Nylas message ID
            
        Returns:
            bool: True if successful
        """
        try:
            self.client.messages.update(
                identifier=self.grant_id,
                message_id=email_id,
                request_body={"unread": False}
            )
            logger.debug(f"Marked email {email_id} as read")
            return True
            
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False