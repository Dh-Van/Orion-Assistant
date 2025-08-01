#!/usr/bin/env python3
"""
Simple script to test the Pipecat email agent with function calling.

Usage:
    python run_email_test.py
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# Add the project root to Python path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipecat.transports.services.daily import DailyTransport, DailyParams
from src.agents.orchestrator import AgentOrchestratorFactory
from src.clients.daily import DailyClient


async def test_email_agent():
    """Test the email agent by creating a room and demonstrating function calling."""
    
    # Load environment variables
    load_dotenv('.env.test')
    
    # Configuration
    DAILY_API_KEY = os.getenv('DAILY_API_KEY')
    EMAIL_RECIPIENT = "dhvan.spams@gmail.com"
    
    if not DAILY_API_KEY:
        print("Error: DAILY_API_KEY not set in environment")
        return
    
    # Create Daily client
    daily_client = DailyClient(api_key=DAILY_API_KEY)
    
    # Create a room for testing
    print("🚀 Pipecat Email Agent Test with Function Calling")
    print("=" * 50)
    print("Creating Daily room...")
    
    room_info, token_info = await daily_client.create_room_and_token(
        room_name=f"email-test-{int(datetime.now().timestamp())}",
        user_name="Pipecat Email Bot",
        room_exp_minutes=10
    )
    
    print(f"\n✅ Room created!")
    print(f"📹 Room URL: {room_info.url}")
    print(f"🤖 Bot joining with Pipecat function calling enabled...")
    
    try:
        # Create transport
        transport = DailyTransport(
            room_url=room_info.url,
            token=token_info.token,
            bot_name="Pipecat Email Assistant",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                video_out_enabled=False,
                vad_enabled=True
            )
        )
        
        # Create orchestrator with Pipecat function calling
        orchestrator = AgentOrchestratorFactory.create_from_env(transport=transport)
        await orchestrator.setup()
        
        print("\n🎙️  Bot is ready with function calling capabilities!")
        print("\n📧 You can now:")
        print(f"1. Join the room at: {room_info.url}")
        print("2. Try these commands:")
        print(f"   - 'Send an email to {EMAIL_RECIPIENT}'")
        print("   - 'Read my recent emails'")
        print("   - 'Search for emails about meetings'")
        print("\n💡 The bot will use Pipecat's native function calling to execute your requests.")
        print("\nPress Ctrl+C to stop the bot...")
        
        # Run the orchestrator
        await orchestrator.run()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping bot...")
    except Exception as e:
        logger.error(f"Error during test: {e}")
        print(f"\n❌ Error: {e}")
    
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        await daily_client.delete_room(room_info.name)
        print("✅ Room deleted")
        print("\n👋 Test completed!")


if __name__ == "__main__":
    print("🚀 AI Email Agent Test")
    print("=" * 40)
    asyncio.run(test_email_agent())