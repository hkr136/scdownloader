"""Telegram bot command and message handlers."""

import asyncio
from io import BytesIO
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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


# Caption footer added to every sent track
CAPTION_FOOTER = "@scdownlbot - download music from soundcloud"


def build_track_caption(artist: str, title: str, index: int | None = None, total: int | None = None) -> str:
    # Build Telegram caption for an audio/document message.
    # Ensures a consistent footer and respects Telegram caption length limits.
    artist = artist or 'Unknown Artist'
    title = title or 'Unknown Title'

    if index is not None and total is not None:
        head = f"🎵 {index}/{total}: {artist} - {title}"
    else:
        head = f"🎵 {artist} - {title}"

    caption = head + "\n\n" + CAPTION_FOOTER

    # Telegram caption limit is 1024 chars (safe for audio/document)
    if len(caption) > 1024:
        # Preserve footer and trim the head
        max_head = 1024 - (len(CAPTION_FOOTER) + 2)  # 2 newlines
        if max_head <= 1:
            return CAPTION_FOOTER[:1024]
        head_trunc = head[: max_head - 1] + "…"
        caption = head_trunc + "\n\n" + CAPTION_FOOTER
        caption = caption[:1024]

    return caption



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_message = """
🎵 <b>Привет! Я SoundCloud Downloader Bot</b>

Отправь мне ссылку на трек или плейлист с SoundCloud, и я скачаю его для тебя!

<b>Команды:</b>
/start - Показать это сообщение
/help - Помощь

<b>Как использовать:</b>
Просто отправь ссылку на трек или плейлист, например:
• https://soundcloud.com/artist/track-name
• https://soundcloud.com/artist/sets/playlist-name

<b>Возможности:</b>
✅ Скачивание треков и плейлистов
✅ Обложка встраивается в метаданные
✅ Автоматическое удаление служебных сообщений

⚠️ <b>Важно:</b>
• Контент должен быть публично доступен
• Максимальный размер файла: {max_size}MB
• Максимум 50 треков в плейлисте
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

<b>Как скачать плейлист:</b>
1. Найди плейлист на soundcloud.com
2. Скопируй ссылку на плейлист (обычно содержит /sets/)
3. Отправь ссылку мне
4. Бот скачает все треки по очереди

<b>Поддерживаемые форматы ссылок:</b>
• https://soundcloud.com/artist/track - трек
• https://soundcloud.com/artist/sets/playlist - плейлист

<b>Ограничения:</b>
• Только публичный контент
• Максимум {max_size}MB на файл
• Максимум 50 треков в плейлисте
• Лимит запросов: {rate_limit} в минуту

<b>Проблемы?</b>
• Проверь, что ссылка правильная
• Убедись, что контент доступен публично
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


async def handle_track(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    track_info: Dict,
    settings: Settings,
    messages_to_delete: list
):
    """
    Handle downloading a single track.
    
    Args:
        update: Telegram update
        context: Telegram context
        track_info: Track information dictionary
        settings: Bot settings
        messages_to_delete: List of messages to delete after sending
    """
    user_id = update.effective_user.id
    status_message = messages_to_delete[0] if messages_to_delete else None
    
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
    
    if status_message:
        await status_message.edit_text(
            info_text + "\n⬇️ Начинаю загрузку...",
            parse_mode=ParseMode.HTML
        )
    
    # Get stream URL
    async with SoundCloudClient(
        client_ids=settings.soundcloud_client_ids,
        rate_limit=settings.rate_limit,
        rotation_strategy=settings.client_id_rotation_strategy,
        cooldown_seconds=settings.client_id_cooldown_seconds
    ) as client:
        stream_url = await client.get_stream_url(track_info)
        
        if not stream_url:
            if status_message:
                await status_message.edit_text(
                    "❌ Не удалось получить ссылку для загрузки.\n"
                    "Трек может быть недоступен для стриминга."
                )
            return
    
    # Download track
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    
    downloader = AsyncAudioDownloader(
        settings.temp_directory,
        settings.max_file_size_mb
    )
    playlist_thumb = None  # (bytes, mime) cached for fallback artwork
    
    # Progress callback
    last_percent = 0
    async def progress_callback(current: int, total: int):
        nonlocal last_percent
        if total > 0 and status_message:
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
    
    # Download and embed artwork
    thumb_file = None
    if track_info.get('artwork_url') and status_message:
        await status_message.edit_text(
            info_text + "\n🖼 Добавляю обложку...",
            parse_mode=ParseMode.HTML
        )
        artwork = await downloader.download_artwork(track_info['artwork_url'])
        if artwork:
            artwork_data, artwork_mime = artwork
            # Create Telegram thumbnail (Telegram often ignores embedded ID3 cover)
            ext = 'png' if artwork_mime == 'image/png' else 'jpg'
            thumb_file = InputFile(BytesIO(artwork_data), filename=f'cover.{ext}')
            downloader.embed_metadata(file_path, track_info, artwork_data, artwork_mime=artwork_mime)
        else:
            downloader.embed_metadata(file_path, track_info)
    else:
        downloader.embed_metadata(file_path, track_info)
    
    if status_message:
        await status_message.edit_text(
            info_text + "\n📤 Отправляю файл...",
            parse_mode=ParseMode.HTML
        )
    
    # Send audio file
    try:
        with open(file_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=track_info['title'],
                performer=track_info['artist'],
                duration=int(track_info['duration'] / 1000),
                caption=build_track_caption(track_info.get('artist'), track_info.get('title')),

                thumbnail=thumb_file,
                read_timeout=60,
                write_timeout=60
            )
        
        # Clean up
        file_path.unlink(missing_ok=True)
        
        # Delete all messages related to this track
        for msg in messages_to_delete:
            try:
                await msg.delete()
            except Exception as del_error:
                logger.debug(f"Could not delete message: {del_error}")
        
        logger.info(f"Successfully sent track to user {user_id}")
        
    except Exception as send_error:
        logger.error(f"Failed to send audio file: {send_error}")
        # Clean up file even if sending failed
        file_path.unlink(missing_ok=True)
        
        # Try to send as document if audio fails
        try:
            if status_message:
                await status_message.edit_text(
                    "⚠️ Не удалось отправить как аудио, отправляю как файл..."
                )
            with open(file_path, 'rb') as doc_file:
                await update.message.reply_document(
                    document=doc_file,
                    filename=f"{track_info['artist']} - {track_info['title']}.mp3",
                    caption=build_track_caption(track_info.get('artist'), track_info.get('title')),

                    thumbnail=thumb_file,
                    read_timeout=60,
                    write_timeout=60
                )
            
            # Delete all messages related to this track
            for msg in messages_to_delete:
                try:
                    await msg.delete()
                except Exception as del_error:
                    logger.debug(f"Could not delete message: {del_error}")
            
            logger.info(f"Sent as document to user {user_id}")
        except Exception as doc_error:
            logger.error(f"Failed to send as document: {doc_error}")
            if status_message:
                await status_message.edit_text(
                    "❌ Не удалось отправить файл.\n"
                    "Возможно, файл слишком большой или проблемы с сетью."
                )


async def handle_playlist(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    playlist_info: Dict,
    settings: Settings,
    messages_to_delete: list
):
    """
    Handle downloading a playlist.
    
    Args:
        update: Telegram update
        context: Telegram context
        playlist_info: Playlist information dictionary
        settings: Bot settings
        messages_to_delete: List of messages to delete after sending
    """
    user_id = update.effective_user.id
    tracks = playlist_info['tracks']
    total_tracks = len(tracks)
    
    if total_tracks == 0:
        await update.message.reply_text("❌ Плейлист пуст!")
        return
    
    # Limit playlist size for safety
    MAX_PLAYLIST_SIZE = 50
    if total_tracks > MAX_PLAYLIST_SIZE:
        await update.message.reply_text(
            f"❌ Плейлист слишком большой ({total_tracks} треков).\n"
            f"Максимум: {MAX_PLAYLIST_SIZE} треков."
        )
        return
    
    # Send initial message
    status_message = messages_to_delete[0] if messages_to_delete else None
    if status_message:
        await status_message.edit_text(
            f"📀 <b>Плейлист:</b> {playlist_info['title']}\n"
            f"👤 <b>Автор:</b> {playlist_info['user']}\n"
            f"🎵 <b>Треков:</b> {total_tracks}\n\n"
            f"⏳ Начинаю загрузку...",
            parse_mode=ParseMode.HTML
        )
    
    client = SoundCloudClient(
        client_ids=settings.soundcloud_client_ids,
        rate_limit=settings.rate_limit,
        rotation_strategy=settings.client_id_rotation_strategy,
        cooldown_seconds=settings.client_id_cooldown_seconds
    )
    downloader = AsyncAudioDownloader(settings.temp_directory, settings.max_file_size_mb)
    
    successful = 0
    failed = 0
    
    for idx, track_info in enumerate(tracks, 1):
        try:
            # Update status
            if status_message:
                await status_message.edit_text(
                    f"📀 <b>Плейлист:</b> {playlist_info['title']}\n"
                    f"🎵 <b>Трек {idx}/{total_tracks}</b>\n\n"
                    f"▶️ {track_info.get('artist')} - {track_info.get('title')}\n"
                    f"⏳ Загружаю...",
                    parse_mode=ParseMode.HTML
                )
            
            # Get stream URL
            stream_url = await client.get_stream_url(track_info)
            if not stream_url:
                logger.warning(f"Could not get stream URL for track {idx}")
                failed += 1
                continue
            
            # Ensure artist and title are not None
            artist = track_info.get('artist') or 'Unknown Artist'
            title = track_info.get('title') or 'Unknown Title'
            
            logger.info(f"Downloading track {idx}/{total_tracks}: {artist} - {title}")
            
            # Download track
            file_path = await downloader.download_track(
                stream_url,
                artist,
                title
            )
            
            # Download and embed artwork
            thumb_file = None
            artwork_url = track_info.get('artwork_url') or playlist_info.get('artwork_url')
            
            if artwork_url:
                # Cache playlist artwork if used as fallback
                if not track_info.get('artwork_url') and playlist_thumb is not None:
                    artwork = playlist_thumb
                else:
                    artwork = await downloader.download_artwork(artwork_url)
                    if artwork and not track_info.get('artwork_url'):
                        playlist_thumb = artwork
                if artwork:
                    artwork_data, artwork_mime = artwork
                    ext = 'png' if artwork_mime == 'image/png' else 'jpg'
                    thumb_file = InputFile(BytesIO(artwork_data), filename=f'cover.{ext}')
                    downloader.embed_metadata(file_path, track_info, artwork_data, artwork_mime=artwork_mime)
                else:
                    logger.warning(f"Artwork download failed for track {idx}, embedding metadata without artwork")
                    downloader.embed_metadata(file_path, track_info)
            else:
                logger.warning(f"No artwork URL for track {idx}: {title}")
                downloader.embed_metadata(file_path, track_info)
            
            # Send file
            logger.info(f"Sending track {idx} to Telegram: {artist} - {title}")
            with open(file_path, 'rb') as audio:
                await update.message.reply_audio(
                    audio=audio,
                    title=title,
                    performer=artist,
                    duration=int(track_info['duration'] / 1000) if track_info.get('duration') else None,
                    caption=build_track_caption(artist, title, idx, total_tracks),

                    thumbnail=thumb_file,
                    read_timeout=60,
                    write_timeout=60
                )
            
            # Clean up file
            file_path.unlink(missing_ok=True)
            successful += 1
            
            logger.info(f"Successfully sent track {idx}/{total_tracks} to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to download/send track {idx}: {e}")
            failed += 1
            continue
    
    # Send final message and then delete it
    if status_message:
        await status_message.edit_text(
            f"✅ <b>Загрузка завершена!</b>\n\n"
            f"📀 <b>Плейлист:</b> {playlist_info['title']}\n"
            f"✅ <b>Успешно:</b> {successful}\n"
            f"❌ <b>Ошибок:</b> {failed}",
            parse_mode=ParseMode.HTML
        )
        
        # Wait a moment so user can see the final message
        await asyncio.sleep(3)
        
        # Delete all service messages including final status
        for msg in messages_to_delete:
            try:
                await msg.delete()
            except Exception as del_error:
                logger.debug(f"Could not delete message: {del_error}")
    
    await client.close()


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle SoundCloud URL messages."""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    logger.info(f"Received URL from user {user_id} ({username}): {url}")
    
    # List to track all messages to delete after sending file
    messages_to_delete = []
    
    # Validate URL
    if not validate_url(url):
        await update.message.reply_text(
            "❌ Неправильная ссылка!\n\n"
            "Отправь правильную ссылку на трек или плейлист с SoundCloud, например:\n"
            "https://soundcloud.com/artist/track-name\n"
            "https://soundcloud.com/artist/sets/playlist-name"
        )
        return
    
    # Get settings
    settings: Settings = context.bot_data['settings']
    
    # Send initial status
    status_message = await update.message.reply_text(
        "🔍 Получаю информацию..."
    )
    messages_to_delete.append(status_message)
    
    try:
        # Determine content type (track or playlist)
        async with SoundCloudClient(
            client_ids=settings.soundcloud_client_ids,
            rate_limit=settings.rate_limit,
            rotation_strategy=settings.client_id_rotation_strategy,
            cooldown_seconds=settings.client_id_cooldown_seconds
        ) as client:
            data = await client.resolve_url(url)
            
            if not data:
                await status_message.edit_text(
                    "❌ Не удалось получить информацию.\n"
                    "Убедитесь, что ссылка доступна публично."
                )
                return
            
            content_kind = data.get('kind')
            logger.info(f"Content type: {content_kind}")
            
            if content_kind == 'track':
                # Handle single track
                track_info = await client.get_track_info(url)
                if not track_info:
                    await status_message.edit_text(
                        "❌ Не удалось получить информацию о треке.\n"
                        "Убедитесь, что трек доступен публично."
                    )
                    return
                
                await handle_track(update, context, track_info, settings, messages_to_delete)
                
            elif content_kind in ['playlist', 'system-playlist']:
                # Handle playlist
                playlist_info = await client.get_playlist_info(url)
                if not playlist_info:
                    await status_message.edit_text(
                        "❌ Не удалось получить информацию о плейлисте.\n"
                        "Убедитесь, что плейлист доступен публично."
                    )
                    return
                
                await handle_playlist(update, context, playlist_info, settings, messages_to_delete)
                
            else:
                await status_message.edit_text(
                    f"❌ Неподдерживаемый тип контента: {content_kind}\n\n"
                    f"Бот поддерживает только треки и плейлисты."
                )
        
    except DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_message.edit_text(f"❌ Ошибка загрузки: {e}")
    except SoundCloudAPIError as e:
        logger.error(f"API error: {e}")
        await status_message.edit_text(f"❌ Ошибка API: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        try:
            await status_message.edit_text(
                "❌ Произошла непредвиденная ошибка.\n"
                "Попробуйте позже."
            )
        except:
            pass  # If we can't even edit the message, just log it


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-URL text messages."""
    await update.message.reply_text(
        "🤔 Отправь мне ссылку на трек или плейлист с SoundCloud!\n\n"
        "Например:\n"
        "• https://soundcloud.com/artist/track-name\n"
        "• https://soundcloud.com/artist/sets/playlist-name\n\n"
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
