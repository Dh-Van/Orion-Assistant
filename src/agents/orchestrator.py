"""
Agent Orchestrator - Coordinates between voice interface and conversation management.
This is the main entry point that connects Pipecat to our email agent logic.
"""

import asyncio
from typing import Optional, Dict, Any
from loguru import logger

from pipecat.frames.frames import (
    Frame, TextFrame, TranscriptionFrame, EndFrame,
    TTSSpeakFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    SystemFrame, ErrorFrame
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.transports.base_transport import BaseTransport

from .conversation_manager import ConversationManager
from ..services.intent_recognition import IntentRecognitionService
from ..services.email_service import EmailService
from ..voice.voice_interface import VoiceInterface
from ..models.conversation_state import ConversationPhase


class EmailAgentProcessor(FrameProcessor):
    """
    Custom frame processor that handles email agent logic.
    Bridges between Pipecat frames and our conversation manager.
    """
    
    def __init__(
        self,
        conversation_manager: ConversationManager,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.conversation_manager = conversation_manager
        self._processing = False
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames from the pipeline."""
        await super().process_frame(frame, direction)
        
        # Handle transcription frames (user speech)
        if isinstance(frame, TranscriptionFrame):
            # Ignore interim transcriptions
            if hasattr(frame, 'is_final') and not frame.is_final:
                await self.push_frame(frame, direction)
                return
                
            # Avoid processing while already processing
            if self._processing:
                logger.debug("Already processing, skipping transcription")
                await self.push_frame(frame, direction)
                return
            
            try:
                self._processing = True
                user_text = frame.text.strip()
                
                if user_text:
                    logger.info(f"Processing user input: {user_text}")
                    
                    # Get response from conversation manager
                    response = await self.conversation_manager.process_user_input(user_text)
                    
                    # Create TTS frame for response
                    if response:
                        await self.push_frame(TTSSpeakFrame(response))
                        
            except Exception as e:
                logger.error(f"Error processing transcription: {e}")
                error_response = "I'm sorry, I encountered an error. Could you please repeat that?"
                await self.push_frame(TTSSpeakFrame(error_response))
                
            finally:
                self._processing = False
        
        # Pass through other frames
        else:
            await self.push_frame(frame, direction)


class AgentOrchestrator:
    """
    Main orchestrator that sets up and runs the email voice agent.
    Coordinates between Pipecat pipeline and business logic.
    """
    
    def __init__(
        self,
        transport: BaseTransport,
        voice_interface: VoiceInterface,
        conversation_manager: ConversationManager,
        enable_metrics: bool = False,
        enable_usage_metrics: bool = False
    ):
        """
        Initialize the orchestrator.
        
        Args:
            transport: Pipecat transport (WebRTC, WebSocket, etc.)
            voice_interface: Voice interface for STT/TTS
            conversation_manager: Conversation management logic
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
        
        logger.info("AgentOrchestrator initialized")
    
    def _build_pipeline(self) -> Pipeline:
        """Build the Pipecat pipeline."""
        # Get STT and TTS services from voice interface
        stt = self.voice_interface.get_stt_service()
        tts = self.voice_interface.get_tts_service()
        
        # Create email agent processor
        agent_processor = EmailAgentProcessor(
            conversation_manager=self.conversation_manager,
            name="email_agent"
        )
        
        # Build pipeline
        pipeline = Pipeline([
            self.transport.input(),      # Audio input from user
            stt,                         # Convert speech to text
            agent_processor,             # Process with our agent logic
            tts,                         # Convert response to speech
            self.transport.output()      # Send audio back to user
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
            
            # IMPORTANT: Unmute the bot when client connects
            try:
                # For Daily transport, we need to unmute
                if hasattr(transport, 'client'):
                    # Access the Daily client
                    daily_client = transport.client
                    
                    # Update local participant (bot) to unmute audio
                    if hasattr(daily_client, 'update_inputs'):
                        await daily_client.update_inputs({
                            "microphone": True,
                            "camera": False
                        })
                        logger.info("Bot microphone unmuted")
                    
                    # Alternative method for some Daily SDK versions
                    if hasattr(daily_client, 'set_local_audio'):
                        daily_client.set_local_audio(True)
                        logger.info("Bot audio enabled via set_local_audio")
                        
                    # Also try updating participant
                    if hasattr(daily_client, 'update_participant'):
                        await daily_client.update_participant('local', {
                            'setAudio': True
                        })
                        logger.info("Bot audio enabled via update_participant")
                        
            except Exception as e:
                logger.error(f"Error unmuting bot: {e}")
            
            # Send welcome message
            welcome_message = (
                "Hello! I'm your email assistant. I can help you send emails, "
                "read your inbox, or search for specific messages. "
                "How can I help you today?"
            )
            await self.task.queue_frame(TTSSpeakFrame(welcome_message))
        
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
            """Handle user started speaking (for interruption)."""
            logger.debug("User started speaking")
            # Could implement interruption logic here
        
        @self.transport.event_handler("on_user_stopped_speaking")
        async def on_user_stopped_speaking(transport):
            """Handle user stopped speaking."""
            logger.debug("User stopped speaking")
        
        @self.transport.event_handler("on_participant_updated")
        async def on_participant_updated(transport, participant):
            """Handle participant updates - check audio state."""
            logger.debug(f"Participant updated: {participant}")
            
            # Log audio state for debugging
            if 'audio' in participant:
                logger.info(f"Participant audio state: {participant['audio']}")
    
    async def run(self):
        """Run the agent orchestrator."""
        if not self.task:
            await self.setup()
        
        try:
            logger.info("Starting email voice agent...")
            
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
    """Factory for creating agent orchestrators with different configurations."""
    
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
        intent_service = IntentRecognitionService()
        email_service = EmailService()
        
        # Create conversation manager
        conversation_manager = ConversationManager(
            intent_service=intent_service,
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