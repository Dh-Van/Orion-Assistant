"""
Bot implementation and management for the Pipecat Email Agent.
"""

import asyncio
import subprocess
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import aiohttp
from loguru import logger

from pipecat.frames.frames import LLMMessagesFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.google.stt import GoogleSTTService
from pipecat.services.google.tts import GoogleTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.services.daily import DailyTransport, DailyParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from config import config
from clients.nylas_client import NylasClient


@dataclass
class BotInstance:
    """Represents an active bot instance."""
    room_name: str
    room_url: str
    task: Optional[PipelineTask] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class EmailFunctionHandler:
    """Handles email-related function calls."""
    
    def __init__(self, nylas_client: NylasClient):
        self.nylas_client = nylas_client
    
    async def send_email(self, params: FunctionCallParams):
        """Handle send_email function calls."""
        try:
            to = params.arguments.get("to")
            subject = params.arguments.get("subject")
            body = params.arguments.get("body")
            
            result = self.nylas_client.send_email(to, subject, body)
            
            if result:
                await params.result_callback("Email sent successfully!")
            else:
                await params.result_callback("Failed to send email.")
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            await params.result_callback(f"Error sending email: {str(e)}")
    
    async def read_new_emails(self, params: FunctionCallParams):
        """Handle read_new_emails function calls."""
        try:
            num_emails = params.arguments.get("num_emails", 100)
            
            emails = self.nylas_client.read_emails(num_emails)
            
            if emails:
                summary = f"You have {len(emails)} emails. "
                for i, email in enumerate(emails[:5]):
                    summary += f"Email {i+1}: {email}. "
                if len(emails) > 5:
                    summary += f"And {len(emails) - 5} more emails."
                await params.result_callback(summary)
            else:
                await params.result_callback("No new emails found.")
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            await params.result_callback(f"Error reading emails: {str(e)}")
    
    async def query_emails(self, params: FunctionCallParams):
        """Handle query_emails function calls."""
        try:
            query = params.arguments.get("query")
            query_key = params.arguments.get("query_key", "body")
            
            results = self.nylas_client.search_emails_with_vector_db(query, query_key, num_results=5)
            
            if results:
                summary = f"Found {len(results)} matching emails. "
                for i, (doc, score) in enumerate(results[:3]):
                    email_info = doc.metadata
                    summary += f"Result {i+1}: From {email_info.get('senders', 'Unknown')}, Subject: {email_info.get('subject', 'No subject')}. "
                await params.result_callback(summary)
            else:
                await params.result_callback("No emails matching your query were found.")
        except Exception as e:
            logger.error(f"Error querying emails: {e}")
            await params.result_callback(f"Error querying emails: {str(e)}")


class BotManager:
    """Manages bot instances and Daily room operations."""
    
    def __init__(self):
        self.active_bots: Dict[str, BotInstance] = {}
        self.daily_api_url = "https://api.daily.co/v1"
    
    async def create_room(self) -> Optional[Dict[str, Any]]:
        """Create a new Daily room."""
        if not config.daily_api_key:
            raise ValueError("Daily API key not configured")
        
        url = f"{self.daily_api_url}/rooms"
        headers = {
            "Authorization": f"Bearer {config.daily_api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    logger.error(f"Failed to create room: {response.status} - {error}")
                    return None
    
    async def create_token(self, room_name: str, is_owner: bool = True) -> Optional[str]:
        """Create a meeting token for a room."""
        if not config.daily_api_key:
            raise ValueError("Daily API key not configured")
        
        url = f"{self.daily_api_url}/meeting-tokens"
        headers = {
            "Authorization": f"Bearer {config.daily_api_key}",
            "Content-Type": "application/json"
        }
        
        import time
        
        data = {
            "properties": {
                "room_name": room_name,
                "is_owner": is_owner,
                "exp": int(time.time()) + (60 * 60)  # 1 hour from now
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["token"]
                else:
                    error = await response.text()
                    logger.error(f"Failed to create token: {response.status} - {error}")
                    return None
    
    async def start_bot(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new bot instance."""
        room_url = request_data.get("room_url")
        
        # Create room if not provided
        if not room_url:
            room_data = await self.create_room()
            if not room_data:
                raise Exception("Failed to create room")
            room_url = room_data["url"]
            room_name = room_data["name"]
        else:
            room_name = room_url.split("/")[-1]
        
        # Check if bot already exists for this room
        if room_name in self.active_bots:
            raise Exception(f"Bot already active for room {room_name}")
        
        # Create tokens
        bot_token = await self.create_token(room_name, is_owner=True)
        client_token = await self.create_token(room_name, is_owner=False)
        
        if not bot_token or not client_token:
            raise Exception("Failed to create tokens")
        
        # Create bot instance
        bot_instance = BotInstance(room_name=room_name, room_url=room_url)
        self.active_bots[room_name] = bot_instance
        
        # Start bot in background
        asyncio.create_task(self._run_bot(bot_instance, bot_token, request_data))
        
        logger.info(f"Started bot for room: {room_name}")
        
        return {
            "room_url": room_url,
            "room_name": room_name,
            "token": client_token,
            "bot_name": config.bot_name
        }
    
    async def stop_bot(self, room_name: str):
        """Stop a bot instance."""
        if room_name not in self.active_bots:
            raise Exception(f"No active bot for room {room_name}")
        
        bot_instance = self.active_bots[room_name]
        
        # Cancel the task
        if bot_instance.task:
            await bot_instance.task.cancel()
        
        del self.active_bots[room_name]
        logger.info(f"Stopped bot for room: {room_name}")
    
    async def cleanup(self):
        """Clean up all active bots."""
        logger.info("Cleaning up active bots...")
        
        tasks = []
        for room_name in list(self.active_bots.keys()):
            tasks.append(self.stop_bot(room_name))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_active_bot_count(self) -> int:
        """Get the number of active bots."""
        return len(self.active_bots)
    
    async def _run_bot(self, bot_instance: BotInstance, token: str, request_data: Dict[str, Any]):
        """Run a bot instance."""
        try:
            # Initialize transport
            transport = DailyTransport(
                bot_instance.room_url,
                token,
                config.bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    vad_analyzer=SileroVADAnalyzer(),
                ),
            )
            
            # Initialize Google services
            # For STT and TTS, we need to handle credentials differently
            stt_kwargs = {
                "model": "chirp_2",
                "location": "us-central1",
                "credentials_path": "creds.json"
            }
            
            tts_kwargs = {
                "voice_name": "en-US-Chirp3-HD-Charon",
                "language_code": "en-US",
                "credentials_path": "creds.json"
            }
            
            # If we have credentials_info, use it; otherwise rely on GOOGLE_APPLICATION_CREDENTIALS
            # if config.google_credentials:
            #     stt_kwargs["credentials_info"] = config.google_credentials
            #     tts_kwargs["credentials_info"] = config.google_credentials
            
            stt = GoogleSTTService(**stt_kwargs)
            tts = GoogleTTSService(**tts_kwargs)
            
            # Initialize LLM
            llm = GoogleLLMService(
                api_key=config.google_api_key,
                model="gemini-1.5-flash"
            )
            
            # Initialize email handler
            nylas_client = NylasClient(config.nylas_grant_id)
            email_handler = EmailFunctionHandler(nylas_client)
            
            # Register functions
            llm.register_function("send_email", email_handler.send_email)
            llm.register_function("read_new_emails", email_handler.read_new_emails)
            llm.register_function("query_emails", email_handler.query_emails)
            
            # Define function schemas
            send_email_schema = FunctionSchema(
                name="send_email",
                description="Sends an email to one or more recipients",
                properties={
                    "to": {"type": "string", "description": "The recipient's email address"},
                    "subject": {"type": "string", "description": "The email subject"},
                    "body": {"type": "string", "description": "The email body content"}
                },
                required=["to", "subject", "body"]
            )
            
            read_emails_schema = FunctionSchema(
                name="read_new_emails",
                description="Reads and returns a summary of the user's new, unread emails",
                properties={
                    "num_emails": {"type": "integer", "description": "Number of emails to read (default: 100)"}
                },
                required=[]  # No required parameters
            )
            
            query_emails_schema = FunctionSchema(
                name="query_emails",
                description="Searches the user's mailbox for emails matching a specific query",
                properties={
                    "query": {"type": "string", "description": "The search query"},
                    "query_key": {"type": "string", "description": "The field to search in (e.g., 'body', 'subject')"}
                },
                required=["query", "query_key"]
            )
            
            tools = ToolsSchema(standard_tools=[
                send_email_schema,
                read_emails_schema,
                query_emails_schema
            ])
            
            # System prompt
            system_prompt = f"""You are {config.bot_name}, a helpful voice AI assistant that helps users manage their emails. 
You can:
1. Send emails to recipients
2. Read and summarize new emails
3. Search for specific emails based on queries

Be conversational and helpful. Keep your responses concise since they will be converted to speech.
When asked to perform email operations, use the available functions to help the user.
Your output will be converted to audio so don't include special characters in your answers."""
            
            # Initial messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Say hello."},
            ]
            
            # Create context using OpenAILLMContext (standard for all providers)
            context = OpenAILLMContext(messages, tools)
            context_aggregator = llm.create_context_aggregator(context)
            
            # Build pipeline
            pipeline = Pipeline([
                transport.input(),
                stt,
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                context_aggregator.assistant(),
            ])
            
            # Create task
            task = PipelineTask(
                pipeline,
                params=PipelineParams(
                    allow_interruptions=True,
                    enable_metrics=True,
                    enable_usage_metrics=True,
                ),
            )
            
            bot_instance.task = task
            
            # Event handlers
            @transport.event_handler("on_client_connected")
            async def on_client_connected(transport, client):
                logger.info(f"Client connected to room {bot_instance.room_name}: {client}")
                # The initial greeting will be triggered by the "Say hello." message in the context
                await task.queue_frames([context_aggregator.user().get_context_frame()])
            
            @transport.event_handler("on_client_disconnected")
            async def on_client_disconnected(transport, client):
                logger.info(f"Client disconnected from room {bot_instance.room_name}: {client}")
            
            # Run the pipeline
            runner = PipelineRunner()
            await runner.run(task)
            
        except Exception as e:
            logger.error(f"Error running bot for room {bot_instance.room_name}: {e}")
            raise
        finally:
            # Clean up
            if bot_instance.room_name in self.active_bots:
                del self.active_bots[bot_instance.room_name]