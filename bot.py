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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# keys, can be environment variables
TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN", "8121913581:AAEcplN7VQ9r2uvAelVbCegaxCQPusdFBgk"
)
CHAT_ID = os.getenv("CHAT_ID", "-1002514102114")
NASA_API_KEY = os.getenv("NASA_API_KEY", "5RqBZjQI4rrfEXoNIwpbEKdYF57IVQkyzBGX1d2h")
DEEPL_AUTH_KEY = os.getenv("DEEPL_AUTH_KEY", "c5a6de6d-01ab-46d1-8e8f-0e2946813d0f:fx")
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache.db")
DONKI_URL = os.getenv("DONKI_URL", "https://api.nasa.gov/DONKI/notifications")

# Проверка ключей
missing = [
    n
    for n, v in [("NASA_API_KEY", NASA_API_KEY), ("DEEPL_AUTH_KEY", DEEPL_AUTH_KEY)]
    if not v
]
if missing:
    logger.error(f"Missing configuration: {', '.join(missing)}")
    raise RuntimeError(f"Не заданы: {', '.join(missing)}")


# Кэширование DB
def _connect_db(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_events (
            event_id TEXT PRIMARY KEY,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS translations (
            source TEXT PRIMARY KEY,
            translated TEXT
        )"""
    )
    conn.commit()
    return conn


class CacheDB:
    def __init__(self, path):
        self.conn = _connect_db(path)


class EventCache:
    def __init__(self, db: CacheDB):
        self.db = db

    def is_new(self, event_id: str) -> bool:
        cur = self.db.conn.cursor()
        cur.execute("SELECT 1 FROM sent_events WHERE event_id=?", (event_id,))
        return cur.fetchone() is None

    def mark_sent(self, event_id: str):
        cur = self.db.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO sent_events(event_id) VALUES(?)", (event_id,)
        )
        self.db.conn.commit()


class DonkiClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def fetch(self, start: str, end: str) -> list:
        params = {
            "startDate": start,
            "endDate": end,
            "type": "all",
            "api_key": self.api_key,
        }
        logger.info(f"Fetching DONKI from {start} to {end}")
        r = requests.get(DONKI_URL, params=params)
        r.raise_for_status()
        data = r.json()
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data


class Formatter:
    @staticmethod
    def format(ev: dict) -> tuple[list[str], list[str]]:
        msg_type = ev.get("messageType", ev.get("type", ""))
        issue_time = ev.get("messageIssueTime", ev.get("beginTime", ""))
        body = ev.get("messageBody", "") or ""
        link = ev.get("messageURL", "")
        
        remove_lines = ("Links to", "Community Coordinated Modeling Center", "Message Type", "Message Issue Date", "Message ID", "Disclaimer")
        replace_lines = {"ccmc": "База данных Уведомлений, Знаний, Информации Координируемого Сообществом Центра Моделирования",
                        "type": "Тип сообщения: ",
                        "date": "Дата и время события: ",
                        "id": "Идентификатор: ",
        }
        # header
        lines = [f"[{msg_type}] {issue_time}"]
        # body lines until Links to:
        for raw in body.splitlines():
            raw = raw.replace("##", "")
            raw = raw.strip()
            txt = raw
            if txt.startswith(remove_lines):
                # continue
                pass
            lines.append(raw)
        # extract links
        urls = re.findall(r"https?://\S+", body)
        if link:
            urls.insert(0, link)
        seen, links = set(), []
        for url in urls:
            if url not in seen:
                seen.add(url)
                links.append(url)
        return lines, links
    
    def formate_for_translate():
        pass


class Translator:
    def __init__(self, auth_key: str, db: CacheDB):
        self.client = deepl.Translator(auth_key)
        self.db = db

    def translate_line(self, text: str) -> str:
        cur = self.db.conn.cursor()
        cur.execute("SELECT translated FROM translations WHERE source=?", (text,))
        if row := cur.fetchone():
            return row[0]
        res = self.client.translate_text(text, target_lang="RU").text
        cur.execute(
            "INSERT INTO translations(source, translated) VALUES(?,?)", (text, res)
        )
        self.db.conn.commit()
        return res

    def translate_lines(self, lines: list[str]) -> list[str]:
        return [self.translate_line(l) for l in lines]


class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send(self, text: str, links: list[str]):
        # await self.bot.send_message(chat_id=self.chat_id, text=text)
        # if links:
        #     await self.bot.send_message(chat_id=self.chat_id, text='\n'.join(links))
        pass


def get_date_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=1)).isoformat(), today.isoformat()


async def main():
    db = CacheDB(CACHE_DB_PATH)
    cache = EventCache(db)
    client = DonkiClient(NASA_API_KEY)
    fmt = Formatter()
    tr = Translator(DEEPL_AUTH_KEY, db)
    notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)

    start, end = get_date_range()
    events = client.fetch(start, end)
    with open("output.txt", "w", encoding="utf-8") as f:
        for ev in events:
            if ev.get("messageType") == "Report":
                break
            eid = (
                ev.get("messageID")
                or ev.get("activityID")
                or f"{ev.get('messageType')}:{ev.get('messageIssueTime')}"
            )
            # if not cache.is_new(eid): continue
            lines, links = fmt.format(ev)
            # translated = tr.translate_lines(lines)
            # summary_ru = '\n'.join(translated)
            summary_ru = "\n".join(lines)
            # await notifier.send(summary_ru, links)
            f.write(summary_ru + "\n")
            if links:
                f.write("Ссылки:\n" + "\n".join(links) + "\n")
            f.write("-" * 100 + "\n")
            cache.mark_sent(eid)
            logger.info(f"Logged {eid}")


if __name__ == "__main__":
    asyncio.run(main())
