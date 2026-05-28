# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A scheduled Telegram bot that polls [NASA's DONKI API](https://api.nasa.gov/DONKI/notifications) for space weather events (solar flares, geomagnetic storms, etc.) and sends formatted HTML notifications to a Telegram channel in Russian.

The bot is designed to be run on a cron schedule (not as a long-running process). Each invocation performs one full cycle: fetch → deduplicate → format → send → persist, then exits.

## Running the bot

```bash
# Install dependencies
pip install -r requirements.txt

# Production run (uses data/db.db and TG_CHAT_ID)
python app.py

# Test mode (uses in-memory SQLite and TG_TEST_ID chat)
python app.py test
```

There is no test suite and no linter configuration.

## Architecture

The pipeline lives entirely in `app.py`'s `BotApp.on_run()`:

1. **Fetch** — `DonkiClient.new_fetch()` hits the DONKI notifications endpoint asynchronously via `aiohttp`.
2. **Deduplicate** — Each event's `messageID` is checked against SQLite. Already-seen IDs are skipped. `Report` type events are always skipped.
3. **Format** — `Formatter.extract_context(ev)` parses the plain-text `messageBody` field with regex patterns to extract timestamps, intensity values, etc. `Formatter.get_template(msg_type)` returns the matching Jinja2 template.
4. **Send** — `TelegramNotifier.send_notification()` sends the rendered HTML string via `python-telegram-bot`.
5. **Persist** — Sent event IDs are stored in SQLite. Records older than 180 days are pruned at the end of each cycle.

## Supported event types

| Code | Event |
|------|-------|
| `FLR` | Solar Flare |
| `CME` | Coronal Mass Ejection |
| `IPS` | Interplanetary Shock |
| `MPC` | Magnetopause Crossing |
| `GST` | Geomagnetic Storm |
| `RBE` | Radiation Belt Enhancement |
| `SEP` | Solar Energetic Particle (template exists, no fields extracted yet) |

Adding a new event type requires three coordinated changes: a Jinja2 template in `src/templates/templates.py`, a regex extraction branch in `Formatter.extract_context()`, and a mapping entry in `Formatter.get_template()`.

## Key conventions

- **Templates** (`src/templates/templates.py`) are Jinja2 `Template` objects using Telegram's HTML parse mode. `DefaultUndefined` ensures missing regex captures render as `"Неизвестно"` rather than raising an error.
- **Configuration** lives entirely in `src/keys.py` (tokens, chat IDs, API key, DB path, DONKI URL). All `src/` modules import from it via `from src.keys import *` in `app.py`, which then passes values explicitly to each component.
- **Logging** appends to `logs.log` in the working directory at `INFO` level.
- **Test mode** is the primary way to develop without touching production: it uses an in-memory database (no state persists between runs) and routes messages to `TG_TEST_ID`.
- The synchronous `DonkiClient.fetch()` method exists but is unused in the main loop; `new_fetch()` (async) is the active one.
- `deepl` and `googletrans` appear in `requirements.txt` but are not used anywhere in the current code.
