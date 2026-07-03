<h3 align="center">
  <img src="https://img.shields.io/badge/status-active-success?style=flat-square" alt="status">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/python-3.8%2B-lightgrey?style=flat-square" alt="python">
</h3>

# SoundCloud Telegram Bot

Telegram бот для скачивания треков с SoundCloud.

## Features

- Скачивание треков и плейлистов (до 50 треков)
- Автоматическое встраивание обложек в метаданные
- Автоматическое удаление служебных сообщений
- Асинхронная обработка запросов
- Docker поддержка

## Requirements

- Python 3.8+
- Telegram Bot Token
- SoundCloud Client ID

## Installation

```bash
git clone https://github.com/hkr136/scdownloader.git
cd scdownloader
cp .env.example .env
# Заполните токены в .env
./run.sh
```

Docker:

```bash
docker-compose up -d
```

## Configuration

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| TELEGRAM_BOT_TOKEN | Токен бота | Обязательно |
| SOUNDCLOUD_CLIENT_ID | SoundCloud API | Обязательно |
| MAX_FILE_SIZE_MB | Макс. размер файла | 50 |
| MAX_CONCURRENT_DOWNLOADS | Одновременные загрузки | 5 |

## Commands

- `/start` — начать работу
- `/help` — справка

## License

MIT — см. [LICENSE](LICENSE)

## Author

[hkr136](https://github.com/hkr136)