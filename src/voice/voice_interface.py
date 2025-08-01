"""
Voice Interface - Handles all Pipecat-specific voice components.
Provides abstraction for STT/TTS services and voice activity detection.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from loguru import logger

# Pipecat imports
from pipecat.services.google import GoogleSTTService, GoogleTTSService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADAnalyzer


class STTProvider(Enum):
    """Available STT providers."""
    DEEPGRAM = "deepgram"
    GOOGLE = "google"
    OPENAI = "openai"


class TTSProvider(Enum):
    """Available TTS providers."""
    GOOGLE = "google"


@dataclass
class VoiceConfig:
    """Configuration for voice interface."""
    # STT Configuration
    stt_provider: STTProvider = STTProvider.GOOGLE
    stt_language: str = "en-US"
    stt_model: Optional[str] = None
    
    # TTS Configuration
    tts_provider: TTSProvider = TTSProvider.GOOGLE
    tts_voice_id: Optional[str] = None
    tts_language: str = "en-US"
    tts_speed: float = 1.0
    
    # VAD Configuration
    enable_vad: bool = True
    vad_threshold: float = 0.5
    vad_min_speech_duration: float = 0.1
    vad_min_silence_duration: float = 0.3
    
    # Audio Configuration
    sample_rate: int = 16000
    channels: int = 1


class VoiceInterface:
    """
    Manages voice components for the email agent.
    Provides abstraction over Pipecat's STT/TTS services.
    """
    
    def __init__(self, config: VoiceConfig):
        """
        Initialize voice interface.
        
        Args:
            config: Voice configuration
        """
        self.config = config
        self._stt_service: Optional[STTService] = None
        self._tts_service: Optional[TTSService] = None
        self._vad_analyzer: Optional[VADAnalyzer] = None
        
        # Initialize services
        self._initialize_services()
        
        logger.info(f"VoiceInterface initialized with STT: {config.stt_provider.value}, TTS: {config.tts_provider.value}")
    
    def _initialize_services(self):
        """Initialize STT, TTS, and VAD services based on configuration."""
        # Initialize STT
        self._stt_service = self._create_stt_service()
        
        # Initialize TTS
        self._tts_service = self._create_tts_service()
        
        # Initialize VAD if enabled
        if self.config.enable_vad:
            self._vad_analyzer = SileroVADAnalyzer()
    
    def _create_stt_service(self) -> STTService:
        """Create STT service based on provider."""        
        if self.config.stt_provider == STTProvider.GOOGLE:
            credentials_b64 = os.getenv('GOOGLE_CREDENTIALS')
            if not credentials_b64:
                raise ValueError("GOOGLE_CREDENTIALS not set")
            
            # Decode base64 to get JSON string
            import base64
            credentials_json = base64.b64decode(credentials_b64).decode('utf-8')
            
            return GoogleSTTService(
                credentials=credentials_json,
                params=GoogleSTTService.InputParams(
                    language=self.config.stt_language,
                    model=self.config.stt_model or "latest_long",
                    interim_results=True,
                    punctuation=True
                )
            )
            
    def _create_tts_service(self) -> TTSService:
        """Create TTS service based on provider."""        
        if self.config.tts_provider == TTSProvider.GOOGLE:
            credentials_b64 = os.getenv('GOOGLE_CREDENTIALS')
            if not credentials_b64:
                raise ValueError("GOOGLE_CREDENTIALS not set")
            
            # Decode base64 to get JSON string
            import base64
            credentials_json = base64.b64decode(credentials_b64).decode('utf-8')
            
            return GoogleTTSService(
                credentials=credentials_json,
                params=GoogleTTSService.InputParams(
                    voice_name=self.config.tts_voice_id or "en-US-Journey-D",
                    language_code=self.config.tts_language,
                    speaking_rate=self.config.tts_speed,
                    pitch=0.0,
                    volume_gain_db=0.0,
                    sample_rate_hz=self.config.sample_rate
                )
            )
        
        else:
            raise ValueError(f"Unsupported TTS provider: {self.config.tts_provider}")
    
    def get_stt_service(self) -> STTService:
        """Get the configured STT service."""
        if not self._stt_service:
            raise RuntimeError("STT service not initialized")
        return self._stt_service
    
    def get_tts_service(self) -> TTSService:
        """Get the configured TTS service."""
        if not self._tts_service:
            raise RuntimeError("TTS service not initialized")
        return self._tts_service
    
    def get_vad_analyzer(self) -> Optional[VADAnalyzer]:
        """Get the VAD analyzer if enabled."""
        return self._vad_analyzer
    
    def update_tts_voice(self, voice_id: str):
        """
        Update TTS voice dynamically.
        
        Args:
            voice_id: New voice ID
        """
        self.config.tts_voice_id = voice_id
        
        # Recreate TTS service with new voice
        old_service = self._tts_service
        try:
            self._tts_service = self._create_tts_service()
            logger.info(f"Updated TTS voice to: {voice_id}")
        except Exception as e:
            # Restore old service on error
            self._tts_service = old_service
            logger.error(f"Failed to update TTS voice: {e}")
            raise
    
    def update_tts_speed(self, speed: float):
        """
        Update TTS speaking speed.
        
        Args:
            speed: Speaking speed (0.5-2.0)
        """
        if not 0.5 <= speed <= 2.0:
            raise ValueError("Speed must be between 0.5 and 2.0")
        
        self.config.tts_speed = speed
        
        # Some services support dynamic speed updates
        if hasattr(self._tts_service, 'set_speed'):
            self._tts_service.set_speed(speed)
        else:
            # Otherwise recreate service
            self._tts_service = self._create_tts_service()
        
        logger.info(f"Updated TTS speed to: {speed}")
    
    @classmethod
    def create_from_env(cls, **overrides) -> 'VoiceInterface':
        """
        Create VoiceInterface from environment variables.
        
        Environment variables:
        - VOICE_STT_PROVIDER: STT provider name
        - VOICE_TTS_PROVIDER: TTS provider name
        - VOICE_TTS_VOICE_ID: TTS voice ID
        - VOICE_LANGUAGE: Language code
        - VOICE_ENABLE_VAD: Enable VAD (true/false)
        
        Args:
            **overrides: Override any config values
            
        Returns:
            Configured VoiceInterface
        """
        # Build config from environment
        config_dict = {
            'stt_provider': STTProvider(os.getenv('VOICE_STT_PROVIDER', 'google')),
            'tts_provider': TTSProvider(os.getenv('VOICE_TTS_PROVIDER', 'google')),
            'tts_voice_id': os.getenv('VOICE_TTS_VOICE_ID'),
            'stt_language': os.getenv('VOICE_LANGUAGE', 'en-US-Journey-D'),
            'tts_language': os.getenv('VOICE_LANGUAGE', 'en-US'),
            'enable_vad': os.getenv('VOICE_ENABLE_VAD', 'true').lower() == 'true'
        }
        
        # Apply overrides
        config_dict.update(overrides)
        
        # Create config
        config = VoiceConfig(**config_dict)
        
        return cls(config)
    
    def get_supported_voices(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Get list of supported voices for each TTS provider.
        
        Returns:
            Dict mapping provider to list of voice options
        """
        voices = {
            TTSProvider.DEEPGRAM.value: [
                {"id": "nova", "name": "Nova", "description": "Natural female voice"},
                {"id": "stella", "name": "Stella", "description": "Expressive female voice"},
                {"id": "athena", "name": "Athena", "description": "Professional female voice"},
                {"id": "hera", "name": "Hera", "description": "Warm female voice"},
                {"id": "orion", "name": "Orion", "description": "Professional male voice"},
                {"id": "perseus", "name": "Perseus", "description": "Casual male voice"},
                {"id": "angus", "name": "Angus", "description": "Natural male voice"},
                {"id": "helios", "name": "Helios", "description": "Expressive male voice"}
            ],
            TTSProvider.GOOGLE.value: [
                {"id": "en-US-Journey-D", "name": "Journey D", "description": "Male voice"},
                {"id": "en-US-Journey-F", "name": "Journey F", "description": "Female voice"},
                {"id": "en-US-Polyglot-1", "name": "Polyglot 1", "description": "Male multilingual"},
                {"id": "en-US-Studio-M", "name": "Studio M", "description": "Male studio voice"},
                {"id": "en-US-Studio-O", "name": "Studio O", "description": "Female studio voice"}
            ],
            TTSProvider.CARTESIA.value: [
                {"id": "79a125e8-cd45-4c13-8a67-188112f4dd22", "name": "British Lady", "description": "Professional British female"},
                {"id": "a0e99841-438c-4a64-b679-ae501e7d6091", "name": "Confident British Man", "description": "Professional British male"},
                {"id": "156fb8d2-335b-4950-9cb3-a2d33befec77", "name": "Calm Woman", "description": "Soothing female voice"},
                {"id": "98a34ef2-2140-4c28-9c71-663dc4dd7022", "name": "Friendly Man", "description": "Warm male voice"}
            ],
            TTSProvider.ELEVENLABS.value: [
                {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "description": "American female"},
                {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "description": "American female"},
                {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi", "description": "American female"},
                {"id": "CYw3kZ02Hs0563khs1Fj", "name": "Dave", "description": "British male"},
                {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin", "description": "Irish male"},
                {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "description": "American female"},
                {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "description": "American male"},
                {"id": "GBv7mTt0atIp3Br8iCZE", "name": "Thomas", "description": "American male"}
            ]
        }
        
        return voices
    
    def get_audio_config(self) -> Dict[str, Any]:
        """
        Get audio configuration for pipeline setup.
        
        Returns:
            Dict with audio configuration
        """
        return {
            "sample_rate": self.config.sample_rate,
            "channels": self.config.channels,
            "vad_enabled": self.config.enable_vad,
            "vad_analyzer": self._vad_analyzer
        }