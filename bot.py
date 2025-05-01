import os
import re
import sys
import json
import sqlite3
import requests
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from jinja2 import Template
from telegram import Bot
from telegram.error import TelegramError

import deepl
import googletrans


# логирование
logging.basicConfig(
    filename="logs.log",  # Имя файла
    encoding="utf-8",  # Кодировка
    level=logging.INFO,  # Уровень - DEBUG: минимальный уровень логирования
    format="%(asctime)s - %(levelname)s - %(message)s",  # формат сообщений
    filemode="w",  # Мод - перезапись в файл
)

# Environment variables / configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8121913581:AAEcplN7VQ9r2uvAelVbCegaxCQPusdFBgk")
CHAT_ID = os.getenv("CHAT_ID", "-1002514102114")
NASA_API_KEY = os.getenv("NASA_API_KEY", "5RqBZjQI4rrfEXoNIwpbEKdYF57IVQkyzBGX1d2h")
DEEPL_AUTH_KEY = os.getenv("DEEPL_AUTH_KEY", "c5a6de6d-01ab-46d1-8e8f-0e2946813d0f:fx")
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache.db")
DONKI_URL = os.getenv("DONKI_URL", "https://api.nasa.gov/DONKI/notifications")

# Validate configuration
missing = [
    name
    for name, val in [
        ("NASA_API_KEY", NASA_API_KEY),
        ("DEEPL_AUTH_KEY", DEEPL_AUTH_KEY),
    ]
    if not val
]
if missing:
    logging.error(f"Missing configuration: {', '.join(missing)}")
    raise RuntimeError(f"Не заданы: {', '.join(missing)}")


# Database setup and caching
class CacheDB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self._init_tables()

    def _init_tables(self):
        cur = self.conn.cursor()
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
        self.conn.commit()


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


# NASA DONKI API client
class DonkiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch(self) -> list:
        params = {
            "api_key": self.api_key,
        }
        logging.info(f"Fetching DONKI events data")
        resp = requests.get(DONKI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data


# Форматирование текста, два этапа: сырое до перевода, готовое сообщение для отправки
class Formatter:
    # Шаблон сообщения
    MSG_TEMPLATE_LEGACY = Template(
        """
**[{{ msg_type }}]** - {{ event_id }} - **{{ event_name }}**

**Сводка**:
{{ summary_text }}

{% if notes %}
Примечания:
{{ notes }}
{% endif %}

{% if links %}
Ссылки на анимации:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}
""".strip()
    )

    MSG_TEMPLATE = Template(
        """
**[{{ msg_type }}]** - {{ event_id }} - **{{ event_name }}**

**Сводка**:
{{ summary_text }}

{% if notes %}
Примечания:
{{ notes }}
{% endif %}
""".strip()
    )

    @staticmethod
    def _find(text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None
    
    @classmethod
    def set_name(cls, id: str):
        match id:
            case "FLR":
                return "Солнечная вспышка"
            case "SEP":
                return "Подъём энергичных частиц"
            case "CME":
                return "Корональный выброс массы"
            case "IPS":
                return "Межпланетные ударные волны"
            case "MPC":
                return "Прорывы магнитопаузы"
            case "GST":
                return "Геомагнитные бури"
            case "RBE":
                return "Усиление радиационных поясов"

    @classmethod
    def base_data(cls, ev: dict) -> dict:
        msg_type = ev.get("messageType", "")
        msg_id = ev.get("messageID", "")
        msg_time = ev.get("messageIssueTime", "")
        msg_name = cls.set_name(msg_type)
        body = ev.get("messageBody", "") or ""
        summary, notes = cls.extract_summary_notes(body)
        links = cls.extract_links(ev, body)
        return {
            "event_id": msg_id,
            "event_name": msg_name,
            "msg_type": msg_type,
            "msg_time": msg_time,
            "summary_text": summary,
            "notes": notes,
            "links": links,
        }
    
    @classmethod
    def extract_summary_notes(cls, body: str) -> tuple[str, str]:
        """
        Разбивает body на два куска:
        - summary: всё, что между '## Summary:' и (перед) '## Notes:' или концом строки
        - notes: всё, что после '## Notes:' до конца body
        """
        # 1) Найдём и вырежем Notes
        notes = ""
        m_notes = re.search(r"##\s*Notes:\s*([\s\S]+)$", body)
        if m_notes:
            notes = m_notes.group(1).strip()
            # обрезаем тело до начала Notes
            body = body[:m_notes.start()]

        # 2) Найдём Summary
        summary = ""
        m_sum = re.search(r"##\s*Summary:\s*([\s\S]+?)(?=(\n##\s*\w+:)|\Z)", body)
        if m_sum:
            summary = m_sum.group(1).strip()

        # 3) Уберём Markdown-заголовки '## ' из summary
        #    (например строки, начинающиеся с '## ')
        summary = re.sub(r"(?m)^##\s*", "", summary)

        return summary, notes

    @classmethod
    def extract_links(cls, ev: dict, body: str) -> list[str]:
        """
        Собирает все HTTP(S)-ссылки из body и возвращает их списком.
        Не мутирует ev или body — но при желании можно вырезать ссылки из body.
        """
        # найдём все вхождения ссылок
        urls = re.findall(r"https?://\S+", body)
        # убираем дубли, сохраняя порядок
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    # Главная точка входа для разбора сырого JSON
    @classmethod
    def pre_format(cls, ev: dict) -> dict:
        data = cls.base_data(ev)

        return data


    # Форматируем окончательный текст по шаблону
    @classmethod
    def post_format(cls, data: dict) -> str:
        return cls.MSG_TEMPLATE.render(**data)


# Переводчик - Google или DeepL
class Translator:
    def __init__(self, deepl_key: str = None, db: CacheDB = None):
        self.deepl = deepl.Translator(deepl_key)
        self.google = googletrans.Translator()
        self.db = db

    # возвращает метод перевода
    async def translate(self, text: str, target_lang: str = "RU", test: bool = False):
        # проверка на наличие бд 
        if self.db is not None:
            cur = self.db.conn.cursor()
            cur.execute("SELECT translated FROM translations WHERE source=?", (text,))
            if row := cur.fetchone():
                return row[0]
        
        logging.info("Check for DeepL usage limits")
        if self.deepl.get_usage().character.limit_exceeded or test == True:
            # google
            if test:
                logging.info("TESTING GOOGLE TRANSLATE")
            else:
                logging.info("DeepL usage limit exceeded")
                logging.info("Using Google for translation")

            translated = await self.google.translate(text=text, dest=target_lang.lower())
            result = translated.text
        else:
            # deepl
            logging.info("Using DeepL for translation")
            translated = self.deepl.translate_text(
                text=text, target_lang=target_lang.upper()
            )
            result = translated.text

        if self.db is not None:
            cur = self.db.conn.cursor()
            cur.execute(
                "INSERT INTO translations(source, translated) VALUES(?,?)",
                (text, result),
            )
            self.db.conn.commit()

        return result

    # через чекер получает метод и переводит
    def translate_lines(self, lines: list[str]) -> list[str]:
        translated = []
        for text in lines:
            # проверяем кэш и переводим при необходимости
            translated_text = self.translate(text, target_lang="RU")
            translated.append(translated_text)
        return translated


# Уведомление Телеграм
class TelegramNotifier:
    def __init__(self, token: str = None, chat_id: str = None):
        # self.bot = Bot(token=token)
        # self.chat_id = chat_id
        pass

    async def send(self, text: str, links: list[str]):
        """
        # REAL SENDING (commented out):
        # await self.bot.send_message(chat_id=self.chat_id, text=text)
        # if links:
        #     await self.bot.send_message(chat_id=self.chat_id, text='\n'.join(links))
        """
        logging.info("Send disabled in test mode")


# Функция для тестирования
async def formate_test(input_file="donki_output.json", output_file="out_orig.txt", trans: bool = False):
    logging.info("Starting Formatter test")

    db = CacheDB(CACHE_DB_PATH)
    tr = Translator(DEEPL_AUTH_KEY, db) if trans else None

    if not os.path.exists(input_file):
        logging.error(f"Input file not found: {input_file}")
        return
    with open(input_file, encoding="utf-8") as jf:
        events = json.load(jf)
    with open(output_file, "w", encoding="utf-8") as outf:
        for ev in events:
            if ev.get("messageType") == "Report":
                continue
            data = Formatter.pre_format(ev)
            if tr:
                data["summary_text"] = await tr.translate(text=data["summary_text"], target_lang="RU", test=True)
                if data["notes"]:
                    data["notes"] = await tr.translate(data["notes"], target_lang="RU", test=True)
            message = Formatter.post_format(data)
            outf.write(message + "\n" + ("=" * 80) + "\n")


async def donki_test(output_file = "donki_output.json"):
    logging.info("Starting DONKI test")
    donki = DonkiClient(NASA_API_KEY)
    data = donki.fetch()

    # save raw JSON response
    with open(output_file, "w", encoding="utf-8") as jf:
        logging.info("Saving DONKI output data to json")
        json.dump(data, jf, ensure_ascii=False, indent=2)


async def test():
    pass


# асинхронная функция запуска
# !переделать в класс
async def main():
    db = CacheDB(CACHE_DB_PATH)
    cache = EventCache(db)
    client = DonkiClient(NASA_API_KEY)
    fmt = Formatter()
    tr = Translator(DEEPL_AUTH_KEY, db)
    notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)

    events = client.fetch()

    with open("output.txt", "w", encoding="utf-8") as outf:
        for ev in events:
            if ev.get("messageType") == "Report":
                continue
            data = fmt.pre_format(ev)
            # проверка кэша
            if not cache.is_new(data["event_id"]):
                continue
            # lines = tr.translate_lines(...)
            message = fmt.post_format(data)
            outf.write(message + "\n" + ("-" * 80) + "\n")
            cache.mark_sent(data["event_id"])
            logging.info(f"Logged {data['event_id']}")


# запуск
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test())
    elif len(sys.argv) > 1 and sys.argv[1] == "dtest":
        asyncio.run(donki_test())
    elif len(sys.argv) > 1 and sys.argv[1] == "ftest":
        if len(sys.argv) > 2 and sys.argv[2] == "t":
            asyncio.run(formate_test(output_file="out_trans.txt", trans=True))
        else:
            asyncio.run(formate_test())
    else:
        asyncio.run(main())
