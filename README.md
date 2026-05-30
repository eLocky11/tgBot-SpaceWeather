# 🌌 tgBot-SpaceWeather

Telegram-бот для мониторинга космической погоды. Опрашивает [NASA DONKI API](https://api.nasa.gov/DONKI/notifications), фильтрует новые события и отправляет форматированные HTML-уведомления в Telegram-канал на русском языке.

Бот не работает как постоянный процесс — он запускается по расписанию (cron), выполняет один полный цикл и завершается.

> 📄 Этот файл создан Claude Code (claude-sonnet-4-6) по запросу владельца репозитория.

---

## Поддерживаемые события

| Код | Событие |
|-----|---------|
| `FLR` | Солнечная вспышка |
| `CME` | Корональный выброс массы |
| `IPS` | Межпланетная ударная волна |
| `MPC` | Прорыв магнитопаузы |
| `GST` | Геомагнитный шторм |
| `RBE` | Усиление радиационных поясов |
| `SEP` | Подъём энергичных частиц |

---

## Структура проекта

```
tgBot-SpaceWeather/
├── app.py                      # Точка входа, оркестровка цикла
├── requirements.txt
├── data/
│   └── db.db                   # SQLite-база (создаётся автоматически)
├── logs.log                    # Лог-файл (создаётся автоматически)
└── src/
    ├── keys.py                 # Вся конфигурация и токены
    ├── donki.py                # HTTP-клиент к NASA DONKI API
    ├── database.py             # Работа с SQLite (дедупликация)
    ├── formatter.py            # Парсинг событий + подбор шаблона
    ├── notifier.py             # Отправка сообщений в Telegram
    └── templates/
        └── templates.py        # Jinja2 HTML-шаблоны для каждого типа событий
```

---

## Как работает бот

Каждый запуск проходит по следующей цепочке:

```
NASA DONKI API
      │
      ▼
  1. Fetch         — async-запрос к DONKI через aiohttp
      │
      ▼
  2. Deduplicate   — проверка messageID в SQLite, пропуск уже отправленных
      │
      ▼
  3. Format        — regex-парсинг messageBody, рендер Jinja2-шаблона
      │
      ▼
  4. Send          — отправка HTML-сообщения через python-telegram-bot
      │
      ▼
  5. Persist       — запись messageID в БД, удаление записей старше 180 дней
```

### Детали реализации

- **`src/keys.py`** — единственное место, где хранятся токены, chat ID, API-ключ и URL. Все модули получают значения через явную передачу из `app.py`.
- **`src/donki.py`** — два метода: `fetch()` (синхронный, не используется в основном цикле) и `new_fetch()` (асинхронный, активный).
- **`src/database.py`** — SQLite с WAL-режимом. Таблица `events` хранит `messageID`, тело сообщения и дату отправки. Метод `remove_old_events()` автоматически чистит записи старше 180 дней.
- **`src/formatter.py`** — статический класс `Formatter`. Метод `extract_context()` извлекает поля из текстового тела события регулярными выражениями; `get_template()` возвращает нужный Jinja2-шаблон по типу события.
- **`src/templates/templates.py`** — шаблоны на русском языке в HTML-режиме Telegram. Класс `DefaultUndefined` подставляет `"Неизвестно"` вместо любой незаполненной переменной, предотвращая ошибки рендера.
- **`src/notifier.py`** — наследуется от `telegram.Bot`, оборачивает `send_message` с логированием.

---

## Установка и запуск

### Требования

- Python 3.10+
- Доступ к интернету (NASA API + Telegram API)

### Установка

```bash
git clone https://github.com/eLocky11/tgBot-SpaceWeather.git
cd tgBot-SpaceWeather
pip install -r requirements.txt
```

### Конфигурация

Все настройки задаются в `src/keys.py`:

```python
TELEGRAM_TOKEN = "..."      # Токен бота от @BotFather
TG_CHAT_ID     = "..."      # ID основного канала/чата
TG_TEST_ID     = "..."      # ID тестового чата
NASA_API_KEY   = "..."      # Ключ NASA API (бесплатно на api.nasa.gov)
DB_PATH        = "data/db.db"
DONKI_URL      = "https://api.nasa.gov/DONKI/notifications"
```

### Запуск

```bash
# Продакшн (пишет в data/db.db, шлёт в TG_CHAT_ID)
python app.py

# Тестовый режим (in-memory БД, шлёт в TG_TEST_ID)
python app.py test
```

В тестовом режиме состояние не сохраняется между запусками — удобно для отладки шаблонов и парсинга.

### Запуск по расписанию (cron)

```cron
# Запуск каждые 30 минут
*/30 * * * * /usr/bin/python3 /path/to/tgBot-SpaceWeather/app.py
```

---

## Добавление нового типа событий

Нужно сделать три изменения синхронно:

1. **Шаблон** — добавить `XXX_TEMPLATE = Template(...)` в `src/templates/templates.py`
2. **Парсинг** — добавить ветку `elif ev["messageType"] == "XXX":` в `Formatter.extract_context()` в `src/formatter.py`
3. **Маппинг** — добавить `"XXX": XXX_TEMPLATE` в словарь в `Formatter.get_template()`

---

## Дальнейшие планы

- [ ] **Supabase** — миграция с локального SQLite на Supabase Postgres для облачного хранения состояния и возможности деплоя без постоянного сервера
- [ ] **GitHub Actions** — скрипт для удалённого запуска бота по расписанию (`schedule: cron`) без необходимости держать собственный сервер
