"""Async downloader for audio files."""

import aiohttp
import aiofiles
from pathlib import Path
from typing import Optional, Callable
import asyncio

from ..utils.logger import setup_logger
from ..utils.validators import sanitize_filename


class DownloadError(Exception):
    """Custom exception for download errors."""
    pass


class AsyncAudioDownloader:
    """Handles async downloading of audio files."""
    
    def __init__(self, output_dir: Path, max_file_size_mb: int = 50):
        """
        Initialize audio downloader.
        
        Args:
            output_dir: Directory to save downloaded files
            max_file_size_mb: Maximum file size in MB
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.logger = setup_logger()
    
    async def download(
        self,
        url: str,
        filename: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """
        Download a file from URL asynchronously.
        
        Args:
            url: Download URL
            filename: Desired filename (will be sanitized)
            progress_callback: Optional callback for progress updates (current, total)
            
        Returns:
            Path to downloaded file
            
        Raises:
            DownloadError: If download fails
        """
        if not url:
            raise DownloadError("Download URL is empty")
        
        # Sanitize filename
        safe_filename = sanitize_filename(filename)
        if not safe_filename.endswith('.mp3'):
            safe_filename += '.mp3'
        
        output_path = self.output_dir / safe_filename
        
        self.logger.info(f"Downloading to: {output_path}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    
                    # Check file size
                    if total_size > self.max_file_size_bytes:
                        raise DownloadError(
                            f"File too large: {total_size / 1024 / 1024:.2f}MB "
                            f"(max: {self.max_file_size_bytes / 1024 / 1024:.2f}MB)"
                        )
                    
                    # Download with progress
                    downloaded = 0
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if chunk:
                                await f.write(chunk)
                                downloaded += len(chunk)
                                
                                if progress_callback:
                                    progress_callback(downloaded, total_size)
            
            self.logger.info(f"Successfully downloaded: {output_path}")
            return output_path
            
        except aiohttp.ClientError as e:
            self.logger.error(f"Download failed: {e}")
            # Clean up partial download
            if output_path.exists():
                output_path.unlink()
            raise DownloadError(f"Failed to download file: {e}")
        except asyncio.TimeoutError:
            self.logger.error("Download timed out")
            if output_path.exists():
                output_path.unlink()
            raise DownloadError("Download timed out")
        except Exception as e:
            self.logger.error(f"Unexpected error during download: {e}")
            if output_path.exists():
                output_path.unlink()
            raise DownloadError(f"Unexpected error: {e}")
    
    async def download_track(
        self,
        stream_url: str,
        artist: str,
        title: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """
        Download a track with proper naming.
        
        Args:
            stream_url: URL to download from
            artist: Track artist name
            title: Track title
            progress_callback: Optional callback for progress updates
            
        Returns:
            Path to downloaded file
        """
        # Create filename from artist and title
        filename = f"{artist} - {title}"
        return await self.download(stream_url, filename, progress_callback)
