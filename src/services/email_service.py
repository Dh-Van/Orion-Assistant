"""
Email Service - High-level business logic for email operations.
Wraps the Nylas client with voice-friendly interfaces.
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from loguru import logger

from ..clients.nylas import NylasClient, Email
from ..clients.gemini import GeminiClient
from ..models.email_models import (
    EmailRequest, EmailResponse, EmailSummary, SearchResult
)


class EmailService:
    """High-level email operations service."""
    
    def __init__(
        self,
        nylas_client: Optional[NylasClient] = None,
        gemini_client: Optional[GeminiClient] = None
    ):
        """
        Initialize email service.
        
        Args:
            nylas_client: Optional Nylas client instance
            gemini_client: Optional Gemini client for AI features
        """
        # Initialize clients if not provided
        if not nylas_client:
            grant_id = os.getenv('NYLAS_GRANT_ID')
            if not grant_id:
                raise ValueError("NYLAS_GRANT_ID environment variable not set")
            nylas_client = NylasClient(grant_id=grant_id)
            
        if not gemini_client:
            gemini_client = GeminiClient()
        
        self.nylas_client = nylas_client
        self.gemini_client = gemini_client
        
        logger.info("EmailService initialized")
    
    async def send_email(self, request: EmailRequest) -> EmailResponse:
        """
        Send an email.
        
        Args:
            request: Email request with recipient, subject, and body
            
        Returns:
            EmailResponse with success status
        """
        try:
            # Format recipient for Nylas
            to = request.to
            if isinstance(to, str):
                to = [{'email': to, 'name': to.split('@')[0]}]
            
            # Send email
            success = self.nylas_client.send_email(
                to=to,
                subject=request.subject,
                body=request.body,
                cc=request.cc,
                bcc=request.bcc
            )
            
            if success:
                logger.info(f"Email sent successfully to {request.to}")
                return EmailResponse(
                    success=True,
                    message=f"Email sent successfully to {request.to}"
                )
            else:
                return EmailResponse(
                    success=False,
                    message="Failed to send email",
                    error="Unknown error from email service"
                )
                
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return EmailResponse(
                success=False,
                message="Failed to send email",
                error=str(e)
            )
    
    async def read_recent_emails(
        self,
        limit: int = 5,
        unread_only: bool = False
    ) -> List[EmailSummary]:
        """
        Read recent emails and return voice-friendly summaries.
        
        Args:
            limit: Maximum number of emails to return
            unread_only: Only return unread emails
            
        Returns:
            List of email summaries
        """
        try:
            # Fetch emails
            emails = self.nylas_client.read_emails(
                limit=limit,
                unread_only=unread_only
            )
            
            # Convert to summaries
            summaries = []
            for email in emails:
                summary = await self._create_email_summary(email)
                summaries.append(summary)
            
            logger.info(f"Retrieved {len(summaries)} email summaries")
            return summaries
            
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            return []
    
    async def search_emails(
        self,
        query: str,
        search_field: str = "all",
        limit: int = 5,
        use_ai: bool = True
    ) -> List[SearchResult]:
        """
        Search emails with optional AI-powered semantic search.
        
        Args:
            query: Search query
            search_field: Field to search (subject, body, from, all)
            limit: Maximum results
            use_ai: Use AI for semantic search
            
        Returns:
            List of search results
        """
        try:
            if use_ai and search_field in ["body", "all"]:
                # Use vector search for better results
                emails = self.nylas_client.read_emails(limit=50)  # Get more for AI search
                
                if emails:
                    # Convert to dicts for vector search
                    email_dicts = [email.to_dict() for email in emails]
                    
                    # Perform vector search
                    results = self.gemini_client.search_emails_with_vectors(
                        emails=email_dicts,
                        query=query,
                        search_field=search_field,
                        num_results=limit
                    )
                    
                    # Convert results
                    search_results = []
                    for email_dict, score in results:
                        # Create Email object from dict
                        email = Email(
                            id=email_dict.get('id'),
                            subject=email_dict.get('subject'),
                            body=email_dict.get('body'),
                            senders=[{'email': email_dict.get('senders', '')}],
                            date=email_dict.get('date', 0)
                        )
                        
                        summary = await self._create_email_summary(email)
                        search_results.append(SearchResult(
                            email_summary=summary,
                            relevance_score=float(score),
                            matched_field=search_field
                        ))
                    
                    return search_results
            
            # Fallback to regular search
            emails = self.nylas_client.search_emails(
                query=query,
                search_field=search_field,
                limit=limit
            )
            
            # Convert to search results
            search_results = []
            for email in emails:
                summary = await self._create_email_summary(email)
                search_results.append(SearchResult(
                    email_summary=summary,
                    relevance_score=1.0,  # No score from regular search
                    matched_field=search_field
                ))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return []
    
    async def get_email_by_id(self, email_id: str) -> Optional[EmailSummary]:
        """
        Get a specific email by ID.
        
        Args:
            email_id: Email ID
            
        Returns:
            EmailSummary or None if not found
        """
        try:
            email = self.nylas_client.get_email_by_id(email_id)
            if email:
                return await self._create_email_summary(email, include_full_body=True)
            return None
            
        except Exception as e:
            logger.error(f"Error getting email: {e}")
            return None
    
    async def reply_to_email(
        self,
        email_id: str,
        body: str,
        reply_all: bool = False
    ) -> EmailResponse:
        """
        Reply to an email.
        
        Args:
            email_id: ID of email to reply to
            body: Reply body
            reply_all: Whether to reply to all recipients
            
        Returns:
            EmailResponse with status
        """
        try:
            success = self.nylas_client.reply_to_email(
                email_id=email_id,
                body=body,
                reply_all=reply_all
            )
            
            if success:
                return EmailResponse(
                    success=True,
                    message="Reply sent successfully"
                )
            else:
                return EmailResponse(
                    success=False,
                    message="Failed to send reply"
                )
                
        except Exception as e:
            logger.error(f"Error replying to email: {e}")
            return EmailResponse(
                success=False,
                message="Failed to send reply",
                error=str(e)
            )
    
    async def generate_reply(
        self,
        email_id: str,
        instruction: str,
        tone: str = "professional"
    ) -> Optional[str]:
        """
        Generate an AI reply to an email.
        
        Args:
            email_id: ID of email to reply to
            instruction: User's instruction for the reply
            tone: Tone of the reply
            
        Returns:
            Generated reply text or None
        """
        try:
            # Get original email
            email = self.nylas_client.get_email_by_id(email_id)
            if not email:
                return None
            
            # Generate reply
            reply = self.gemini_client.generate_email_reply(
                original_email=f"From: {email.senders[0]['email']}\nSubject: {email.subject}\n\n{email.body}",
                instruction=instruction,
                tone=tone
            )
            
            return reply
            
        except Exception as e:
            logger.error(f"Error generating reply: {e}")
            return None
    
    async def _create_email_summary(
        self,
        email: Email,
        include_full_body: bool = False
    ) -> EmailSummary:
        """
        Create a voice-friendly email summary.
        
        Args:
            email: Email object
            include_full_body: Whether to include full body or summarize
            
        Returns:
            EmailSummary object
        """
        # Extract sender info
        sender_email = email.senders[0]['email'] if email.senders else 'Unknown'
        sender_name = email.senders[0].get('name', sender_email.split('@')[0])
        
        # Handle body
        if include_full_body:
            body_preview = email.body
        else:
            # Summarize long emails for voice
            if len(email.body) > 200:
                body_preview = self.gemini_client.summarize_text(
                    text=email.body,
                    max_length=50,
                    style="concise"
                )
            else:
                # Just take first 100 chars
                body_preview = email.body[:100] + "..." if len(email.body) > 100 else email.body
        
        # Format date
        if email.date:
            date = datetime.fromtimestamp(email.date)
            # Make it voice-friendly
            if date.date() == datetime.now().date():
                date_str = f"today at {date.strftime('%-I:%M %p')}"
            elif (datetime.now().date() - date.date()).days == 1:
                date_str = f"yesterday at {date.strftime('%-I:%M %p')}"
            else:
                date_str = date.strftime('%B %-d at %-I:%M %p')
        else:
            date_str = "unknown time"
        
        return EmailSummary(
            id=email.id,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=email.subject,
            body_preview=body_preview,
            date=email.date,
            date_str=date_str,
            is_unread=getattr(email, 'unread', False)
        )
    
    def mark_as_read(self, email_id: str) -> bool:
        """
        Mark an email as read.
        
        Args:
            email_id: Email ID
            
        Returns:
            Success status
        """
        try:
            return self.nylas_client.mark_as_read(email_id)
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False