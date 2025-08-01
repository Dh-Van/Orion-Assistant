"""
Agent Tools - Define available functions the AI can call.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


# Tool parameter models
class SendEmailParams(BaseModel):
    """Parameters for sending an email."""
    recipient: str = Field(description="Email address or name of recipient")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body content")
    
class ReadEmailParams(BaseModel):
    """Parameters for reading emails."""
    count: int = Field(default=5, description="Number of emails to read")
    filter: Optional[Literal["all", "unread", "today", "important"]] = Field(
        default="all", 
        description="Filter for emails"
    )

class SearchEmailParams(BaseModel):
    """Parameters for searching emails."""
    query: str = Field(description="Search query")
    search_field: Literal["all", "subject", "body", "from", "to"] = Field(
        default="all",
        description="Field to search in"
    )
    limit: int = Field(default=5, description="Maximum results to return")

class ReplyEmailParams(BaseModel):
    """Parameters for replying to an email."""
    email_id: str = Field(description="ID of email to reply to")
    body: str = Field(description="Reply message content")
    reply_all: bool = Field(default=False, description="Whether to reply to all recipients")


# Tool definitions for the AI
TOOL_DEFINITIONS = [
    {
        "name": "send_email",
        "description": "Send an email to someone",
        "parameters": SendEmailParams.model_json_schema()
    },
    {
        "name": "read_emails", 
        "description": "Read recent emails from the inbox",
        "parameters": ReadEmailParams.model_json_schema()
    },
    {
        "name": "search_emails",
        "description": "Search for specific emails",
        "parameters": SearchEmailParams.model_json_schema()
    },
    {
        "name": "get_help",
        "description": "Get help on what the assistant can do",
        "parameters": {}
    }
]


class ToolCall(BaseModel):
    """Represents a tool call from the AI."""
    name: str
    arguments: Dict[str, Any]
    
class AIResponse(BaseModel):
    """AI response with optional tool calls."""
    message: str = Field(description="Response message to the user")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools to execute")
    needs_confirmation: bool = Field(default=False, description="Whether to ask for confirmation")
    collecting_info: bool = Field(default=False, description="Whether more info is needed")