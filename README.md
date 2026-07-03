<h3 align="center">
  <img src="https://img.shields.io/badge/AI%20Product%20Engineer-blue?style=flat-square">
  <img src="https://img.shields.io/badge/status-active-success?style=flat-square">
</h3>

# SoundCloud Telegram Bot

Telegram бот для скачивания треков с SoundCloud.

## Features

- Скачивание треков и плейлистов (до 50 треков)
- Автоматическое встраивание обложек в метаданные
- Асинхронная обработка запросов
- Docker поддержка

## Tech Stack

Python, Telegram Bot API, REST API

## Installation

```bash
git clone https://github.com/hkr136/scdownloader.git
cd scdownloader
cp .env.example .env
./run.sh
```

## Roadmap

- [ ] Статистика использования
- [ ] Кэширование треков

## License

MIT — см. [LICENSE](LICENSE)