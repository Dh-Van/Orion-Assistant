"""
Main entry point for the Pipecat Email Agent.
Designed for Google Cloud Run deployment.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Dict, Optional

from aiohttp import web
from loguru import logger

from config import config
from bot import BotManager

# Global bot manager instance
bot_manager: Optional[BotManager] = None

@asynccontextmanager
async def lifespan(app: web.Application):
    """Application lifespan manager."""
    global bot_manager
    
    logger.info("Starting Pipecat Email Agent...")
    logger.info(f"Configuration: {config.to_dict()}")
    
    # Initialize bot manager
    bot_manager = BotManager()
    
    yield
    
    # Cleanup
    logger.info("Shutting down Pipecat Email Agent...")
    if bot_manager:
        await bot_manager.cleanup()

async def health_check(request: web.Request):
    """Health check endpoint for Cloud Run."""
    return web.json_response({
        "status": "healthy",
        "service": "pipecat-email-agent",
        "bot_name": config.bot_name,
        "active_bots": bot_manager.get_active_bot_count() if bot_manager else 0
    })

async def start_bot(request: web.Request):
    """Start a new bot instance."""
    if not bot_manager:
        return web.json_response({"error": "Service not initialized"}, status=503)
    
    try:
        data = await request.json() if request.body_exists else {}
        result = await bot_manager.start_bot(data)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def stop_bot(request: web.Request):
    """Stop a bot instance."""
    if not bot_manager:
        return web.json_response({"error": "Service not initialized"}, status=503)
    
    try:
        data = await request.json()
        room_name = data.get("room_name")
        if not room_name:
            return web.json_response({"error": "room_name required"}, status=400)
        
        await bot_manager.stop_bot(room_name)
        return web.json_response({"status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def get_token(request: web.Request):
    """Get a token for joining an existing room."""
    if not bot_manager:
        return web.json_response({"error": "Service not initialized"}, status=503)
    
    try:
        room_name = request.query.get("room", "default-room")
        identity = request.query.get("identity", "user")
        
        token = await bot_manager.create_token(room_name, is_owner=False)
        if token:
            return web.json_response({"token": token})
        else:
            return web.json_response({"error": "Failed to create token"}, status=500)
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_incoming_call(request: web.Request):
    """Handle incoming phone calls via Daily."""
    if not bot_manager:
        return web.json_response({"error": "Service not initialized"}, status=503)
    
    try:
        data = await request.json()
        logger.info(f"Incoming call: {data}")
        result = await bot_manager.start_bot(data)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        return web.json_response({"error": str(e)}, status=500)

def create_app() -> web.Application:
    """Create the web application."""
    app = web.Application()
    
    # Add routes
    if config.enable_health_check:
        app.router.add_get("/health", health_check)
        app.router.add_get("/", health_check)  # Cloud Run default health check
    
    app.router.add_post("/start", start_bot)
    app.router.add_post("/stop", stop_bot)
    app.router.add_get("/get-token", get_token)
    app.router.add_post("/incoming-call", handle_incoming_call)
    
    return app

def setup_logging():
    """Configure logging for Cloud Run compatibility."""
    logger.remove()
    
    # Cloud Run expects logs in stdout
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level=config.log_level
    )

def handle_sigterm(signum, frame):
    """Handle SIGTERM for graceful shutdown in Cloud Run."""
    logger.info("Received SIGTERM, initiating graceful shutdown...")
    sys.exit(0)

async def init_app():
    """Initialize the application with lifespan management."""
    global bot_manager
    
    # Initialize bot manager
    bot_manager = BotManager()
    logger.info("Bot manager initialized")
    
    app = create_app()
    return app

def main():
    """Main entry point."""
    setup_logging()
    
    # Register signal handler for Cloud Run
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    logger.info(f"Starting server on {config.host}:{config.port}")
    
    # Run the app with proper initialization
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Initialize the app
    app = loop.run_until_complete(init_app())
    
    # Run the web app
    web.run_app(
        app,
        host=config.host,
        port=config.port,
        handle_signals=True,
        access_log=None,  # Disable access logs (we use structured logging)
        loop=loop
    )

if __name__ == "__main__":
    main()