"""
Agent Orchestrator using Pipecat's native function calling pattern.
This follows the standard Pipecat pipeline architecture.
"""

import asyncio
from typing import Optional
from loguru import logger

from pipecat.frames.frames import Frame, TTSSpeakFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.base_transport import BaseTransport
from pipecat.services.llm_service import FunctionCallParams

from .ai_conversation_manager import AIConversationManager
from ..services.email_service import EmailService
from ..voice.voice_interface import VoiceInterface


class AgentOrchestrator:
    """
    Main orchestrator that sets up and runs the email voice agent.
    Uses Pipecat's native function calling architecture.
    """
    
    def __init__(
        self,
        transport: BaseTransport,
        voice_interface: VoiceInterface,
        conversation_manager: AIConversationManager,
        enable_metrics: bool = False,
        enable_usage_metrics: bool = False
    ):
        """
        Initialize the orchestrator.
        
        Args:
            transport: Pipecat transport (WebRTC, WebSocket, etc.)
            voice_interface: Voice interface for STT/TTS
            conversation_manager: AI conversation management with function calling
            enable_metrics: Enable performance metrics
            enable_usage_metrics: Enable usage metrics
        """
        self.transport = transport
        self.voice_interface = voice_interface
        self.conversation_manager = conversation_manager
        self.enable_metrics = enable_metrics
        self.enable_usage_metrics = enable_usage_metrics
        
        self.pipeline: Optional[Pipeline] = None
        self.task: Optional[PipelineTask] = None
        
        logger.info("AgentOrchestrator initialized with Pipecat function calling")
    
    def _build_pipeline(self) -> Pipeline:
        """Build the Pipecat pipeline following the standard pattern."""
        # Get services
        stt = self.voice_interface.get_stt_service()
        tts = self.voice_interface.get_tts_service()
        llm = self.conversation_manager.get_llm_service()
        context_aggregator = self.conversation_manager.get_context_aggregator()
        
        # Build standard Pipecat pipeline
        pipeline = Pipeline([
            self.transport.input(),           # Audio/video input
            stt,                              # Speech to text
            context_aggregator.user(),        # User context aggregation
            llm,                              # LLM with function calling
            tts,                              # Text to speech
            self.transport.output(),          # Audio/video output
            context_aggregator.assistant(),   # Assistant context aggregation
        ])
        
        return pipeline
    
    async def setup(self):
        """Set up the orchestrator and pipeline."""
        try:
            # Build pipeline
            self.pipeline = self._build_pipeline()
            
            # Create pipeline task
            self.task = PipelineTask(
                self.pipeline,
                params=PipelineParams(
                    enable_metrics=self.enable_metrics,
                    enable_usage_metrics=self.enable_usage_metrics,
                    allow_interruptions=True
                )
            )
            
            # Set up transport event handlers
            self._setup_event_handlers()
            
            # Set up function call event handlers
            self._setup_function_call_handlers()
            
            logger.info("Orchestrator setup complete")
            
        except Exception as e:
            logger.error(f"Error setting up orchestrator: {e}")
            raise
    
    def _setup_event_handlers(self):
        """Set up event handlers for transport events."""
        
        @self.transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            """Handle client connection."""
            logger.info(f"Client connected: {client}")
            
            # Unmute bot audio for Daily transport
            try:
                if hasattr(transport, 'client'):
                    daily_client = transport.client
                    
                    if hasattr(daily_client, 'update_inputs'):
                        await daily_client.update_inputs({
                            "microphone": True,
                            "camera": False
                        })
                        logger.info("Bot microphone unmuted")
                    
                    if hasattr(daily_client, 'set_local_audio'):
                        daily_client.set_local_audio(True)
                        logger.info("Bot audio enabled")
                        
            except Exception as e:
                logger.error(f"Error unmuting bot: {e}")
            
            # Send welcome message
            welcome_frame = await self.conversation_manager.add_welcome_message()
            await self.task.queue_frame(welcome_frame)
            
            # Queue initial context to trigger greeting
            context_aggregator = self.conversation_manager.get_context_aggregator()
            await self.task.queue_frame(context_aggregator.user().get_context_frame())
        
        @self.transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            """Handle client disconnection."""
            logger.info(f"Client disconnected: {client}")
            
            # Clean up
            self.conversation_manager.reset_conversation()
            
            # Cancel the task
            if self.task:
                await self.task.cancel()
        
        @self.transport.event_handler("on_user_started_speaking")
        async def on_user_started_speaking(transport):
            """Handle user started speaking."""
            logger.debug("User started speaking")
        
        @self.transport.event_handler("on_user_stopped_speaking")
        async def on_user_stopped_speaking(transport):
            """Handle user stopped speaking."""
            logger.debug("User stopped speaking")
    
    def _setup_function_call_handlers(self):
        """Set up event handlers for function calls."""
        llm = self.conversation_manager.get_llm_service()
        
        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            """Handle when function calls start."""
            logger.info(f"Function calls started: {[fc.name for fc in function_calls]}")
            
            # Optionally provide feedback to user
            await self.task.queue_frame(
                TTSSpeakFrame("Let me handle that for you.")
            )
        
        @llm.event_handler("on_function_calls_finished")
        async def on_function_calls_finished(service, function_calls):
            """Handle when function calls finish."""
            logger.info(f"Function calls finished: {[fc.name for fc in function_calls]}")
    
    async def run(self):
        """Run the agent orchestrator."""
        if not self.task:
            await self.setup()
        
        try:
            logger.info("Starting Pipecat email voice agent...")
            
            # Ensure transport is ready
            if hasattr(self.transport, 'ensure_connected'):
                await self.transport.ensure_connected()
            
            # Run the pipeline
            runner = PipelineRunner()
            await runner.run(self.task)
            
        except Exception as e:
            logger.error(f"Error running orchestrator: {e}")
            raise
        finally:
            logger.info("Email voice agent stopped")
    
    async def stop(self):
        """Stop the orchestrator."""
        if self.task:
            await self.task.cancel()
        
        logger.info("Orchestrator stopped")


class AgentOrchestratorFactory:
    """Factory for creating agent orchestrators with Pipecat function calling."""
    
    @staticmethod
    def create_from_env(
        transport: BaseTransport,
        **kwargs
    ) -> AgentOrchestrator:
        """
        Create orchestrator from environment configuration.
        
        Args:
            transport: Pipecat transport to use
            **kwargs: Additional configuration options
            
        Returns:
            Configured AgentOrchestrator instance
        """
        # Create services
        email_service = EmailService()
        
        # Create AI conversation manager with Pipecat function calling
        conversation_manager = AIConversationManager(
            email_service=email_service
        )
        
        # Create voice interface
        voice_interface = VoiceInterface.create_from_env()
        
        # Create orchestrator
        return AgentOrchestrator(
            transport=transport,
            voice_interface=voice_interface,
            conversation_manager=conversation_manager,
            **kwargs
        )