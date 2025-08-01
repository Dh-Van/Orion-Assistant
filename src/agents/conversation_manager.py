"""
Conversation Manager for handling multi-turn email interactions.
Maintains conversation state and routes intents to appropriate handlers.
"""

from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from ..models.conversation_state import ConversationState, ConversationPhase
from ..models.intent_models import UserIntent, IntentType
from ..models.email_models import EmailRequest, EmailDraft
from ..services.intent_recognition import IntentRecognitionService
from ..services.email_service import EmailService


class ConversationManager:
    """Manages conversation flow and state for email voice interactions."""
    
    def __init__(
        self,
        intent_service: IntentRecognitionService,
        email_service: EmailService
    ):
        """
        Initialize conversation manager.
        
        Args:
            intent_service: Service for recognizing user intents
            email_service: Service for email operations
        """
        self.intent_service = intent_service
        self.email_service = email_service
        self.state = ConversationState()
        
        # Intent handlers mapping
        self.intent_handlers: Dict[IntentType, Callable] = {
            IntentType.SEND_EMAIL: self._handle_send_email,
            IntentType.READ_EMAIL: self._handle_read_email,
            IntentType.SEARCH_EMAIL: self._handle_search_email,
            IntentType.REPLY_EMAIL: self._handle_reply_email,
            IntentType.CONFIRM: self._handle_confirmation,
            IntentType.CANCEL: self._handle_cancel,
            IntentType.HELP: self._handle_help,
            IntentType.UNCLEAR: self._handle_unclear
        }
        
        logger.info("ConversationManager initialized")
    
    async def process_user_input(self, text: str) -> str:
        """
        Process user input and return appropriate response.
        
        Args:
            text: User's spoken text
            
        Returns:
            Response text to be spoken
        """
        try:
            # Add to conversation history
            self.state.add_message("user", text)
            
            # Recognize intent
            intent = await self.intent_service.recognize_intent(
                text, 
                context=self.state
            )
            
            logger.info(f"Recognized intent: {intent.type.value}")
            
            # Handle based on current phase
            if self.state.phase == ConversationPhase.WAITING_CONFIRMATION:
                return await self._handle_confirmation_phase(text, intent)
            
            # Route to appropriate handler
            handler = self.intent_handlers.get(intent.type, self._handle_unclear)
            response = await handler(intent)
            
            # Add response to history
            self.state.add_message("assistant", response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing input: {e}")
            return "I'm sorry, I encountered an error. Could you please try again?"
    
    async def _handle_send_email(self, intent: UserIntent) -> str:
        """Handle send email intent."""
        self.state.phase = ConversationPhase.COLLECTING_INFO
        self.state.current_intent = IntentType.SEND_EMAIL
        
        # Check what information we have
        if not self.state.draft_email:
            self.state.draft_email = EmailDraft()
        
        # Extract any email info from the intent
        if intent.entities:
            if "recipient" in intent.entities:
                self.state.draft_email.recipient = intent.entities["recipient"]
            if "subject" in intent.entities:
                self.state.draft_email.subject = intent.entities["subject"]
            if "body" in intent.entities:
                self.state.draft_email.body = intent.entities["body"]
        
        # Determine what's missing
        missing = self._get_missing_email_fields()
        
        if missing:
            return self._ask_for_missing_field(missing[0])
        else:
            # We have all info, ask for confirmation
            self.state.phase = ConversationPhase.WAITING_CONFIRMATION
            return self._format_email_confirmation()
    
    async def _handle_read_email(self, intent: UserIntent) -> str:
        """Handle read email intent."""
        self.state.phase = ConversationPhase.PROCESSING
        self.state.current_intent = IntentType.READ_EMAIL
        
        # Get number of emails to read
        count = intent.entities.get("count", 3) if intent.entities else 3
        
        try:
            emails = await self.email_service.read_recent_emails(limit=count)
            
            if not emails:
                return "You don't have any new emails in your inbox."
            
            # Format response
            response = f"You have {len(emails)} recent email{'s' if len(emails) > 1 else ''}. "
            
            for i, email in enumerate(emails[:3], 1):  # Limit to 3 for voice
                response += f"Email {i}: From {email.sender_name}, subject: {email.subject}. "
            
            if len(emails) > 3:
                response += f"And {len(emails) - 3} more. "
            
            response += "Would you like me to read any of these in detail?"
            
            self.state.phase = ConversationPhase.IDLE
            return response
            
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            self.state.phase = ConversationPhase.IDLE
            return "I had trouble accessing your emails. Please try again later."
    
    async def _handle_search_email(self, intent: UserIntent) -> str:
        """Handle search email intent."""
        self.state.phase = ConversationPhase.PROCESSING
        self.state.current_intent = IntentType.SEARCH_EMAIL
        
        # Get search query
        query = intent.entities.get("query", "") if intent.entities else ""
        
        if not query:
            self.state.phase = ConversationPhase.COLLECTING_INFO
            return "What would you like to search for in your emails?"
        
        try:
            results = await self.email_service.search_emails(
                query=query,
                search_field=intent.entities.get("field", "all")
            )
            
            if not results:
                self.state.phase = ConversationPhase.IDLE
                return f"I couldn't find any emails matching '{query}'."
            
            # Format response
            response = f"I found {len(results)} email{'s' if len(results) > 1 else ''} matching '{query}'. "
            
            for i, email in enumerate(results[:2], 1):  # Limit to 2 for voice
                response += f"Result {i}: From {email.sender_name}, subject: {email.subject}. "
            
            if len(results) > 2:
                response += f"And {len(results) - 2} more results. "
            
            self.state.phase = ConversationPhase.IDLE
            return response
            
        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            self.state.phase = ConversationPhase.IDLE
            return "I had trouble searching your emails. Please try again."
    
    async def _handle_reply_email(self, intent: UserIntent) -> str:
        """Handle reply to email intent."""
        # This would be similar to send_email but with reply context
        return "Reply functionality is coming soon. For now, you can send a new email instead."
    
    async def _handle_confirmation(self, intent: UserIntent) -> str:
        """Handle confirmation intent."""
        if self.state.phase != ConversationPhase.WAITING_CONFIRMATION:
            return "I'm not sure what you're confirming. How can I help you?"
        
        if self.state.current_intent == IntentType.SEND_EMAIL and self.state.draft_email:
            # Send the email
            try:
                await self.email_service.send_email(
                    EmailRequest(
                        to=self.state.draft_email.recipient,
                        subject=self.state.draft_email.subject,
                        body=self.state.draft_email.body
                    )
                )
                
                # Reset state
                self.state.reset()
                return f"Great! I've sent your email to {self.state.draft_email.recipient}."
                
            except Exception as e:
                logger.error(f"Error sending email: {e}")
                self.state.phase = ConversationPhase.IDLE
                return "I encountered an error sending the email. Please try again."
        
        return "I'm not sure what to confirm. How can I help you?"
    
    async def _handle_cancel(self, intent: UserIntent) -> str:
        """Handle cancel intent."""
        if self.state.phase == ConversationPhase.IDLE:
            return "There's nothing to cancel. How can I help you?"
        
        # Reset state
        previous_intent = self.state.current_intent
        self.state.reset()
        
        return f"Okay, I've cancelled the {previous_intent.value if previous_intent else 'current operation'}. What would you like to do instead?"
    
    async def _handle_help(self, intent: UserIntent) -> str:
        """Handle help intent."""
        return (
            "I can help you with your emails! You can ask me to: "
            "Send an email by saying 'Send an email to someone'. "
            "Read your recent emails by saying 'Read my emails'. "
            "Or search for specific emails by saying 'Search for' followed by what you're looking for. "
            "What would you like to do?"
        )
    
    async def _handle_unclear(self, intent: UserIntent) -> str:
        """Handle unclear intent."""
        context_hint = ""
        
        if self.state.phase == ConversationPhase.COLLECTING_INFO:
            if self.state.current_intent == IntentType.SEND_EMAIL:
                missing = self._get_missing_email_fields()
                if missing:
                    return self._ask_for_missing_field(missing[0])
        
        return "I didn't quite understand that. Could you please rephrase? You can say 'help' to hear what I can do."
    
    async def _handle_confirmation_phase(self, text: str, intent: UserIntent) -> str:
        """Handle input during confirmation phase."""
        # Check for yes/no in the raw text
        text_lower = text.lower()
        
        if any(word in text_lower for word in ["yes", "yeah", "yep", "sure", "correct", "right", "send it"]):
            return await self._handle_confirmation(intent)
        elif any(word in text_lower for word in ["no", "nope", "cancel", "stop", "wait"]):
            self.state.phase = ConversationPhase.COLLECTING_INFO
            return "Okay, what would you like to change?"
        else:
            # Maybe they're providing a correction
            if self.state.current_intent == IntentType.SEND_EMAIL:
                # Try to extract what they want to change
                return await self._handle_email_correction(text, intent)
            
        return "Please say 'yes' to confirm or 'no' to make changes."
    
    async def _handle_email_correction(self, text: str, intent: UserIntent) -> str:
        """Handle corrections to email draft."""
        # This would analyze what field they're trying to correct
        # For now, just re-enter collection mode
        self.state.phase = ConversationPhase.COLLECTING_INFO
        return "What would you like to change? The recipient, subject, or message?"
    
    def _get_missing_email_fields(self) -> List[str]:
        """Get list of missing email fields."""
        missing = []
        if not self.state.draft_email:
            return ["recipient", "subject", "body"]
        
        if not self.state.draft_email.recipient:
            missing.append("recipient")
        if not self.state.draft_email.subject:
            missing.append("subject")
        if not self.state.draft_email.body:
            missing.append("body")
        
        return missing
    
    def _ask_for_missing_field(self, field: str) -> str:
        """Generate question for missing field."""
        questions = {
            "recipient": "Who would you like to send this email to?",
            "subject": "What's the subject of your email?",
            "body": "What would you like to say in the email?"
        }
        return questions.get(field, f"What's the {field}?")
    
    def _format_email_confirmation(self) -> str:
        """Format email for confirmation."""
        if not self.state.draft_email:
            return "I don't have any email to confirm."
        
        return (
            f"I'm ready to send an email to {self.state.draft_email.recipient} "
            f"with the subject '{self.state.draft_email.subject}'. "
            f"The message says: {self.state.draft_email.body}. "
            "Should I send it?"
        )
    
    def reset_conversation(self):
        """Reset conversation state."""
        self.state.reset()
        logger.info("Conversation state reset")