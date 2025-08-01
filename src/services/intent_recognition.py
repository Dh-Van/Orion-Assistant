"""
Intent Recognition Service - Uses AI to understand user intentions.
"""

import re
from typing import Optional, Dict, Any, List
from loguru import logger

from ..clients.gemini import GeminiClient
from ..models.intent_models import UserIntent, IntentType, IntentClassification
from ..models.conversation_state import ConversationState, ConversationPhase


class IntentRecognitionService:
    """Service for recognizing user intents from natural language."""
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """
        Initialize intent recognition service.
        
        Args:
            gemini_client: Optional Gemini client instance
        """
        self.gemini_client = gemini_client or GeminiClient()
        
        # Intent keywords for fallback detection - more strict patterns
        self.intent_patterns = {
            IntentType.SEND_EMAIL: [
                r'\b(?:send|write|compose)\s+(?:an?\s+)?email\b',
                r'\bemail\s+(?:to\s+)?\w+',
                r'\b(?:send|write)\s+(?:a\s+)?message\b'
            ],
            IntentType.READ_EMAIL: [
                r'\b(?:read|check|show)\s+(?:my\s+)?(?:email|inbox|messages)\b',
                r'\b(?:any|new)\s+(?:email|messages)\b',
                r'\bwhat\'?s?\s+in\s+my\s+inbox\b'
            ],
            IntentType.SEARCH_EMAIL: [
                r'\b(?:search|find|look)\s+(?:for\s+)?.+',
                r'\bwhere\s+(?:is|are)\s+.+\s+email'
            ],
            IntentType.REPLY_EMAIL: [
                r'\breply\s+(?:to\s+)?(?:this|that|the)?\s*email\b',
                r'\brespond\s+to\s+(?:this|that|the)?\s*email\b'
            ],
            IntentType.CONFIRM: [
                r'^(?:yes|yeah|yep|sure|correct|right|confirm|send it|go ahead|ok|okay)[\s\.!]*$'
            ],
            IntentType.CANCEL: [
                r'^(?:no|nope|cancel|stop|nevermind|forget it|abort)[\s\.!]*$'
            ],
            IntentType.HELP: [
                r'\bhelp\b',
                r'\bwhat can you do\b',
                r'\b(?:show|list)\s+commands\b'
            ]
        }
        
        logger.info("IntentRecognitionService initialized")
    
    async def recognize_intent(
        self,
        text: str,
        context: Optional[ConversationState] = None
    ) -> UserIntent:
        """
        Recognize user intent from text.
        
        Args:
            text: User's spoken text
            context: Current conversation context
            
        Returns:
            UserIntent with type and extracted entities
        """
        try:
            # Try AI intent recognition first
            intent_data = await self._ai_intent_recognition(text, context)
            
            if intent_data and intent_data.confidence > 0.7:  # Only use AI if confident
                return UserIntent(
                    type=intent_data.intent,
                    confidence=intent_data.confidence,
                    entities=intent_data.entities,
                    original_text=text
                )
            
            # Fallback to pattern-based recognition
            return self._pattern_intent_recognition(text, context)
            
        except Exception as e:
            logger.error(f"Error recognizing intent: {e}")
            # If all else fails, try to be helpful based on context
            if context and context.phase == ConversationPhase.COLLECTING_INFO:
                return self._context_based_intent(text, context)
            
            return UserIntent(
                type=IntentType.UNCLEAR,
                confidence=0.0,
                original_text=text
            )
    
    async def _ai_intent_recognition(
        self,
        text: str,
        context: Optional[ConversationState]
    ) -> Optional[IntentClassification]:
        """Use AI to recognize intent."""
        try:
            # Build context prompt
            context_info = ""
            if context:
                if context.phase == ConversationPhase.COLLECTING_INFO:
                    context_info = f"Currently collecting information for {context.current_intent.value if context.current_intent else 'unknown'} intent. "
                    if context.draft_email:
                        context_info += f"Draft email has: recipient={bool(context.draft_email.recipient)}, subject={bool(context.draft_email.subject)}, body={bool(context.draft_email.body)}. "
                elif context.phase == ConversationPhase.WAITING_CONFIRMATION:
                    context_info = "Waiting for user confirmation. "
                
                # Add recent conversation
                if context.conversation_history:
                    recent = context.conversation_history[-4:]  # Last 2 exchanges
                    context_info += "Recent conversation: " + " ".join([f"{msg['role']}: {msg['content']}" for msg in recent])
            
            prompt = f"""
            Analyze the user's intent from their message.
            
            User message: "{text}"
            
            Context: {context_info if context_info else "Starting new conversation"}
            
            Classify the intent and extract relevant entities.
            
            Possible intents:
            - SEND_EMAIL: User wants to send/compose/write an email
            - READ_EMAIL: User wants to read/check their emails
            - SEARCH_EMAIL: User wants to search/find specific emails
            - REPLY_EMAIL: User wants to reply to an email
            - CONFIRM: User is confirming something (yes, sure, correct)
            - CANCEL: User wants to cancel/stop current action
            - HELP: User needs help or wants to know capabilities
            - UNCLEAR: Cannot determine clear intent
            
            For SEND_EMAIL, extract:
            - recipient: email address or name
            - subject: email subject
            - body: email content
            
            For SEARCH_EMAIL, extract:
            - query: what to search for
            - field: where to search (subject, body, from, all)
            
            For READ_EMAIL, extract:
            - count: how many emails to read
            - filter: any specific filter (unread, today, etc.)
            
            Be conservative - only classify as CONFIRM or CANCEL if the message clearly indicates that intent.
            """
            
            # Get structured response
            result = self.gemini_client.generate_structured_output(
                prompt=prompt,
                response_model=IntentClassification
            )
            
            return result
            
        except Exception as e:
            logger.error(f"AI intent recognition failed: {e}")
            return None
    
    def _pattern_intent_recognition(
        self,
        text: str,
        context: Optional[ConversationState]
    ) -> UserIntent:
        """Pattern-based intent recognition."""
        text_lower = text.lower().strip()
        
        # Check each intent pattern
        for intent_type, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    # Extract entities based on intent
                    entities = self._extract_entities(text, intent_type)
                    
                    return UserIntent(
                        type=intent_type,
                        confidence=0.8,
                        entities=entities,
                        original_text=text
                    )
        
        # If no pattern matches, check context
        if context and context.phase == ConversationPhase.COLLECTING_INFO:
            return self._context_based_intent(text, context)
        
        return UserIntent(
            type=IntentType.UNCLEAR,
            confidence=0.0,
            original_text=text
        )
    
    def _context_based_intent(
        self,
        text: str,
        context: ConversationState
    ) -> UserIntent:
        """Determine intent based on conversation context."""
        # If we're collecting email info, assume they're providing it
        if context.current_intent == IntentType.SEND_EMAIL and context.draft_email:
            entities = {}
            
            # Determine what we're waiting for
            if not context.draft_email.recipient:
                entities['recipient'] = text.strip()
            elif not context.draft_email.subject:
                entities['subject'] = text.strip()
            elif not context.draft_email.body:
                entities['body'] = text.strip()
            
            return UserIntent(
                type=IntentType.SEND_EMAIL,
                confidence=0.7,
                entities=entities,
                original_text=text
            )
        
        # Default to unclear
        return UserIntent(
            type=IntentType.UNCLEAR,
            confidence=0.0,
            original_text=text
        )
    
    def _extract_entities(self, text: str, intent_type: IntentType) -> Dict[str, Any]:
        """Extract entities based on intent type."""
        entities = {}
        
        if intent_type == IntentType.SEND_EMAIL:
            entities = self._extract_email_entities(text)
        elif intent_type == IntentType.SEARCH_EMAIL:
            entities = self._extract_search_entities(text)
        elif intent_type == IntentType.READ_EMAIL:
            entities = self._extract_read_entities(text)
        
        return entities
    
    def _extract_email_entities(self, text: str) -> Dict[str, Any]:
        """Extract email-related entities."""
        entities = {}
        text_lower = text.lower()
        
        # Extract email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        if emails:
            entities['recipient'] = emails[0]
        
        # Extract "to <name>" pattern
        to_pattern = r'to\s+(\w+(?:\s+\w+)?)'
        to_match = re.search(to_pattern, text_lower)
        if to_match and 'recipient' not in entities:
            recipient = to_match.group(1).strip()
            # Don't treat common words as recipients
            if recipient not in ['email', 'message', 'mail']:
                entities['recipient'] = recipient
        
        # Extract subject after "subject:" or "about:"
        subject_pattern = r'(?:subject|about)[:\s]+(.+?)(?:\.|$)'
        subject_match = re.search(subject_pattern, text_lower)
        if subject_match:
            entities['subject'] = subject_match.group(1).strip()
        
        return entities
    
    def _extract_search_entities(self, text: str) -> Dict[str, Any]:
        """Extract search-related entities."""
        entities = {}
        text_lower = text.lower()
        
        # Remove "search for" or "find" to get query
        search_pattern = r'(?:search for|find|look for|where is|where are)\s+(.+)'
        match = re.search(search_pattern, text_lower)
        if match:
            entities['query'] = match.group(1).strip()
        
        # Determine search field
        if "subject" in text_lower:
            entities['field'] = "subject"
        elif "from" in text_lower:
            entities['field'] = "from"
        elif "body" in text_lower:
            entities['field'] = "body"
        else:
            entities['field'] = "all"
        
        return entities
    
    def _extract_read_entities(self, text: str) -> Dict[str, Any]:
        """Extract read email entities."""
        entities = {}
        text_lower = text.lower()
        
        # Extract count
        number_pattern = r'\b(\d+|one|two|three|four|five)\b'
        match = re.search(number_pattern, text_lower)
        if match:
            number_word = match.group(1)
            word_to_num = {
                'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5
            }
            entities['count'] = word_to_num.get(number_word, int(number_word) if number_word.isdigit() else 3)
        
        # Check for filters
        if "unread" in text_lower:
            entities['filter'] = "unread"
        elif "today" in text_lower:
            entities['filter'] = "today"
        
        return entities