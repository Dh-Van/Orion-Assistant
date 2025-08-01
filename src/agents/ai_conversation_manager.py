import os
from typing import Optional, List
from loguru import logger

from pipecat.frames.frames import TTSSpeakFrame
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

# Assuming these imports are correct for your project structure
from ..services.email_service import EmailService
from ..models.email_models import EmailRequest


class AIConversationManager:
    """AI-powered conversation manager using Pipecat's function calling."""

    def __init__(
        self,
        email_service: EmailService,
        google_api_key: Optional[str] = None
    ):
        """
        Initialize AI conversation manager.

        Args:
            email_service: Service for email operations
            google_api_key: Optional Google API key
        """
        self.email_service = email_service

        # Initialize Google LLM service with Pipecat
        api_key = google_api_key or os.getenv('GOOGLE_API_KEY')
        self.llm = GoogleLLMService(
            api_key=api_key,
            # FIX: Using a valid, current Gemini model name.
            model="gemini-1.5-flash-latest"
        )

        # Register function handlers
        self._register_functions()

        # Create initial context
        self.context = self._create_initial_context()
        self.context_aggregator = self.llm.create_context_aggregator(self.context)

        logger.info("AIConversationManager initialized with Pipecat function calling")

    def _register_functions(self):
        """Register all available functions with the LLM service."""

        # Register send_email function
        async def send_email_handler(params: FunctionCallParams):
            """Handle send email function calls."""
            try:
                logger.info(f"Sending email with params: {params.arguments}")
                recipient = params.arguments.get("recipient", "")
                subject = params.arguments.get("subject", "")
                body = params.arguments.get("body", "")

                if not all([recipient, subject, body]):
                    await params.result_callback({
                        "success": False,
                        "error": "Missing required fields: recipient, subject, or body"
                    })
                    return

                result = await self.email_service.send_email(
                    EmailRequest(to=recipient, subject=subject, body=body)
                )

                await params.result_callback({
                    "success": result.success,
                    "message": result.message,
                    "error": result.error
                })
            except Exception as e:
                logger.error(f"Error in send_email handler: {e}")
                await params.result_callback({"success": False, "error": str(e)})

        # Register read_emails function
        async def read_emails_handler(params: FunctionCallParams):
            """Handle read emails function calls."""
            try:
                count = params.arguments.get("count", 5)
                filter_type = params.arguments.get("filter", "all")
                unread_only = filter_type == "unread"
                emails = await self.email_service.read_recent_emails(
                    limit=count, unread_only=unread_only
                )

                email_list = [{
                    "from": email.sender_name,
                    "subject": email.subject,
                    "date": email.date_str,
                    "preview": email.body_preview[:100]
                } for email in emails]

                await params.result_callback({
                    "success": True,
                    "count": len(emails),
                    "emails": email_list
                })
            except Exception as e:
                logger.error(f"Error in read_emails handler: {e}")
                await params.result_callback({"success": False, "error": str(e)})

        # Register search_emails function
        async def search_emails_handler(params: FunctionCallParams):
            """Handle search emails function calls."""
            try:
                query = params.arguments.get("query", "")
                search_field = params.arguments.get("search_field", "all")
                limit = params.arguments.get("limit", 5)

                results = await self.email_service.search_emails(
                    query=query, search_field=search_field, limit=limit, use_ai=True
                )

                search_results = [{
                    "from": result.email_summary.sender_name,
                    "subject": result.email_summary.subject,
                    "date": result.email_summary.date_str,
                    "relevance": result.relevance_score
                } for result in results]

                await params.result_callback({
                    "success": True,
                    "count": len(results),
                    "results": search_results
                })
            except Exception as e:
                logger.error(f"Error in search_emails handler: {e}")
                await params.result_callback({"success": False, "error": str(e)})

        # Register all functions with the LLM service
        self.llm.register_function("send_email", send_email_handler)
        self.llm.register_function("read_emails", read_emails_handler)
        self.llm.register_function("search_emails", search_emails_handler)

    def _create_initial_context(self) -> OpenAILLMContext:
        """Create initial conversation context with tools."""
        send_email_schema = FunctionSchema(
            name="send_email",
            description="Send an email to someone",
            properties={
                "recipient": {"type": "string", "description": "Email address of the recipient"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body content"}
            },
            required=["recipient", "subject", "body"]
        )

        read_emails_schema = FunctionSchema(
            name="read_emails",
            description="Read recent emails from the inbox",
            properties={
                "count": {"type": "integer", "description": "Number of emails to read", "default": 5},
                "filter": {"type": "string", "description": "Filter type: all, unread, today", "enum": ["all", "unread", "today"], "default": "all"}
            },
            required=[]
        )

        search_emails_schema = FunctionSchema(
            name="search_emails",
            description="Search for specific emails",
            properties={
                "query": {"type": "string", "description": "Search query"},
                "search_field": {"type": "string", "description": "Field to search in", "enum": ["all", "subject", "body", "from", "to"], "default": "all"},
                "limit": {"type": "integer", "description": "Maximum results to return", "default": 5}
            },
            required=["query"]
        )
        
        # FIX 1: Create ToolsSchema by passing a list to the `standard_tools` argument.
        tools = ToolsSchema(
            standard_tools=[send_email_schema, read_emails_schema, search_emails_schema]
        )

        system_prompt = """You are an intelligent email assistant that helps users manage their emails through voice commands.
You have access to functions for sending, reading, and searching emails.
When users ask to perform an email operation, extract all necessary information, call the appropriate function, and provide a natural, voice-friendly response based on the results.
For sending emails, always confirm the details before sending and ask for any missing information.
Be conversational, helpful, and proactive."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": "Hello! I'm your email assistant. How can I help you today?"}
        ]

        # FIX 2: Pass the `tools` object directly, not `tools.to_dict()`.
        return OpenAILLMContext(messages, tools)

    def get_context_aggregator(self):
        """Get the context aggregator for pipeline integration."""
        return self.context_aggregator

    def get_llm_service(self):
        """Get the LLM service for pipeline integration."""
        return self.llm

    async def add_welcome_message(self):
        """Add a welcome message to start the conversation."""
        return TTSSpeakFrame(
            "Hello! I'm your AI email assistant. I can help you send emails, "
            "read your inbox, or search for specific messages. "
            "Just tell me what you'd like to do!"
        )

    def reset_conversation(self):
        """Reset conversation state."""
        self.context = self._create_initial_context()
        self.context_aggregator = self.llm.create_context_aggregator(self.context)
        logger.info("Conversation reset")