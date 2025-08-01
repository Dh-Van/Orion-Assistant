"""
Conversation state management models.
"""

from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from .intent_models import IntentType
from .email_models import EmailDraft


class ConversationPhase(Enum):
    """Current phase of the conversation."""
    IDLE = "idle"                          # Waiting for user input
    COLLECTING_INFO = "collecting_info"    # Gathering information
    PROCESSING = "processing"              # Processing request
    WAITING_CONFIRMATION = "waiting_confirmation"  # Waiting for user confirmation
    ERROR = "error"                        # Error state


@dataclass
class ConversationState:
    """
    Maintains the current state of the conversation.
    Tracks context, current intent, and collected information.
    """
    # Current conversation phase
    phase: ConversationPhase = ConversationPhase.IDLE
    
    # Current intent being processed
    current_intent: Optional[IntentType] = None
    
    # Draft email being composed
    draft_email: Optional[EmailDraft] = None
    
    # Current email being viewed/replied to
    current_email_id: Optional[str] = None
    
    # Search context
    last_search_query: Optional[str] = None
    last_search_results: List[str] = field(default_factory=list)  # Email IDs
    
    # Conversation history
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    
    # Error information
    last_error: Optional[str] = None
    
    # Timestamp of last interaction
    last_interaction: datetime = field(default_factory=datetime.now)
    
    # Additional context data
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str):
        """
        Add a message to conversation history.
        
        Args:
            role: 'user' or 'assistant'
            content: Message content
        """
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.last_interaction = datetime.now()
        
        # Keep history reasonable size (last 20 messages)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
    
    def get_recent_context(self, num_messages: int = 6) -> List[Dict[str, str]]:
        """
        Get recent conversation context.
        
        Args:
            num_messages: Number of recent messages to return
            
        Returns:
            List of recent messages
        """
        return self.conversation_history[-num_messages:]
    
    def set_error(self, error: str):
        """
        Set error state.
        
        Args:
            error: Error message
        """
        self.phase = ConversationPhase.ERROR
        self.last_error = error
    
    def clear_error(self):
        """Clear error state."""
        if self.phase == ConversationPhase.ERROR:
            self.phase = ConversationPhase.IDLE
        self.last_error = None
    
    def reset(self):
        """Reset conversation state to idle."""
        self.phase = ConversationPhase.IDLE
        self.current_intent = None
        self.draft_email = None
        self.current_email_id = None
        self.last_search_query = None
        self.last_search_results = []
        self.clear_error()
        # Keep conversation history for context
    
    def is_active(self) -> bool:
        """Check if conversation has active operation."""
        return self.phase not in [ConversationPhase.IDLE, ConversationPhase.ERROR]
    
    def get_minutes_since_interaction(self) -> float:
        """Get minutes since last interaction."""
        return (datetime.now() - self.last_interaction).total_seconds() / 60
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "phase": self.phase.value,
            "current_intent": self.current_intent.value if self.current_intent else None,
            "draft_email": self.draft_email.to_dict() if self.draft_email else None,
            "current_email_id": self.current_email_id,
            "last_search_query": self.last_search_query,
            "last_search_results": self.last_search_results,
            "conversation_history": self.conversation_history,
            "last_error": self.last_error,
            "last_interaction": self.last_interaction.isoformat(),
            "context_data": self.context_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """Create ConversationState from dictionary."""
        state = cls()
        
        if "phase" in data:
            state.phase = ConversationPhase(data["phase"])
        
        if "current_intent" in data and data["current_intent"]:
            state.current_intent = IntentType(data["current_intent"])
        
        if "draft_email" in data and data["draft_email"]:
            state.draft_email = EmailDraft.from_dict(data["draft_email"])
        
        state.current_email_id = data.get("current_email_id")
        state.last_search_query = data.get("last_search_query")
        state.last_search_results = data.get("last_search_results", [])
        state.conversation_history = data.get("conversation_history", [])
        state.last_error = data.get("last_error")
        
        if "last_interaction" in data:
            state.last_interaction = datetime.fromisoformat(data["last_interaction"])
        
        state.context_data = data.get("context_data", {})
        
        return state