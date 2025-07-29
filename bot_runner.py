import os
import json
import subprocess
import asyncio
from typing import Dict
from aiohttp import web
from dotenv import load_dotenv
from loguru import logger
import aiohttp

load_dotenv(override=True)

# Store active bot processes
active_bots: Dict[str, subprocess.Popen] = {}

async def create_room():
    """Create a new Daily room for the bot."""
    url = "https://api.daily.co/v1/rooms"
    headers = {
        "Authorization": f"Bearer {os.getenv('DAILY_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                logger.error(f"Failed to create room: {response.status}")
                return None

async def create_token(room_name: str, is_owner: bool = True):
    """Create a meeting token for the room."""
    url = "https://api.daily.co/v1/meeting-tokens"
    headers = {
        "Authorization": f"Bearer {os.getenv('DAILY_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    data = {
        "properties": {
            "room_name": room_name,
            "is_owner": is_owner,
            "exp": 60 * 60  # 1 hour expiration
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                data = await response.json()
                return data["token"]
            else:
                logger.error(f"Failed to create token: {response.status}")
                return None

async def start_bot(request: web.Request):
    """Start a new bot instance."""
    try:
        # Get request data
        data = await request.json() if request.body_exists else {}
        room_url = data.get("room_url")
        
        # If no room URL provided, create a new room
        if not room_url:
            room_data = await create_room()
            if not room_data:
                return web.json_response({"error": "Failed to create room"}, status=500)
            room_url = room_data["url"]
            room_name = room_data["name"]
        else:
            # Extract room name from URL
            room_name = room_url.split("/")[-1]
        
        # Create tokens
        bot_token = await create_token(room_name, is_owner=True)
        client_token = await create_token(room_name, is_owner=False)
        
        if not bot_token or not client_token:
            return web.json_response({"error": "Failed to create tokens"}, status=500)
        
        # Start the bot process
        cmd = [
            "python", "bot.py",
            "-u", room_url,
            "-t", bot_token
        ]
        
        # Add call parameters if this is an incoming call
        call_id = data.get("callId")
        call_domain = data.get("callDomain")
        if call_id:
            cmd.extend(["-i", call_id])
        if call_domain:
            cmd.extend(["-d", call_domain])
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Store the process
        active_bots[room_name] = proc
        
        logger.info(f"Started bot for room: {room_name}")
        
        return web.json_response({
            "room_url": room_url,
            "room_name": room_name,
            "token": client_token,
            "bot_token": bot_token
        })
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def stop_bot(request: web.Request):
    """Stop a bot instance."""
    try:
        data = await request.json()
        room_name = data.get("room_name")
        
        if room_name in active_bots:
            proc = active_bots[room_name]
            proc.terminate()
            del active_bots[room_name]
            logger.info(f"Stopped bot for room: {room_name}")
            return web.json_response({"status": "stopped"})
        else:
            return web.json_response({"error": "Bot not found"}, status=404)
            
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def get_token(request: web.Request):
    """Get a token for joining an existing room (compatibility endpoint)."""
    try:
        room_name = request.query.get("room", "my-agent-room")
        identity = request.query.get("identity", "user")
        
        token = await create_token(room_name, is_owner=False)
        
        if token:
            return web.json_response({"token": token})
        else:
            return web.json_response({"error": "Failed to create token"}, status=500)
            
    except Exception as e:
        logger.error(f"Error getting token: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_incoming_call(request: web.Request):
    """Handle incoming phone calls via Daily."""
    try:
        data = await request.json()
        logger.info(f"Incoming call: {data}")
        
        # Start a bot for the incoming call
        return await start_bot(request)
        
    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def health_check(request: web.Request):
    """Health check endpoint."""
    return web.json_response({"status": "healthy", "active_bots": len(active_bots)})

async def cleanup_bots(app):
    """Cleanup all active bots on shutdown."""
    logger.info("Cleaning up active bots...")
    for room_name, proc in active_bots.items():
        proc.terminate()
        logger.info(f"Terminated bot for room: {room_name}")
    active_bots.clear()

def create_app():
    """Create the web application."""
    app = web.Application()
    
    # Routes
    app.router.add_post("/start", start_bot)
    app.router.add_post("/stop", stop_bot)
    app.router.add_get("/get-token", get_token)  # Compatibility with your existing endpoint
    app.router.add_post("/incoming-call", handle_incoming_call)
    app.router.add_get("/health", health_check)
    
    # Cleanup handler
    app.on_cleanup.append(cleanup_bots)
    
    return app

def main():
    """Run the bot runner server."""
    logging_level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=logging_level
    )
    
    app = create_app()
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8080))
    
    logger.info(f"Starting bot runner on {host}:{port}")
    web.run_app(app, host=host, port=port)

if __name__ == "__main__":
    main()