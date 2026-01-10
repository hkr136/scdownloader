"""Main Telegram bot class."""

import asyncio
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from ..config.settings import Settings
from ..utils.logger import setup_logger
from .handlers import setup_handlers


class SoundCloudBot:
    """Main SoundCloud Telegram Bot class."""
    
    def __init__(self, settings: Settings):
        """
        Initialize the bot.
        
        Args:
            settings: Bot configuration settings
        """
        self.settings = settings
        self.logger = setup_logger(
            level=settings.log_level,
            log_file=settings.log_file
        )
        self.application: Application = None
    
    def build_application(self) -> Application:
        """
        Build and configure the telegram application.
        
        Returns:
            Configured Application instance
        """
        # Build application
        builder = ApplicationBuilder()
        builder.token(self.settings.bot_token)
        
        # Configure concurrent updates
        builder.concurrent_updates(True)
        
        # Increase timeouts for large file uploads
        builder.read_timeout(60)
        builder.write_timeout(60)
        builder.connect_timeout(30)
        builder.pool_timeout(30)
        
        self.application = builder.build()
        
        # Setup handlers
        setup_handlers(self.application, self.settings)
        
        self.logger.info("Bot application built successfully")
        return self.application
    
    async def start(self):
        """Start the bot."""
        self.logger.info("Starting SoundCloud Telegram Bot...")
        
        # Validate settings
        is_valid, errors = self.settings.validate()
        if not is_valid:
            self.logger.error("Configuration errors:")
            for error in errors:
                self.logger.error(f"  - {error}")
            raise ValueError("Invalid configuration")
        
        # Build application
        if self.application is None:
            self.build_application()
        
        # Initialize and start
        await self.application.initialize()
        await self.application.start()
        
        self.logger.info("Bot started successfully!")
        self.logger.info("Press Ctrl+C to stop")
        
        # Start polling
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    
    async def stop(self):
        """Stop the bot."""
        self.logger.info("Stopping bot...")
        
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        self.logger.info("Bot stopped")
    
    async def run(self):
        """Run the bot until interrupted."""
        try:
            await self.start()
            
            # Keep running
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.exception(f"Bot error: {e}")
        finally:
            await self.stop()
