"""
Configuration management for the Pipecat Email Agent.
Designed for easy environment variable injection in Cloud Run.
"""

import os
import json
import base64
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from loguru import logger

# Load .env file only in development
if os.getenv("ENVIRONMENT") != "production":
    load_dotenv(override=True)

class Config:
    """Centralized configuration management."""
    
    def __init__(self):
        # Server Configuration
        self.port = int(os.getenv("PORT", "8080"))
        self.host = os.getenv("HOST", "0.0.0.0")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.bot_name = os.getenv("BOT_NAME", "Orion")
        self.enable_health_check = os.getenv("ENABLE_HEALTH_CHECK", "true").lower() == "true"
        
        # Daily Configuration
        self.daily_api_key = os.getenv("DAILY_API_KEY")
        if not self.daily_api_key:
            logger.warning("DAILY_API_KEY not set - WebRTC features will not work")
        
        # Google Configuration
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if not self.google_api_key:
            logger.warning("GOOGLE_API_KEY not set - Google services will not work")
        
        # Parse Google credentials
        self.google_credentials = self._parse_google_credentials()
        
        # Nylas Configuration
        self.nylas_api_key = os.getenv("NYLAS_API_KEY")
        self.nylas_api_uri = os.getenv("NYLAS_API_URI", "https://api.nylas.com")
        self.nylas_grant_id = os.getenv("NYLAS_GRANT_ID", "")
        
        # Validate required configurations
        self._validate_config()
    
    def _parse_google_credentials(self) -> Optional[Dict[str, Any]]:
        """Parse Google credentials from base64 encoded string."""
        creds_b64 = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_b64:
            logger.warning("GOOGLE_CREDENTIALS not set - using API key only")
            return None
        
        try:
            return json.loads(base64.b64decode(creds_b64))
        except Exception as e:
            logger.error(f"Failed to parse GOOGLE_CREDENTIALS: {e}")
            return None
    
    def _validate_config(self):
        """Validate required configuration values."""
        required_vars = []
        
        if self.enable_health_check:
            logger.info("Health check endpoint enabled")
        
        # In production, we want to ensure all services are configured
        if os.getenv("ENVIRONMENT") == "production":
            required_vars.extend([
                ("DAILY_API_KEY", self.daily_api_key),
                ("GOOGLE_API_KEY", self.google_api_key),
                ("NYLAS_API_KEY", self.nylas_api_key),
                ("NYLAS_GRANT_ID", self.nylas_grant_id)
            ])
            
            missing = [var for var, value in required_vars if not value]
            if missing:
                raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for logging (excluding sensitive data)."""
        return {
            "port": self.port,
            "host": self.host,
            "log_level": self.log_level,
            "bot_name": self.bot_name,
            "enable_health_check": self.enable_health_check,
            "daily_configured": bool(self.daily_api_key),
            "google_configured": bool(self.google_api_key),
            "nylas_configured": bool(self.nylas_api_key and self.nylas_grant_id)
        }

# Global config instance
config = Config()