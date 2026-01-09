"""Configuration settings for Telegram bot."""

import os
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv


class Settings:
    """Bot configuration settings."""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize settings from environment variables.
        
        Args:
            env_file: Optional path to .env file
        """
        # Load environment variables
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        # Telegram Bot
        self.bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
        
        # SoundCloud API
        self.soundcloud_client_id: str = os.getenv('SOUNDCLOUD_CLIENT_ID', '')
        
        # Download settings
        self.download_directory: Path = Path(
            os.getenv('DOWNLOAD_DIRECTORY', './downloads')
        )
        self.temp_directory: Path = Path(
            os.getenv('TEMP_DIRECTORY', './temp')
        )
        self.max_file_size_mb: int = int(os.getenv('MAX_FILE_SIZE_MB', '50'))
        self.max_concurrent_downloads: int = int(
            os.getenv('MAX_CONCURRENT_DOWNLOADS', '5')
        )
        self.download_timeout: int = int(os.getenv('DOWNLOAD_TIMEOUT', '300'))
        
        # Logging settings
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file: Optional[str] = os.getenv('LOG_FILE', 'bot.log')
        
        # Rate limiting
        self.rate_limit: int = int(os.getenv('RATE_LIMIT', '60'))
        self.user_rate_limit: int = int(os.getenv('USER_RATE_LIMIT', '10'))
        
        # Admin users
        admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
        self.admin_user_ids: List[int] = [
            int(uid.strip()) for uid in admin_ids_str.split(',') 
            if uid.strip()
        ]
        
        # Ensure directories exist
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.temp_directory.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration settings.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is not set")
        
        if not self.soundcloud_client_id:
            errors.append("SOUNDCLOUD_CLIENT_ID is not set")
        
        if self.max_file_size_mb < 1:
            errors.append("MAX_FILE_SIZE_MB must be at least 1")
        
        if self.max_concurrent_downloads < 1:
            errors.append("MAX_CONCURRENT_DOWNLOADS must be at least 1")
        
        if self.rate_limit < 1:
            errors.append("RATE_LIMIT must be at least 1")
        
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_log_levels:
            errors.append(f"LOG_LEVEL must be one of {valid_log_levels}")
        
        return (len(errors) == 0, errors)
    
    def __repr__(self) -> str:
        """String representation of settings (excluding sensitive data)."""
        return (
            f"Settings(download_directory={self.download_directory}, "
            f"max_file_size_mb={self.max_file_size_mb}, "
            f"log_level={self.log_level})"
        )
