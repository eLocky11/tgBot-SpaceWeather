import os
import re
import json
import sqlite3
import requests
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from telegram import Bot
from telegram.error import TelegramError
import deepl

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# URL's

# keys, can be environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8121913581:AAEcplN7VQ9r2uvAelVbCegaxCQPusdFBgk")
CHAT_ID        = os.getenv("CHAT_ID", "-1002514102114")
NASA_API_KEY   = os.getenv("NASA_API_KEY", "5RqBZjQI4rrfEXoNIwpbEKdYF57IVQkyzBGX1d2h")
DEEPL_AUTH_KEY = os.getenv("DEEPL_AUTH_KEY", "c5a6de6d-01ab-46d1-8e8f-0e2946813d0f:fx")
CACHE_DB_PATH  = os.getenv("CACHE_DB_PATH", "cache.db")
DONKI_URL      = os.getenv("DONKI_URL", "https://api.nasa.gov/DONKI/notifications")

# check the keys
missing = [name for name, val in [
    ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
    ('CHAT_ID', CHAT_ID),
    ('NASA_API_KEY', NASA_API_KEY),
    ('DEEPL_AUTH_KEY', DEEPL_AUTH_KEY)
] if not val]
if missing:
    logger.error(f"Не установлены обязательные настройки: {', '.join(missing)}")
    raise RuntimeError(f"Missing configuration: {', '.join(missing)}")

# cache DB class
class CacheDB:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self._init_tables()

    def _init_tables(self):
        cur = self.conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sent_events (
                event_id TEXT PRIMARY KEY,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                source TEXT PRIMARY KEY,
                translated TEXT
            )''')
        self.conn.commit()

# event cache class
class EventCache:
    """Кэш уже отправленных событий"""
    def __init__(self, db: CacheDB):
        self.db = db

    def is_new(self, event_id: str) -> bool:
        cur = self.db.conn.cursor()
        # исправлено имя таблицы и передача параметра как кортеж
        cur.execute('SELECT 1 FROM sent_events WHERE event_id = ?', (event_id,))
        return cur.fetchone() is None

    def mark_sent(self, event_id: str):
        cur = self.db.conn.cursor()
        # исправлен синтаксис INSERT INTO и передача параметра как кортеж
        cur.execute('INSERT OR IGNORE INTO sent_events(event_id) VALUES(?)', (event_id,))
        self.db.conn.commit()

# NASA DONKI API class
class DonkiClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch(self, start: str, end: str) -> list:
        params = {
            "startDate": start,
            "endDate": end,
            "type": "all",
            "api_key": self.api_key,
        }
        logger.info(f"Fetching DONKI events from {start} to {end}")
        resp = requests.get(DONKI_URL, params=params)
        resp.raise_for_status()
        json_file = "output.json"
        result = resp.json()

        with open(json_file, "w") as file:
            json.dump(result, file, indent=4)

        return result
    
# text formatter class
class Formatter:
    # formate text and get links
    @staticmethod
    def format(ev: dict) -> tuple[str, list[str]]:
        msg_type = ev.get("messageType", ev.get("type", "UNKNOWN"))
        issue_time = ev.get("messageIssueTime", ev.get("beginTime", "N/A"))
        body = ev.get("messageBody", "")
        link = ev.get("messageURL", "")
        event_class = "empty event class"

        # set event name
        match msg_type:
            case "FLR":
                event_class = "Солнечная вспышка"
            case "SEP":
                event_class = "Подъёмы энергичный частиц"
            case "CME":
                event_class = "Корональные выбросы массы"
            case "IPS":
                event_class = "Межпланетные ударные волны"
            case "MPC":
                event_class = "Прорывы магнитопаузы"
            case "GST":
                event_class = "Геомагнитные бури"
            case "RBE":
                event_class = "Усиления радиационных поясов"

        lines = ["База Данных Уведомлений, Знаний и информации Координируемого Сообществом Центра Моделирования (CCMC DONKI)", f"[{msg_type}] {issue_time}", f"Класс события: {event_class}"]
        for line in body.splitlines():
            if line.strip().startswith("Links to"):
                continue
            lines.append(line)
        summary = "\n".join(lines).strip()

        # getting url and links from body
        urls = re.findall(r'https?://\S+', body)
        seen = set()
        links = [link]
        for url in urls:
            if url not in seen:
                seen.add(url)
                links.append(url)

        return summary, links

# DeepL API class
class Translator:
    def __init__(self, api_key: str, db: CacheDB) -> None:
        self.translator = deepl.Translator(api_key)
        self.db = db

    def translate(self, text: str) -> str:
        cur = self.db.conn.cursor()
        cur.execute('SELECT translated FROM translations WHERE source = ?', (text,))
        row = cur.fetchone()
        if row:
            return row[0]
        result = self.translator.translate_text(text, target_lang="RU").text
        logger.info("Translate result is ready")
        cur.execute('INSERT INTO translations(source, translated) VALUES(?,?)', (text, result))
        self.db.conn.commit()
        return result
    
class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self.bot = Bot(token=token)
        self.chat_id = chat_id

        async def send(self, text: str, links: list[str]):
            try:
                # Добавляем ссылки в конец сообщения перед отправкой
                if links:
                    text = text + "\n\nСсылки:\n" + "\n".join(links)
                await self.bot.send_message(chat_id=self.chat_id, text=text)
            except TelegramError as te:
                logger.error(f"Error sending a message: {te}")
            except Exception as e:
                logger.error(f"Unknown error on on TelegramNotifier.send(): {e}")

def get_date_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    end = now.date()
    start = end - timedelta(days=1)
    return start.isoformat(), end.isoformat()

async def main():
    db = CacheDB(CACHE_DB_PATH)
    cache = EventCache(db)
    client = DonkiClient(NASA_API_KEY)
    formatter = Formatter()
    translator = Translator(DEEPL_AUTH_KEY, db)
    notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)

    start, end = get_date_range()
    events = client.fetch(start, end)
    msg_log = "output.txt"

    # изменить на а при включении кэша
    with open(msg_log, "w", encoding="utf-8") as file:
        for event in events:
            if event.get("messageType") == "Report":
                break
            event_id = event.get("messageID") or event.get("activityID") or f"{event.get("messageType")}:{event.get("messageIssueTime")}"
            # if not cache.is_new(event_id):
                # continue

            summary_en, links = formatter.format(event)
            # summary_ru = translator.translate(summary_en)
            # await notifier.send(summary_ru, links)
            # cache.mark_sent(event_id)
            # logger.info(f"Sent notification for {event_id}")

            end_text = summary_en + "\n\n" + "Ссылки:\n" + "\n".join(links) + "\n\n"+"-"*100+"\n\n"

            file.write(end_text)
            cache.mark_sent(event_id)
            logger.info("Message logs recorded")

if __name__ == "__main__":
    asyncio.run(main())