"""
Email-related data models.
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel, Field


@dataclass
class EmailDraft:
    """Draft email being composed."""
    recipient: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    
    def is_complete(self) -> bool:
        """Check if draft has all required fields."""
        return all([self.recipient, self.subject, self.body])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recipient": self.recipient,
            "cc": self.cc,
            "bcc": self.bcc,
            "subject": self.subject,
            "body": self.body,
            "attachments": self.attachments
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmailDraft':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class EmailRequest:
    """Request to send an email."""
    to: Union[str, List[Dict[str, str]]]  # Email or list of {name, email}
    subject: str
    body: str
    cc: Optional[List[Dict[str, str]]] = None
    bcc: Optional[List[Dict[str, str]]] = None
    attachments: Optional[List[str]] = None
    reply_to_id: Optional[str] = None  # For reply functionality


@dataclass
class EmailResponse:
    """Response from email operations."""
    success: bool
    message: str
    error: Optional[str] = None
    email_id: Optional[str] = None  # ID of sent/processed email


@dataclass
class EmailSummary:
    """Voice-friendly email summary."""
    id: str
    sender_email: str
    sender_name: str
    subject: str
    body_preview: str
    date: int  # Unix timestamp
    date_str: str  # Human-readable date
    is_unread: bool = False
    has_attachments: bool = False
    
    def to_voice_description(self, include_body: bool = False) -> str:
        """
        Convert to natural speech description.
        
        Args:
            include_body: Whether to include body preview
            
        Returns:
            Voice-friendly description
        """
        description = f"Email from {self.sender_name}, sent {self.date_str}. "
        description += f"Subject: {self.subject}. "
        
        if self.is_unread:
            description = "Unread email. " + description
        
        if include_body and self.body_preview:
            description += f"Message says: {self.body_preview}"
        
        if self.has_attachments:
            description += " This email has attachments."
        
        return description


@dataclass
class SearchResult:
    """Email search result with relevance."""
    email_summary: EmailSummary
    relevance_score: float  # 0-1, higher is more relevant
    matched_field: str  # Which field matched (subject, body, from, etc.)
    
    def to_voice_description(self) -> str:
        """Convert to voice-friendly description."""
        return self.email_summary.to_voice_description()


# Pydantic models for structured LLM output
class EmailAction(BaseModel):
    """Structured email action from LLM."""
    action_type: str = Field(description="Type of action: send, read, search, reply")
    recipient: Optional[str] = Field(None, description="Email recipient")
    subject: Optional[str] = Field(None, description="Email subject")
    body: Optional[str] = Field(None, description="Email body content")
    search_query: Optional[str] = Field(None, description="Search query")
    email_count: Optional[int] = Field(None, description="Number of emails to read")
    
    # Status fields
    needs_more_info: bool = Field(description="Whether more information is needed")
    missing_fields: List[str] = Field(default_factory=list, description="Fields that need to be collected")
    confirmation_message: Optional[str] = Field(None, description="Message to confirm with user")


class EmailComposition(BaseModel):
    """Structured email composition from natural language."""
    to_addresses: List[str] = Field(description="List of recipient email addresses")
    cc_addresses: List[str] = Field(default_factory=list, description="CC recipients")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body content")
    tone: str = Field(default="professional", description="Email tone: professional, friendly, formal, casual")
    is_reply: bool = Field(default=False, description="Whether this is a reply")
    
    # Validation
    is_valid: bool = Field(description="Whether the email is ready to send")
    validation_errors: List[str] = Field(default_factory=list, description="Any validation issues")