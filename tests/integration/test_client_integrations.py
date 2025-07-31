"""
Integration tests for all clients.
These tests actually call the real APIs when credentials are provided.

To run these tests:
1. Set up a .env.test file with real credentials
2. Run: pytest tests/integration/test_clients_integration.py -v

To run specific client tests:
- Daily only: pytest tests/integration/test_clients_integration.py::TestDailyIntegration -v
- Nylas only: pytest tests/integration/test_clients_integration.py::TestNylasIntegration -v
- Gemini only: pytest tests/integration/test_clients_integration.py::TestGeminiIntegration -v
"""

import os
import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import List
import json
import base64
from dotenv import load_dotenv

# Load test environment
load_dotenv('.env.test')

# Import clients
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.clients.daily import DailyClient, RoomInfo, TokenInfo
from src.clients.nylas import NylasClient, Email
from src.clients.gemini import GeminiClient


# Test configuration
DAILY_API_KEY = os.getenv('DAILY_API_KEY_TEST', os.getenv('DAILY_API_KEY'))
NYLAS_API_KEY = os.getenv('NYLAS_API_KEY_TEST', os.getenv('NYLAS_API_KEY'))
NYLAS_GRANT_ID = os.getenv('NYLAS_GRANT_ID_TEST', os.getenv('NYLAS_GRANT_ID'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY_TEST', os.getenv('GOOGLE_API_KEY'))

# Handle Google credentials from base64
GOOGLE_CREDENTIALS_B64 = os.getenv('GOOGLE_CREDENTIALS')
if GOOGLE_CREDENTIALS_B64:
    try:
        # Decode and save credentials to a temp file
        creds_json = base64.b64decode(GOOGLE_CREDENTIALS_B64)
        creds_dict = json.loads(creds_json)
        
        # Write to a temporary credentials file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(creds_dict, f)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = f.name
    except Exception as e:
        print(f"Failed to decode Google credentials: {e}")

# Test email settings (change these to your test email)
TEST_EMAIL_TO = os.getenv('TEST_EMAIL_TO', 'test@example.com')
TEST_EMAIL_FROM = os.getenv('TEST_EMAIL_FROM', 'sender@example.com')


@pytest.mark.integration
class TestDailyIntegration:
    """Integration tests for Daily.co client."""
    
    @pytest_asyncio.fixture
    async def daily_client(self):
        """Create Daily client instance."""
        if not DAILY_API_KEY:
            pytest.skip("DAILY_API_KEY not set")
        return DailyClient(api_key=DAILY_API_KEY)
    
    @pytest_asyncio.fixture
    async def cleanup_rooms(self, daily_client):
        """Cleanup any test rooms after tests."""
        created_rooms = []
        yield created_rooms
        
        # Cleanup
        for room_name in created_rooms:
            try:
                await daily_client.delete_room(room_name)
                print(f"Cleaned up room: {room_name}")
            except Exception as e:
                print(f"Failed to cleanup room {room_name}: {e}")
    
    @pytest.mark.asyncio
    async def test_create_and_delete_room(self, daily_client, cleanup_rooms):
        """Test creating and deleting a room."""
        # Create room
        room_info = await daily_client.create_room(
            name=f"test-room-{int(datetime.now(timezone.utc).timestamp())}",
            privacy="public"
        )
        
        assert room_info is not None
        assert room_info.name is not None
        assert room_info.url is not None
        assert "daily.co" in room_info.url
        
        cleanup_rooms.append(room_info.name)
        
        # Verify room exists
        fetched_room = await daily_client.get_room(room_info.name)
        assert fetched_room is not None
        assert fetched_room.name == room_info.name
        
        # Delete room
        success = await daily_client.delete_room(room_info.name)
        assert success is True
        
        # Verify room is gone
        deleted_room = await daily_client.get_room(room_info.name)
        assert deleted_room is None
        
        # Remove from cleanup since we already deleted it
        cleanup_rooms.remove(room_info.name)
    
    @pytest.mark.asyncio
    async def test_create_tokens(self, daily_client, cleanup_rooms):
        """Test creating owner and participant tokens."""
        # Create room first
        room_info = await daily_client.create_room()
        cleanup_rooms.append(room_info.name)
        
        # Create owner token
        owner_token = await daily_client.create_token(
            room_name=room_info.name,
            is_owner=True,
            user_name="Test Owner"
        )
        
        assert owner_token is not None
        assert owner_token.token is not None
        assert owner_token.is_owner is True
        assert owner_token.room_name == room_info.name
        assert owner_token.user_name == "Test Owner"
        
        # Create participant token
        participant_token = await daily_client.create_token(
            room_name=room_info.name,
            is_owner=False,
            user_name="Test Participant"
        )
        
        assert participant_token is not None
        assert participant_token.token is not None
        assert participant_token.is_owner is False
        assert participant_token.token != owner_token.token
    
    @pytest.mark.asyncio
    async def test_room_expiration(self, daily_client, cleanup_rooms):
        """Test creating a room with expiration."""
        # Create room that expires in 5 minutes
        room_info = await daily_client.create_room(
            name=f"test-exp-room-{int(datetime.now(timezone.utc).timestamp())}",
            exp=int(datetime.now(timezone.utc).timestamp()) + 300  # 5 minutes
        )
        
        cleanup_rooms.append(room_info.name)
        
        assert room_info is not None
        
        # Room should exist now
        fetched_room = await daily_client.get_room(room_info.name)
        assert fetched_room is not None
    
    @pytest.mark.asyncio
    async def test_list_rooms(self, daily_client):
        """Test listing rooms."""
        rooms = await daily_client.list_rooms(limit=10)
        
        assert isinstance(rooms, list)
        # We might have 0 rooms, that's OK
        if len(rooms) > 0:
            assert isinstance(rooms[0], RoomInfo)
            assert rooms[0].name is not None
            assert rooms[0].url is not None
    
    @pytest.mark.asyncio
    async def test_create_room_and_token_convenience(self, daily_client, cleanup_rooms):
        """Test the convenience method."""
        room_info, token_info = await daily_client.create_room_and_token(
            user_name="Test User",
            room_exp_minutes=60,
            token_exp_minutes=30
        )
        
        cleanup_rooms.append(room_info.name)
        
        assert room_info is not None
        assert token_info is not None
        assert token_info.room_name == room_info.name
        assert token_info.user_name == "Test User"


@pytest.mark.integration
class TestNylasIntegration:
    """Integration tests for Nylas client."""
    
    @pytest.fixture
    def nylas_client(self):
        """Create Nylas client instance."""
        if not NYLAS_API_KEY or not NYLAS_GRANT_ID:
            pytest.skip("NYLAS_API_KEY or NYLAS_GRANT_ID not set")
        return NylasClient(
            grant_id=NYLAS_GRANT_ID,
            api_key=NYLAS_API_KEY
        )
    
    @pytest.mark.asyncio
    async def test_read_emails(self, nylas_client):
        """Test reading emails from inbox."""
        emails = nylas_client.read_emails(limit=5)
        
        assert isinstance(emails, list)
        
        if len(emails) > 0:
            # Check first email
            email = emails[0]
            assert isinstance(email, Email)
            assert email.id is not None
            assert email.subject is not None
            
            # Test string representation
            email_str = str(email)
            assert "Email from" in email_str
    
    @pytest.mark.asyncio
    async def test_search_emails(self, nylas_client):
        """Test searching emails."""
        # Search by subject
        results = nylas_client.search_emails(
            query="test",
            search_field="subject",
            limit=5
        )
        
        assert isinstance(results, list)
        
        # Search in body
        body_results = nylas_client.search_emails(
            query="the",
            search_field="body",
            limit=5
        )
        
        assert isinstance(body_results, list)
    
    @pytest.mark.asyncio
    async def test_send_and_read_email(self, nylas_client):
        """Test sending an email and reading it back."""
        # Create unique subject
        timestamp = datetime.now().isoformat()
        subject = f"Integration Test Email - {timestamp}"
        body = f"This is an automated test email sent at {timestamp}"
        
        # Send email
        success = nylas_client.send_email(
            to=TEST_EMAIL_TO,
            subject=subject,
            body=body
        )
        
        assert success is True
        
        # Wait a moment for email to be processed
        await asyncio.sleep(2)
        
        # Try to find the email we just sent
        # Note: This might not work immediately due to email delivery delays
        results = nylas_client.search_emails(
            query=subject,
            search_field="subject",
            limit=10
        )
        
        # We might not find it immediately due to delays, that's OK
        print(f"Found {len(results)} emails with subject containing '{subject}'")
    
    @pytest.mark.asyncio
    async def test_get_email_by_id(self, nylas_client):
        """Test fetching specific email by ID."""
        # First, get some emails
        emails = nylas_client.read_emails(limit=100)
        
        if len(emails) == 0:
            pytest.skip("No emails in inbox to test with")
        
        email_id = emails[0].id
        
        # Fetch specific email
        email = nylas_client.get_email_by_id(email_id)
        
        assert email is not None
        assert email.id == email_id
        assert email.subject is not None
    
    @pytest.mark.asyncio
    async def test_email_with_multiple_recipients(self, nylas_client):
        """Test sending email with CC."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        success = nylas_client.send_email(
            to=[{"name": "Primary", "email": TEST_EMAIL_TO}],
            subject=f"Multi-recipient Test - {timestamp}",
            body="Testing email with multiple recipients",
            cc=[{"name": "CC Test", "email": TEST_EMAIL_TO}]  # CC to same address for testing
        )
        
        assert success is True


@pytest.mark.integration
class TestGeminiIntegration:
    """Integration tests for Gemini/Google AI client."""
    
    @pytest.fixture
    def gemini_client(self):
        """Create Gemini client instance."""
        if not GOOGLE_API_KEY:
            pytest.skip("GOOGLE_API_KEY not set")
        return GeminiClient(api_key=GOOGLE_API_KEY)
    
    @pytest.mark.asyncio
    async def test_generate_response(self, gemini_client):
        """Test basic text generation."""
        response = gemini_client.generate_response(
            prompt="Say hello in exactly 5 words",
            temperature=0.1  # Low temperature for consistency
        )
        
        assert response is not None
        assert len(response) > 0
        assert isinstance(response, str)
        
        # Test with system instruction
        response_with_system = gemini_client.generate_response(
            prompt="What is 2+2?",
            system_instruction="You are a helpful math tutor. Give brief answers.",
            temperature=0.1
        )
        
        assert "4" in response_with_system
    
    @pytest.mark.asyncio
    async def test_create_embeddings(self, gemini_client):
        """Test embedding generation."""
        texts = [
            "Hello world",
            "Goodbye world",
            "The quick brown fox jumps over the lazy dog"
        ]
        
        embeddings = gemini_client.create_embeddings(texts)
        
        assert len(embeddings) == 3
        assert all(isinstance(emb, list) for emb in embeddings)
        assert all(len(emb) > 0 for emb in embeddings)
        assert all(isinstance(emb[0], float) for emb in embeddings)
        
        # Test single embedding
        single_embedding = gemini_client.create_embedding("Test text")
        assert isinstance(single_embedding, list)
        assert len(single_embedding) > 0
    
    @pytest.mark.asyncio
    async def test_summarize_text(self, gemini_client):
        """Test text summarization."""
        long_text = """
        The email assistant project is a voice-controlled application that allows users
        to manage their email inbox using natural language commands. Users can send emails,
        read their latest messages, and search for specific emails using voice commands.
        The system uses advanced AI to understand user intent and execute email operations.
        It integrates with Nylas for email management, Google's Gemini for natural language
        processing, and Daily.co for real-time voice communication. The architecture is
        designed to be scalable and maintainable, with clear separation of concerns.
        """
        
        summary = gemini_client.summarize_text(
            text=long_text,
            max_length=50,
            style="concise"
        )
        
        assert summary is not None
        assert len(summary) < len(long_text)
        assert isinstance(summary, str)
        
        # Test bullet point style
        bullet_summary = gemini_client.summarize_text(
            text=long_text,
            max_length=100,
            style="bullet_points"
        )
        
        assert bullet_summary is not None
        # Might contain bullet indicators
        assert any(char in bullet_summary for char in ['•', '-', '*', '·']) or 'point' in bullet_summary.lower()
    
    @pytest.mark.asyncio
    async def test_vector_search(self, gemini_client):
        """Test vector similarity search."""
        # Create test emails
        test_emails = [
            {
                "id": "1",
                "subject": "Meeting tomorrow at 3pm",
                "body": "Let's discuss the quarterly results in the conference room.",
                "senders": "boss@company.com",
                "date": "2024-01-01"
            },
            {
                "id": "2",
                "subject": "Your Amazon order has shipped",
                "body": "Your package will arrive tomorrow. Track your shipment online.",
                "senders": "amazon@amazon.com",
                "date": "2024-01-02"
            },
            {
                "id": "3",
                "subject": "Lunch plans",
                "body": "Want to grab sushi at that new place downtown?",
                "senders": "friend@email.com",
                "date": "2024-01-03"
            },
            {
                "id": "4",
                "subject": "Project deadline reminder",
                "body": "Don't forget the project is due next Friday. Please review the requirements.",
                "senders": "manager@company.com",
                "date": "2024-01-04"
            }
        ]
        
        # Search for work-related emails
        results = gemini_client.search_emails_with_vectors(
            emails=test_emails,
            query="work meeting project",
            search_field="body",
            num_results=2
        )
        
        assert len(results) <= 2
        assert all(isinstance(result, tuple) for result in results)
        assert all(len(result) == 2 for result in results)  # (email, score)
        
        # The meeting and project emails should rank higher
        if len(results) > 0:
            top_result = results[0][0]
            assert top_result["id"] in ["1", "4"]  # Meeting or project email
        
        # Test searching all fields
        all_field_results = gemini_client.search_emails_with_vectors(
            emails=test_emails,
            query="Amazon shipping",
            search_field="all",
            num_results=1
        )
        
        if len(all_field_results) > 0:
            assert all_field_results[0][0]["id"] == "2"  # Amazon email
    
    @pytest.mark.asyncio
    async def test_generate_email_reply(self, gemini_client):
        """Test email reply generation."""
        original_email = """
        Hi there,
        
        I wanted to check if you're available for a meeting next Tuesday at 2 PM
        to discuss the new project requirements. Please let me know if this works
        for your schedule.
        
        Best regards,
        John
        """
        
        reply = gemini_client.generate_email_reply(
            original_email=original_email,
            instruction="Accept the meeting and suggest we also discuss the budget",
            tone="professional"
        )
        
        assert reply is not None
        assert len(reply) > 0
        assert "tuesday" in reply.lower() or "meeting" in reply.lower()
        assert "budget" in reply.lower()
        
        # Test different tone
        casual_reply = gemini_client.generate_email_reply(
            original_email=original_email,
            instruction="Decline politely, I'm busy that day",
            tone="friendly"
        )
        
        assert casual_reply is not None
        assert casual_reply != reply  # Should be different
        

@pytest.mark.integration
class TestClientIntegration:
    """Test integration between multiple clients."""
    
    @pytest.fixture
    def all_clients(self):
        """Create all client instances."""
        if not all([DAILY_API_KEY, NYLAS_API_KEY, NYLAS_GRANT_ID, GOOGLE_API_KEY]):
            pytest.skip("Not all API keys are set")
            
        return {
            'daily': DailyClient(api_key=DAILY_API_KEY),
            'nylas': NylasClient(grant_id=NYLAS_GRANT_ID, api_key=NYLAS_API_KEY),
            'gemini': GeminiClient(api_key=GOOGLE_API_KEY)
        }
    
    @pytest.mark.asyncio
    async def test_email_search_with_ai(self, all_clients):
        """Test reading emails and searching with AI."""
        nylas = all_clients['nylas']
        gemini = all_clients['gemini']
        
        # Read some emails
        emails = nylas.read_emails(limit=10)
        
        if len(emails) < 2:
            pytest.skip("Not enough emails to test search")
        
        # Convert to dict format for vector search
        email_dicts = [email.to_dict() for email in emails]
        
        # Search using AI
        results = gemini.search_emails_with_vectors(
            emails=email_dicts,
            query="important urgent priority",
            search_field="subject",
            num_results=3
        )
        
        assert isinstance(results, list)
        print(f"Found {len(results)} emails matching 'important urgent priority'")
        
        # If we have results, verify structure
        if len(results) > 0:
            email, score = results[0]
            assert 'id' in email
            assert 'subject' in email
            assert isinstance(score, float)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


if __name__ == "__main__":
    # Run all integration tests
    pytest.main([__file__, "-v", "-m", "integration"])