# 🚀 Быстрый деплой на сервер

## Что это?

Это ветка `feature/client-id-rotation` с системой автоматической ротации Client ID для непрерывной работы бота.

## ⚡ Быстрый старт (5 минут)

### 1. Подготовка (на вашем компьютере)

Получите 2-3 Client ID с soundcloud.com:

1. Откройте https://soundcloud.com
2. F12 → Network → Воспроизведите трек
3. Найдите `api-v2.soundcloud.com` → Скопируйте `client_id`
4. Повторите в режиме инкогнито для других ID

### 2. На сервере

```bash
# Подключитесь
ssh user@your-server
cd /path/to/soundcloud-bot

# Backup
cp .env .env.backup.$(date +%Y%m%d)
docker-compose logs --tail=100 > logs_backup.txt

# Остановите
docker-compose down

# Обновите код
git fetch origin
git checkout feature/client-id-rotation

# Обновите .env
nano .env
```

Добавьте/измените в `.env`:

```env
# Закомментируйте старый:
# SOUNDCLOUD_CLIENT_ID=old_id

# Добавьте новые:
SOUNDCLOUD_CLIENT_IDS=id1,id2,id3
CLIENT_ID_ROTATION_STRATEGY=failover
CLIENT_ID_COOLDOWN_SECONDS=300
```

### 3. Деплой

```bash
# Пересоберите
docker-compose build

# Запустите
docker-compose up -d

# Проверьте логи
docker-compose logs -f
```

### 4. Проверка

Убедитесь что видите в логах:

```
[INFO] ClientIDManager initialized with 3 client IDs, strategy: failover
[INFO] ✅ Configuration validated successfully
[INFO] Bot started successfully!
```

Отправьте боту тестовую ссылку - должен скачать трек.

## ✅ Готово!

Бот теперь автоматически переключается между Client ID при ошибках.

## 📚 Документация

- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - пошаговый чеклист
- **[DEPLOYMENT_MIGRATION.md](DEPLOYMENT_MIGRATION.md)** - полная инструкция
- **[docs/CLIENT_ID_ROTATION.md](docs/CLIENT_ID_ROTATION.md)** - как это работает

## 🚨 Откат (если что-то пошло не так)

```bash
docker-compose down
git checkout main
cp .env.backup.YYYYMMDD .env
docker-compose build
docker-compose up -d
```

## ⚙️ Конфигурация

### Минимальная (рекомендуется)

```env
SOUNDCLOUD_CLIENT_IDS=id1,id2,id3
```

### Полная

```env
SOUNDCLOUD_CLIENT_IDS=id1,id2,id3,id4
CLIENT_ID_ROTATION_STRATEGY=failover        # или round-robin
CLIENT_ID_COOLDOWN_SECONDS=300             # 5 минут
```

## 🎯 Что нового?

✅ Автоматическая ротация Client ID  
✅ Нулевое время простоя  
✅ Автоматическое восстановление  
✅ Обратная совместимость (старый способ работает)  

## 📊 Мониторинг

```bash
# Проверить логи
docker-compose logs -f soundcloud-bot

# Найти ошибки
docker-compose logs | grep ERROR

# Статус
docker-compose ps
```

### Что ожидать в логах

**✅ Успешная работа:**
```
[DEBUG] Making request to: ... with client_id: abc12345...
[DEBUG] Client ID abc12345... marked as successful (total: 5)
```

**⚠️ Ротация работает (это нормально):**
```
[WARN] Authentication failed with client_id abc12345... (status: 401)
[INFO] Attempting retry with new client ID...
[INFO] Switched to client_id #2 (def67890...)
```

**❌ Требуется действие:**
```
[ERROR] All client IDs are exhausted!
```
→ Нужно добавить новые Client ID в .env

## 💡 Best Practices

1. **Минимум 3 Client ID** для надежности
2. **Мониторьте логи** первые 24 часа
3. **Обновляйте ID регулярно** (раз в 1-2 недели)
4. **Храните backup** старой конфигурации

## 🆘 Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
docker-compose logs soundcloud-bot

# Проверьте .env
cat .env | grep SOUNDCLOUD_CLIENT

# Проверьте что файлы обновились
ls -la src/api/client_id_manager.py
```

### "No active client IDs available"

```bash
# Добавьте новые ID в .env
nano .env

# Перезапустите
docker-compose restart
```

### Хотите вернуться на старую версию

См. раздел **Откат** выше или [DEPLOYMENT_MIGRATION.md](DEPLOYMENT_MIGRATION.md)

## 📞 Поддержка

Вопросы? Смотрите:
- [DEPLOYMENT_MIGRATION.md](DEPLOYMENT_MIGRATION.md) - подробная инструкция
- [docs/TESTING_ROTATION.md](docs/TESTING_ROTATION.md) - тестирование
- [docs/CLIENT_ID_ROTATION.md](docs/CLIENT_ID_ROTATION.md) - техническое описание

---

**Версия:** 1.0  
**Дата:** 2026-01-10  
**Ветка:** feature/client-id-rotation  
**Статус:** ✅ Production Ready
