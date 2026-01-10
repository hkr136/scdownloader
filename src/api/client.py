"""Async SoundCloud API client for fetching track information."""

import time
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

from ..utils.logger import setup_logger
from ..utils.validators import validate_url
from .client_id_manager import ClientIDManager


class SoundCloudAPIError(Exception):
    """Custom exception for SoundCloud API errors."""
    pass


class SoundCloudClient:
    """Async client for interacting with SoundCloud API."""
    
    API_BASE_URL = "https://api-v2.soundcloud.com"
    
    def __init__(
        self, 
        client_id: Optional[str] = None,
        client_ids: Optional[List[str]] = None,
        rate_limit: int = 60,
        rotation_strategy: str = 'failover',
        cooldown_seconds: int = 300
    ):
        """
        Initialize SoundCloud API client.
        
        Args:
            client_id: Single SoundCloud API client ID (deprecated, use client_ids)
            client_ids: List of SoundCloud API client IDs (recommended)
            rate_limit: Maximum requests per minute
            rotation_strategy: Strategy for rotating client IDs ('failover' or 'round-robin')
            cooldown_seconds: Cooldown period for failed client IDs
        """
        self.logger = setup_logger()
        
        # Initialize ClientIDManager
        if client_ids:
            self.id_manager = ClientIDManager(
                client_ids=client_ids,
                strategy=rotation_strategy,
                cooldown_seconds=cooldown_seconds
            )
        elif client_id:
            # Backward compatibility: single client_id
            self.id_manager = ClientIDManager(
                client_ids=[client_id],
                strategy=rotation_strategy,
                cooldown_seconds=cooldown_seconds
            )
        else:
            raise ValueError("Either client_id or client_ids must be provided")
        
        self.current_client_id: Optional[str] = None
        self.rate_limit = rate_limit
        
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
    
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict] = None,
        retry: bool = True
    ) -> Dict[Any, Any]:
        """
        Make an async API request with rate limiting and automatic client ID rotation.
        
        Args:
            endpoint: API endpoint
            params: Optional query parameters
            retry: Whether to retry with a new client ID on auth failure
            
        Returns:
            JSON response as dictionary
            
        Raises:
            SoundCloudAPIError: If request fails
        """
        await self._check_rate_limit()
        
        if params is None:
            params = {}
        
        # Get current client ID if not set
        if self.current_client_id is None:
            self.current_client_id = await self.id_manager.get_active_id()
        
        params['client_id'] = self.current_client_id
        
        url = urljoin(self.API_BASE_URL, endpoint)
        session = await self._get_session()
        
        try:
            self.logger.debug(
                f"Making request to: {url} with client_id: "
                f"{self.current_client_id[:8]}..."
            )
            async with session.get(url, params=params, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Mark successful request
                await self.id_manager.mark_success(self.current_client_id)
                
                return data
                
        except aiohttp.ClientResponseError as e:
            # Check if it's an authentication error
            if e.status in (401, 403):
                self.logger.warning(
                    f"Authentication failed with client_id "
                    f"{self.current_client_id[:8]}... (status: {e.status})"
                )
                
                # Mark this client ID as failed
                await self.id_manager.mark_failed(self.current_client_id, e.status)
                
                # Retry with a new client ID if allowed
                if retry:
                    self.logger.info("Attempting retry with new client ID...")
                    self.current_client_id = None  # Force getting new ID
                    return await self._make_request(endpoint, params, retry=False)
                else:
                    self.logger.error("Retry failed, no more client IDs available")
                    raise SoundCloudAPIError(
                        f"Authentication failed (status: {e.status}). "
                        "All client IDs may be invalid."
                    )
            else:
                # Other HTTP errors
                self.logger.error(f"API request failed with status {e.status}: {e}")
                raise SoundCloudAPIError(
                    f"Failed to fetch data from SoundCloud (status: {e.status}): {e}"
                )
                
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
    
    async def get_playlist_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get playlist/set information from URL.
        
        Args:
            url: SoundCloud playlist/set URL
            
        Returns:
            Dictionary with playlist information or None if failed
        """
        try:
            data = await self.resolve_url(url)
            
            kind = data.get('kind')
            if kind not in ['playlist', 'system-playlist']:
                self.logger.error(f"URL does not point to a playlist: {url} (kind: {kind})")
                return None
            
            # Extract track information
            tracks = []
            for track_data in data.get('tracks', []):
                if track_data and track_data.get('kind') == 'track':
                    # Get full track info if stream_url is missing or data is incomplete
                    transcodings = track_data.get('media', {}).get('transcodings', [])
                    
                    # If no transcodings or missing user data, try to fetch full track data
                    if (not transcodings or not track_data.get('user')) and track_data.get('id'):
                        try:
                            self.logger.debug(f"Fetching full track data for track ID: {track_data.get('id')}")
                            full_track_data = await self._make_request(f'/tracks/{track_data.get("id")}')
                            # Use full data if available
                            if full_track_data:
                                track_data = full_track_data
                                transcodings = track_data.get('media', {}).get('transcodings', [])
                                self.logger.debug(f"Got full track data: {track_data.get('title')} by {track_data.get('user', {}).get('username')}")
                        except Exception as e:
                            self.logger.warning(f"Could not fetch full track data: {e}")
                    
                    track_info = {
                        'id': track_data.get('id'),
                        'title': track_data.get('title'),
                        'artist': track_data.get('user', {}).get('username') if track_data.get('user') else None,
                        'duration': track_data.get('duration'),
                        'genre': track_data.get('genre'),
                        'artwork_url': track_data.get('artwork_url'),
                        'stream_url': transcodings,
                        'created_at': track_data.get('created_at'),
                        'permalink_url': track_data.get('permalink_url'),
                    }
                    
                    # Log track info
                    self.logger.info(
                        f"Track: {track_info['title']} by {track_info['artist']}, "
                        f"artwork_url: {track_info['artwork_url']}"
                    )
                    
                    # Log if data is still incomplete
                    if not track_info['title'] or not track_info['artist']:
                        self.logger.warning(
                            f"Incomplete track data: title={track_info['title']}, "
                            f"artist={track_info['artist']}, id={track_info['id']}"
                        )
                    
                    tracks.append(track_info)
            
            playlist_info = {
                'id': data.get('id'),
                'title': data.get('title'),
                'user': data.get('user', {}).get('username'),
                'track_count': data.get('track_count', len(tracks)),
                'tracks': tracks,
                'artwork_url': data.get('artwork_url'),
                'description': data.get('description'),
                'created_at': data.get('created_at'),
            }
            
            self.logger.info(
                f"Retrieved playlist: {playlist_info['title']} "
                f"by {playlist_info['user']} ({len(tracks)} tracks)"
            )
            return playlist_info
            
        except (SoundCloudAPIError, ValueError) as e:
            self.logger.error(f"Failed to get playlist info: {e}")
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
