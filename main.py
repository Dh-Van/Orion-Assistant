import asyncio
import os
from dotenv import load_dotenv
from loguru import logger

from pipecat.transports.services.daily import DailyTransport, DailyParams
from src.agents.orchestrator import AgentOrchestratorFactory

# Load environment variables from .env file
load_dotenv(".env.test")

async def main():
    """Main function to set up and run the agent."""
    logger.info("Starting email voice agent...")

    # The DailyTransport is used to handle WebRTC connections.
    # It requires a Daily.co API key to manage rooms.
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable is not set.")

    # Configure Daily transport with explicit audio settings
    transport = DailyTransport(
        room_url=os.getenv("DAILY_ROOM_URL"),
        token=os.getenv("DAILY_TOKEN"),
        bot_name="Email Agent",
        params=DailyParams(
            audio_in_enabled=True,    # Enable audio input
            audio_out_enabled=True,   # Enable audio output
            video_out_enabled=False,  # Disable video (not needed)
            vad_enabled=True,         # Enable voice activity detection
            vad_analyzer=None,        # Will use default or from voice interface
            audio_in_sample_rate=16000,
            audio_out_sample_rate=16000,
            start_audio_muted=False,  # Important: Don't start muted
            start_video_muted=True
        )
    )

    # The factory class creates a fully configured agent orchestrator
    # using the settings from your environment variables.
    orchestrator = AgentOrchestratorFactory.create_from_env(
        transport=transport,
        enable_metrics=True,
        enable_usage_metrics=True
    )

    # Set up event handlers and pipeline
    await orchestrator.setup()

    # Run the main pipeline task
    await orchestrator.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")