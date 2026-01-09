"""Telegram bot command and message handlers."""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode, ChatAction

from ..config.settings import Settings
from ..api.client import SoundCloudClient, SoundCloudAPIError
from ..api.downloader import AsyncAudioDownloader, DownloadError
from ..utils.validators import validate_url
from ..utils.logger import setup_logger


logger = setup_logger()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_message = """
🎵 <b>Привет! Я SoundCloud Downloader Bot</b>

Отправь мне ссылку на трек с SoundCloud, и я скачаю его для тебя!

<b>Команды:</b>
/start - Показать это сообщение
/help - Помощь
/stats - Статистика (скоро)

<b>Как использовать:</b>
Просто отправь ссылку на трек, например:
https://soundcloud.com/artist/track-name

⚠️ <b>Важно:</b>
• Трек должен быть публично доступен
• Максимальный размер файла: {max_size}MB
• Бот предназначен только для личного использования
"""
    
    settings: Settings = context.bot_data['settings']
    message = welcome_message.format(max_size=settings.max_file_size_mb)
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_message = """
<b>📖 Помощь</b>

<b>Как скачать трек:</b>
1. Найди трек на soundcloud.com
2. Скопируй ссылку на трек
3. Отправь ссылку мне
4. Дождись загрузки

<b>Поддерживаемые форматы ссылок:</b>
• https://soundcloud.com/artist/track
• https://www.soundcloud.com/artist/track
• https://m.soundcloud.com/artist/track

<b>Ограничения:</b>
• Только публичные треки
• Максимум {max_size}MB
• Лимит запросов: {rate_limit} в минуту

<b>Проблемы?</b>
• Проверь, что ссылка правильная
• Убедись, что трек доступен публично
• Попробуй снова через минуту

По вопросам: @your_username
"""
    
    settings: Settings = context.bot_data['settings']
    message = help_message.format(
        max_size=settings.max_file_size_mb,
        rate_limit=settings.user_rate_limit
    )
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle SoundCloud URL messages."""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    logger.info(f"Received URL from user {user_id} ({username}): {url}")
    
    # Validate URL
    if not validate_url(url):
        await update.message.reply_text(
            "❌ Неправильная ссылка!\n\n"
            "Отправь правильную ссылку на трек с SoundCloud, например:\n"
            "https://soundcloud.com/artist/track-name"
        )
        return
    
    # Get settings
    settings: Settings = context.bot_data['settings']
    
    # Send initial status
    status_message = await update.message.reply_text(
        "🔍 Получаю информацию о треке..."
    )
    
    try:
        # Get track info
        async with SoundCloudClient(settings.soundcloud_client_id, settings.rate_limit) as client:
            track_info = await client.get_track_info(url)
            
            if not track_info:
                await status_message.edit_text(
                    "❌ Не удалось получить информацию о треке.\n"
                    "Убедитесь, что трек доступен публично."
                )
                return
            
            # Display track info
            duration_sec = track_info['duration'] / 1000
            minutes = int(duration_sec // 60)
            seconds = int(duration_sec % 60)
            
            info_text = f"""
📊 <b>Информация о треке:</b>

🎵 <b>Название:</b> {track_info['title']}
👤 <b>Исполнитель:</b> {track_info['artist']}
⏱ <b>Длительность:</b> {minutes}:{seconds:02d}
"""
            if track_info.get('genre'):
                info_text += f"🎼 <b>Жанр:</b> {track_info['genre']}\n"
            
            await status_message.edit_text(
                info_text + "\n⬇️ Начинаю загрузку...",
                parse_mode=ParseMode.HTML
            )
            
            # Get stream URL
            stream_url = await client.get_stream_url(track_info)
            
            if not stream_url:
                await status_message.edit_text(
                    "❌ Не удалось получить ссылку для загрузки.\n"
                    "Трек может быть недоступен для стриминга."
                )
                return
        
        # Download track
        await update.message.chat.send_action(ChatAction.UPLOAD_AUDIO)
        
        downloader = AsyncAudioDownloader(
            settings.temp_directory,
            settings.max_file_size_mb
        )
        
        # Progress callback
        last_percent = 0
        async def progress_callback(current: int, total: int):
            nonlocal last_percent
            if total > 0:
                percent = int((current / total) * 100)
                # Update every 10%
                if percent >= last_percent + 10:
                    last_percent = percent
                    try:
                        await status_message.edit_text(
                            info_text + f"\n⬇️ Загрузка: {percent}%",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass  # Ignore rate limit errors
        
        file_path = await downloader.download_track(
            stream_url,
            track_info['artist'],
            track_info['title'],
            progress_callback
        )
        
        await status_message.edit_text(
            info_text + "\n📤 Отправляю файл...",
            parse_mode=ParseMode.HTML
        )
        
        # Send audio file
        with open(file_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=track_info['title'],
                performer=track_info['artist'],
                duration=int(track_info['duration'] / 1000),
                caption=f"🎵 {track_info['artist']} - {track_info['title']}"
            )
        
        # Clean up
        file_path.unlink(missing_ok=True)
        await status_message.delete()
        
        logger.info(f"Successfully sent track to user {user_id}")
        
    except DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_message.edit_text(f"❌ Ошибка загрузки: {e}")
    except SoundCloudAPIError as e:
        logger.error(f"API error: {e}")
        await status_message.edit_text(f"❌ Ошибка API: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        await status_message.edit_text(
            "❌ Произошла непредвиденная ошибка.\n"
            "Попробуйте позже."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-URL text messages."""
    await update.message.reply_text(
        "🤔 Отправь мне ссылку на трек с SoundCloud!\n\n"
        "Например:\n"
        "https://soundcloud.com/artist/track-name\n\n"
        "Используй /help для получения помощи."
    )


def setup_handlers(application: Application, settings: Settings):
    """
    Setup all bot handlers.
    
    Args:
        application: Telegram Application instance
        settings: Bot settings
    """
    # Store settings in bot_data
    application.bot_data['settings'] = settings
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Message handlers
    # URLs containing soundcloud.com
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r'soundcloud\.com'),
            handle_url
        )
    )
    
    # Other text messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )
    
    logger.info("Handlers registered successfully")
