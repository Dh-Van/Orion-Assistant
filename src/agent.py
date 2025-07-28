import logging
import os
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import google

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug-agent")

load_dotenv(".env.local")

class DebugAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a debug assistant.",
        )

async def entrypoint(ctx: JobContext):
    try:
        logger.info(f"🚀 Debug agent starting for room: {ctx.room.name}")
        
        # Check environment variables
        livekit_url = os.getenv('LIVEKIT_URL')
        livekit_key = os.getenv('LIVEKIT_API_KEY')
        livekit_secret = os.getenv('LIVEKIT_API_SECRET')
        
        logger.info(f"🔧 Environment check:")
        logger.info(f"   LIVEKIT_URL: {livekit_url}")
        logger.info(f"   LIVEKIT_API_KEY: {livekit_key[:10] if livekit_key else None}...")
        logger.info(f"   LIVEKIT_API_SECRET: {livekit_secret[:10] if livekit_secret else None}...")
        
        if not all([livekit_url, livekit_key, livekit_secret]):
            logger.error("❌ Missing required environment variables!")
            raise ValueError("Missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET")
        
        # Simple session without Google services first
        session = AgentSession()
        
        logger.info("🎯 Starting debug session...")
        await session.start(
            agent=DebugAssistant(),
            room=ctx.room,
        )
        
        logger.info("✅ Session started, connecting to room...")
        await ctx.connect()
        logger.info(f"🎉 Debug agent successfully connected to room: {ctx.room.name}")
        
        # Keep alive for testing
        import asyncio
        logger.info("💤 Agent staying alive for 10 minutes for testing...")
        await asyncio.sleep(600)
        
    except Exception as e:
        logger.error(f"❌ Debug agent failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    logger.info("🎬 Starting debug LiveKit agent...")
    
    # Print environment info at startup
    logger.info(f"🌍 Environment variables:")
    logger.info(f"   LIVEKIT_URL: {os.getenv('LIVEKIT_URL')}")
    logger.info(f"   LIVEKIT_API_KEY exists: {bool(os.getenv('LIVEKIT_API_KEY'))}")
    logger.info(f"   LIVEKIT_API_SECRET exists: {bool(os.getenv('LIVEKIT_API_SECRET'))}")
    
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))