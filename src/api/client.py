"""Async SoundCloud API client for fetching track information."""

import time
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from urllib.parse import urljoin

from ..utils.logger import setup_logger
from ..utils.validators import validate_url


class SoundCloudAPIError(Exception):
    """Custom exception for SoundCloud API errors."""
    pass


class SoundCloudClient:
    """Async client for interacting with SoundCloud API."""
    
    API_BASE_URL = "https://api-v2.soundcloud.com"
    
    def __init__(self, client_id: str, rate_limit: int = 60):
        """
        Initialize SoundCloud API client.
        
        Args:
            client_id: SoundCloud API client ID
            rate_limit: Maximum requests per minute
        """
        if not client_id:
            raise ValueError("Client ID is required")
        
        self.client_id = client_id
        self.rate_limit = rate_limit
        self.logger = setup_logger()
        
        # Rate limiting
        self._request_times: list[float] = []
        self._rate_limit_lock = asyncio.Lock()
        
        # Session will be created when needed
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
        return self._session
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        async with self._rate_limit_lock:
            current_time = time.time()
            
            # Remove requests older than 1 minute
            self._request_times = [
                t for t in self._request_times 
                if current_time - t < 60
            ]
            
            # Wait if rate limit exceeded
            if len(self._request_times) >= self.rate_limit:
                sleep_time = 60 - (current_time - self._request_times[0])
                if sleep_time > 0:
                    self.logger.warning(f"Rate limit reached. Waiting {sleep_time:.2f} seconds...")
                    await asyncio.sleep(sleep_time)
                    self._request_times.clear()
            
            self._request_times.append(current_time)
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """
        Make an async API request with rate limiting.
        
        Args:
            endpoint: API endpoint
            params: Optional query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            SoundCloudAPIError: If request fails
        """
        await self._check_rate_limit()
        
        if params is None:
            params = {}
        
        params['client_id'] = self.client_id
        
        url = urljoin(self.API_BASE_URL, endpoint)
        session = await self._get_session()
        
        try:
            self.logger.debug(f"Making request to: {url}")
            async with session.get(url, params=params, timeout=30) as response:
                response.raise_for_status()
                return await response.json()
                
        except aiohttp.ClientError as e:
            self.logger.error(f"API request failed: {e}")
            raise SoundCloudAPIError(f"Failed to fetch data from SoundCloud: {e}")
        except asyncio.TimeoutError:
            self.logger.error("API request timed out")
            raise SoundCloudAPIError("Request timed out")
    
    async def resolve_url(self, url: str) -> Dict[Any, Any]:
        """
        Resolve a SoundCloud URL to get track information.
        
        Args:
            url: SoundCloud track URL
            
        Returns:
            Track information dictionary
            
        Raises:
            ValueError: If URL is invalid
            SoundCloudAPIError: If API request fails
        """
        if not validate_url(url):
            raise ValueError(f"Invalid SoundCloud URL: {url}")
        
        self.logger.info(f"Resolving URL: {url}")
        
        try:
            data = await self._make_request('/resolve', {'url': url})
            return data
            
        except SoundCloudAPIError as e:
            self.logger.error(f"Failed to resolve URL: {e}")
            raise
    
    async def get_track_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed track information from URL.
        
        Args:
            url: SoundCloud track URL
            
        Returns:
            Dictionary with track information or None if failed
        """
        try:
            data = await self.resolve_url(url)
            
            if data.get('kind') != 'track':
                self.logger.error(f"URL does not point to a track: {url}")
                return None
            
            track_info = {
                'id': data.get('id'),
                'title': data.get('title'),
                'artist': data.get('user', {}).get('username'),
                'duration': data.get('duration'),  # in milliseconds
                'genre': data.get('genre'),
                'description': data.get('description'),
                'artwork_url': data.get('artwork_url'),
                'stream_url': data.get('media', {}).get('transcodings', []),
                'created_at': data.get('created_at'),
                'permalink_url': data.get('permalink_url'),
            }
            
            self.logger.info(f"Retrieved track: {track_info['artist']} - {track_info['title']}")
            return track_info
            
        except (SoundCloudAPIError, ValueError) as e:
            self.logger.error(f"Failed to get track info: {e}")
            return None
    
    async def get_stream_url(self, track_info: Dict[str, Any]) -> Optional[str]:
        """
        Get the actual stream URL for downloading.
        
        Args:
            track_info: Track information dictionary
            
        Returns:
            Stream URL or None if not available
        """
        transcodings = track_info.get('stream_url', [])
        
        if not transcodings:
            self.logger.error("No stream URLs available for this track")
            return None
        
        # Try to find progressive (direct download)
        for transcoding in transcodings:
            format_protocol = transcoding.get('format', {}).get('protocol', '')
            
            if format_protocol == 'progressive':
                stream_url = transcoding.get('url')
                if stream_url:
                    try:
                        media_data = await self._make_request(stream_url, {})
                        return media_data.get('url')
                    except SoundCloudAPIError:
                        continue
        
        # Fallback to first available
        if transcodings:
            stream_url = transcodings[0].get('url')
            if stream_url:
                try:
                    media_data = await self._make_request(stream_url, {})
                    return media_data.get('url')
                except SoundCloudAPIError:
                    pass
        
        return None
    
    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
