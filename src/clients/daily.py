"""
Daily.co client for WebRTC room management.
Extracted from bot.py's BotManager
"""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiohttp
from loguru import logger


@dataclass
class RoomInfo:
    """Daily room information."""
    name: str
    url: str
    id: Optional[str] = None
    privacy: str = "public"
    created_at: Optional[datetime] = None
    config: Optional[Dict[str, Any]] = None


@dataclass
class TokenInfo:
    """Daily meeting token information."""
    token: str
    room_name: str
    is_owner: bool
    expires_at: datetime
    user_name: Optional[str] = None


class DailyClient:
    """Client for Daily.co room and token management."""
    
    def __init__(self, api_key: str, api_url: str = "https://api.daily.co/v1"):
        """
        Initialize Daily client.
        
        Args:
            api_key: Daily API key
            api_url: Base URL for Daily API
        """
        if not api_key:
            raise ValueError("Daily API key is required")
            
        self.api_key = api_key
        self.api_url = api_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        logger.info("Initialized Daily client")
    
    async def create_room(
        self,
        name: Optional[str] = None,
        privacy: str = "public",
        properties: Optional[Dict[str, Any]] = None,
        exp: Optional[int] = None
    ) -> RoomInfo:
        """
        Create a new Daily room.
        
        Args:
            name: Optional room name (auto-generated if not provided)
            privacy: Room privacy setting ('public' or 'private')
            properties: Additional room properties
            exp: Unix timestamp when room expires
            
        Returns:
            RoomInfo object with room details
            
        Raises:
            Exception: If room creation fails
        """
        try:
            url = f"{self.api_url}/rooms"
            
            data = {
                "privacy": privacy
            }
            
            if name:
                data["name"] = name
                
            if properties:
                data["properties"] = properties
                
            if exp:
                data["properties"] = data.get("properties", {})
                data["properties"]["exp"] = exp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data) as response:
                    if response.status == 200:
                        room_data = await response.json()
                        logger.info(f"Created room: {room_data.get('name')}")
                        
                        return RoomInfo(
                            name=room_data["name"],
                            url=room_data["url"],
                            id=room_data.get("id"),
                            privacy=room_data.get("privacy", "public"),
                            created_at=datetime.utcnow(),
                            config=room_data.get("config")
                        )
                    else:
                        error = await response.text()
                        raise Exception(f"Failed to create room: {response.status} - {error}")
                        
        except Exception as e:
            logger.error(f"Error creating Daily room: {e}")
            raise
    
    async def create_token(
        self,
        room_name: str,
        is_owner: bool = False,
        user_name: Optional[str] = None,
        exp_minutes: int = 60,
        properties: Optional[Dict[str, Any]] = None
    ) -> TokenInfo:
        """
        Create a meeting token for a room.
        
        Args:
            room_name: Name of the room
            is_owner: Whether this token has owner privileges
            user_name: Optional display name for the user
            exp_minutes: Token expiration in minutes from now
            properties: Additional token properties
            
        Returns:
            TokenInfo object with token details
            
        Raises:
            Exception: If token creation fails
        """
        try:
            url = f"{self.api_url}/meeting-tokens"
            
            # Calculate expiration
            exp_timestamp = int(time.time()) + (exp_minutes * 60)
            
            data = {
                "properties": {
                    "room_name": room_name,
                    "is_owner": is_owner,
                    "exp": exp_timestamp
                }
            }
            
            if user_name:
                data["properties"]["user_name"] = user_name
                
            if properties:
                data["properties"].update(properties)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Created {'owner' if is_owner else 'participant'} token for room: {room_name}")
                        
                        return TokenInfo(
                            token=result["token"],
                            room_name=room_name,
                            is_owner=is_owner,
                            expires_at=datetime.fromtimestamp(exp_timestamp),
                            user_name=user_name
                        )
                    else:
                        error = await response.text()
                        raise Exception(f"Failed to create token: {response.status} - {error}")
                        
        except Exception as e:
            logger.error(f"Error creating Daily token: {e}")
            raise
    
    async def get_room(self, room_name: str) -> Optional[RoomInfo]:
        """
        Get information about a specific room.
        
        Args:
            room_name: Name of the room
            
        Returns:
            RoomInfo object or None if room doesn't exist
        """
        try:
            url = f"{self.api_url}/rooms/{room_name}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        room_data = await response.json()
                        
                        return RoomInfo(
                            name=room_data["name"],
                            url=room_data["url"],
                            id=room_data.get("id"),
                            privacy=room_data.get("privacy", "public"),
                            config=room_data.get("config")
                        )
                    elif response.status == 404:
                        logger.debug(f"Room not found: {room_name}")
                        return None
                    else:
                        error = await response.text()
                        logger.error(f"Failed to get room: {response.status} - {error}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting Daily room: {e}")
            return None
    
    async def delete_room(self, room_name: str) -> bool:
        """
        Delete a Daily room.
        
        Args:
            room_name: Name of the room to delete
            
        Returns:
            bool: True if successful
        """
        try:
            url = f"{self.api_url}/rooms/{room_name}"
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=self.headers) as response:
                    if response.status == 200:
                        logger.info(f"Deleted room: {room_name}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Failed to delete room: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error deleting Daily room: {e}")
            return False
    
    async def list_rooms(
        self,
        limit: int = 100,
        ending_before: Optional[str] = None
    ) -> List[RoomInfo]:
        """
        List all rooms.
        
        Args:
            limit: Maximum number of rooms to return
            ending_before: Pagination cursor
            
        Returns:
            List of RoomInfo objects
        """
        try:
            url = f"{self.api_url}/rooms"
            params = {"limit": limit}
            
            if ending_before:
                params["ending_before"] = ending_before
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        rooms = []
                        
                        for room_data in data.get("data", []):
                            rooms.append(RoomInfo(
                                name=room_data["name"],
                                url=room_data["url"],
                                id=room_data.get("id"),
                                privacy=room_data.get("privacy", "public"),
                                config=room_data.get("config")
                            ))
                        
                        logger.info(f"Listed {len(rooms)} rooms")
                        return rooms
                    else:
                        error = await response.text()
                        logger.error(f"Failed to list rooms: {response.status} - {error}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error listing Daily rooms: {e}")
            return []
    
    async def get_room_presence(self, room_name: str) -> Dict[str, Any]:
        """
        Get current presence info for a room (who's in the room).
        
        Args:
            room_name: Name of the room
            
        Returns:
            Dict with presence information
        """
        try:
            url = f"{self.api_url}/presence/{room_name}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        presence = await response.json()
                        logger.debug(f"Got presence for room {room_name}: {len(presence)} participants")
                        return presence
                    else:
                        error = await response.text()
                        logger.error(f"Failed to get presence: {response.status} - {error}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Error getting room presence: {e}")
            return {}
    
    async def update_room(
        self,
        room_name: str,
        properties: Dict[str, Any]
    ) -> bool:
        """
        Update room properties.
        
        Args:
            room_name: Name of the room
            properties: Properties to update
            
        Returns:
            bool: True if successful
        """
        try:
            url = f"{self.api_url}/rooms/{room_name}"
            
            data = {"properties": properties}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data) as response:
                    if response.status == 200:
                        logger.info(f"Updated room: {room_name}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Failed to update room: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error updating Daily room: {e}")
            return False
    
    async def create_room_and_token(
        self,
        room_name: Optional[str] = None,
        is_owner: bool = True,
        user_name: Optional[str] = None,
        room_exp_minutes: Optional[int] = None,
        token_exp_minutes: int = 60
    ) -> tuple[RoomInfo, TokenInfo]:
        """
        Convenience method to create both room and token.
        
        Args:
            room_name: Optional room name
            is_owner: Whether to create owner token
            user_name: Optional user display name
            room_exp_minutes: Room expiration in minutes
            token_exp_minutes: Token expiration in minutes
            
        Returns:
            Tuple of (RoomInfo, TokenInfo)
        """
        try:
            # Create room
            room_exp = None
            if room_exp_minutes:
                room_exp = int(time.time()) + (room_exp_minutes * 60)
                
            room_info = await self.create_room(name=room_name, exp=room_exp)
            
            # Create token
            token_info = await self.create_token(
                room_name=room_info.name,
                is_owner=is_owner,
                user_name=user_name,
                exp_minutes=token_exp_minutes
            )
            
            return room_info, token_info
            
        except Exception as e:
            logger.error(f"Error creating room and token: {e}")
            raise
    
    def get_room_url(self, room_name: str) -> str:
        """
        Get the URL for a room.
        
        Args:
            room_name: Name of the room
            
        Returns:
            Room URL
        """
        # Daily room URLs follow a standard pattern
        return f"https://yourdomain.daily.co/{room_name}"