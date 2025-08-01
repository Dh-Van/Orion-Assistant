"""
Intent recognition models.
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel, Field


class IntentType(Enum):
    """Types of user intents."""
    # Email actions
    SEND_EMAIL = "send_email"
    READ_EMAIL = "read_email"
    SEARCH_EMAIL = "search_email"
    REPLY_EMAIL = "reply_email"
    DELETE_EMAIL = "delete_email"
    MARK_READ = "mark_read"
    
    # Control intents
    CONFIRM = "confirm"
    CANCEL = "cancel"
    HELP = "help"
    REPEAT = "repeat"
    CLARIFY = "clarify"
    
    # Navigation
    NEXT = "next"
    PREVIOUS = "previous"
    
    # Meta intents
    GREETING = "greeting"
    GOODBYE = "goodbye"
    THANK_YOU = "thank_you"
    
    # Unknown
    UNCLEAR = "unclear"


@dataclass
class UserIntent:
    """
    Recognized user intent with confidence and entities.
    """
    type: IntentType
    confidence: float  # 0-1 confidence score
    entities: Optional[Dict[str, Any]] = None
    original_text: str = ""
    
    def is_email_action(self) -> bool:
        """Check if this is an email-related action."""
        return self.type in [
            IntentType.SEND_EMAIL,
            IntentType.READ_EMAIL,
            IntentType.SEARCH_EMAIL,
            IntentType.REPLY_EMAIL,
            IntentType.DELETE_EMAIL,
            IntentType.MARK_READ
        ]
    
    def is_control_action(self) -> bool:
        """Check if this is a control action."""
        return self.type in [
            IntentType.CONFIRM,
            IntentType.CANCEL,
            IntentType.HELP,
            IntentType.REPEAT,
            IntentType.CLARIFY
        ]
    
    def requires_confirmation(self) -> bool:
        """Check if this intent typically requires confirmation."""
        return self.type in [
            IntentType.SEND_EMAIL,
            IntentType.DELETE_EMAIL,
            IntentType.REPLY_EMAIL
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "entities": self.entities or {},
            "original_text": self.original_text
        }


# Pydantic models for LLM-based intent recognition
class IntentClassification(BaseModel):
    """Structured intent classification from LLM."""
    intent: IntentType = Field(description="Classified intent type")
    confidence: float = Field(description="Confidence score 0-1", ge=0, le=1)
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    reasoning: Optional[str] = Field(None, description="Reasoning for classification")


class EmailEntity(BaseModel):
    """Email-specific entity extraction."""
    recipient: Optional[str] = Field(None, description="Email recipient")
    recipients: List[str] = Field(default_factory=list, description="Multiple recipients")
    subject: Optional[str] = Field(None, description="Email subject")
    body: Optional[str] = Field(None, description="Email body content")
    cc: List[str] = Field(default_factory=list, description="CC recipients")
    bcc: List[str] = Field(default_factory=list, description="BCC recipients")


class SearchEntity(BaseModel):
    """Search-specific entity extraction."""
    query: str = Field(description="Search query")
    search_field: str = Field(default="all", description="Field to search: subject, body, from, to, all")
    date_range: Optional[Dict[str, str]] = Field(None, description="Date range for search")
    limit: int = Field(default=5, description="Number of results")


class ReadEntity(BaseModel):
    """Read email entity extraction."""
    count: int = Field(default=5, description="Number of emails to read")
    filter: Optional[str] = Field(None, description="Filter: unread, today, recent, important")
    folder: Optional[str] = Field(None, description="Specific folder to read from")


class IntentContext(BaseModel):
    """Context for intent recognition."""
    previous_intent: Optional[IntentType] = Field(None, description="Previous user intent")
    conversation_phase: str = Field(description="Current conversation phase")
    awaiting_info: List[str] = Field(default_factory=list, description="Information being collected")
    has_draft: bool = Field(default=False, description="Whether there's a draft email")
    
    
# Intent patterns for improved recognition
INTENT_PATTERNS = {
    IntentType.SEND_EMAIL: [
        r"send (?:an? )?email",
        r"write (?:an? )?email",
        r"compose (?:an? )?email",
        r"email (\w+)",
        r"message (\w+)",
        r"send (?:a )?message"
    ],
    IntentType.READ_EMAIL: [
        r"read (?:my )?emails?",
        r"check (?:my )?emails?",
        r"show (?:me )?(?:my )?emails?",
        r"(?:do|did) I have (?:any )?(?:new )?emails?",
        r"what('s| is) in my inbox",
        r"any new messages"
    ],
    IntentType.SEARCH_EMAIL: [
        r"search (?:for )?(.+)",
        r"find (?:emails? )?(?:about |from |with )?(.+)",
        r"look for (.+)",
        r"where (?:is|are) (?:the )?(?:emails? )?(?:about |from )?(.+)",
        r"show me (?:emails? )?(?:about |from )?(.+)"
    ],
    IntentType.REPLY_EMAIL: [
        r"reply to (?:this |that |the )?email",
        r"respond to (?:this |that |the )?email",
        r"answer (?:this |that |the )?email",
        r"send (?:a )?reply"
    ],
    IntentType.CONFIRM: [
        r"^yes\b",
        r"^yeah\b",
        r"^yep\b",
        r"^sure\b",
        r"^correct\b",
        r"^right\b",
        r"^confirm\b",
        r"^send it\b",
        r"^go ahead\b",
        r"that'?s (?:correct|right)"
    ],
    IntentType.CANCEL: [
        r"^no\b",
        r"^nope\b",
        r"^cancel\b",
        r"^stop\b",
        r"^nevermind\b",
        r"^forget it\b",
        r"^abort\b",
        r"don't send"
    ]
}