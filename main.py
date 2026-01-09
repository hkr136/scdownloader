#!/usr/bin/env python3
"""Main entry point for SoundCloud Telegram Bot."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import Settings
from src.bot.bot import SoundCloudBot
from src.utils.logger import setup_logger


async def main():
    """Main function to run the bot."""
    # Load settings
    try:
        settings = Settings()
        logger = setup_logger(
            level=settings.log_level,
            log_file=settings.log_file
        )
        
        logger.info("=" * 60)
        logger.info("SoundCloud Telegram Bot")
        logger.info("=" * 60)
        
        # Validate configuration
        is_valid, errors = settings.validate()
        if not is_valid:
            logger.error("Configuration errors:")
            for error in errors:
                logger.error(f"  ❌ {error}")
            logger.error("\nPlease check your .env file!")
            sys.exit(1)
        
        logger.info("✅ Configuration validated successfully")
        logger.info(f"📁 Download directory: {settings.download_directory}")
        logger.info(f"📁 Temp directory: {settings.temp_directory}")
        logger.info(f"💾 Max file size: {settings.max_file_size_mb}MB")
        logger.info("")
        
        # Create and run bot
        bot = SoundCloudBot(settings)
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
