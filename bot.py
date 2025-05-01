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

    def fetch(self, start: str, end: str) -> list:
        params = {
            "startDate": start,
            "endDate": end,
            "type": "all",
            "api_key": self.api_key,
        }
        logging.info(f"Fetching DONKI from {start} to {end}")
        resp = requests.get(DONKI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        # save raw JSON response
        with open("output.json", "w", encoding="utf-8") as jf:
            json.dump(data, jf, ensure_ascii=False, indent=2)
        return data


# Форматирование текста, два этапа: сырое до перевода, готовое сообщение для отправки
class Formatter:
    # ШАБЛОНЫ
    # FLR - Солнечные вспышки
    FLR_TEMPLATE = Template(
        """
**[{{ header }}]**
**Сводка**:
{{ summary_text }}

Параметры FLР:
- Время начала: {{ start_time or '—' }}
- Время пика: {{ peak_time or '—' }}
- Интенсивность: {{ intensity or '—' }}
- Регион источника: {{ source_region or '—' }}
- Идентификатор: {{ activity_id or '—' }}

{% if links %}
Ссылки:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}

Примечания:
{{ notes or '—' }}
""".strip()
    )

    # SEP - Подъём энергичных частиц
    SEP_TEMPLATE = Template(
        """
**[{{ header }}]**
**Сводка**:
{{ summary_text }}

Activity ID: {{ activity_id or '—' }}

{% if links %}
Ссылки:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}

Примечания:
{{ notes or '—' }}
""".strip()
    )

    # CME - Выброс корональной массы
    CME_TEMPLATE = Template(
        """
**[{{ header }} ВЫБРОС КОРОНАЛЬНОЙ МАССЫ]**
**Сводка**:
{{ summary_text }}

Параметры CME:
- Время начала: {{ start_time or '—' }}
- Скорость: {{ speed or '—' }} км/с
- Полуугол раскрытия: {{ half_angle or '—' }}°
- Направление (lon/lat): {{ lon or '—' }}/{{ lat or '—' }}
- Activity ID: {{ activity_id or '—' }}

Типы CME:
- S-тип: CME со скоростью менее 500 км/с
- C-тип: Обычная скорость 500-999 км/с
- O-образный: Время от времени 1000-1999 км/с
- R-тип: редкие 2000-2999 км/с
- ER-тип: Чрезвычайно редкий >3000 км/с

Ожидаемое влияние:
{{ impact_paragraph or '—' }}

{% if links %}
Ссылки на анимации:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}

Примечания:
{{ notes or '—' }}
""".strip()
    )

    # IPS, MPC, GST - Межпланетные ударные волны, Прорывы магнитопаузы, Геомагнитные бури
    SIMPLE_TEMPLATE = Template(
        """
**[{{ header }}]**
**Сводка**:
{{ summary_text }}

Activity ID: {{ activity_id or '—' }}

{% if links %}
Ссылки:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}

Примечания:
{{ notes or '—' }}
""".strip()
    )

    # RBE - Усиление радиационных поясов
    RBE_TEMPLATE = Template(
        """
**[{{ header }}]**
**Сводка**:
{{ summary_text }}

Параметры RBE:
- Время начала: {{ start_time or '—' }}
- Поток (>2.0 MeV): {{ flux or '—' }} pfu
- Причина: {{ cause or '—' }}
- Activity ID: {{ activity_id or '—' }}

{% if links %}
Ссылки:
{% for url in links -%}
- {{ url }}
{% endfor %}
{% endif %}

Примечания:
{{ notes or '—' }}
""".strip()
    )

    @staticmethod
    def _find(text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    @classmethod
    def pre_format(cls, ev: dict) -> dict:
        """
        Разбираем сырой JSON-эвент, собираем общий набор полей
        и доп. атрибуты, специфичные для каждого типа.
        """
        event_id = ev.get("messageID", "")
        msg_type = ev.get("messageType", ev.get("type", ""))
        issue_time = ev.get("messageIssueTime", ev.get("beginTime", ""))
        header = f"{msg_type} {issue_time}"
        body = ev.get("messageBody", "") or ""

        # Ссылки: первичная и все найденные в теле
        raw_links = [ev.get("messageURL")] + re.findall(r"https?://\S+", body)
        links = []
        for u in raw_links:
            if u and u not in links:
                links.append(u)

        # Чистим от служебных строк '## …' и "(a) …", "(b) …"
        text = "\n".join(
            line
            for line in body.splitlines()
            if not line.strip().startswith("##")
            and not line.strip().startswith(("Links to the movies", "http://", "https://", "\n"))
            and not re.match(r"^\([a-z]\)", line.strip())
        )

        # Отрезаем и сохраняем Notes
        notes = ""
        if "Notes:" in text:
            parts = text.split("Notes:", 1)
            text, notes = parts[0], parts[1].strip()

        # Убираем из summary любые упоминания Activity ID
        summary_lines = [l.strip() for l in text.splitlines() if "Activity ID" not in l]
        summary_text = "\n".join(summary_lines).replace("Summary:", "").strip()

        data = {
            "event_id": event_id,
            "header": header,
            "msg_type": msg_type,
            "summary_text": summary_text,
            "notes": notes,
            "links": links
        }

        # Специфичное для каждого типа
        if msg_type == "FLR":
            data.update(
                {
                    "start_time": cls._find(body, r"Flare start time:\s*([\dT:Z\-]+)"),
                    "peak_time": cls._find(body, r"Flare peak time:\s*([\dT:Z\-]+)"),
                    "intensity": cls._find(body, r"Flare intensity:\s*(\S+ class)"),
                    "source_region": cls._find(body, r"Source region:\s*(.+?)\."),
                    "activity_id": cls._find(body, r"Activity ID:\s*([\w\-\:]+)"),
                }
            )
        elif msg_type == "SEP":
            data["activity_id"] = cls._find(body, r"Activity ID:\s*([\w\-\:]+)")
        elif msg_type == "CME":
            data.update(
                {
                    "start_time": cls._find(
                        body, r"Start time of the event:\s*([\dT:Z\-]+)"
                    ),
                    "speed": cls._find(body, r"Estimated speed:\s*~?(\d+)"),
                    "half_angle": cls._find(body, r"half-angle:\s*(\d+)"),
                    "lon": cls._find(body, r"lon\./lat\.\):\s*([-\d]+)/"),
                    "lat": cls._find(body, r"lon\./lat\.\):\s*[-\d]+/([-\d]+)"),
                    "activity_id": cls._find(body, r"Activity ID:\s*([\w\-\:]+)"),
                    "impact_paragraph": next(
                        (l for l in text.splitlines() if l.startswith("Based on")), ""
                    ),
                }
            )
        elif msg_type in ("IPS", "MPC", "GST"):
            data["activity_id"] = cls._find(body, r"Activity ID:\s*([\w\-\:]+)")
        elif msg_type == "RBE":
            data.update(
                {
                    "start_time": cls._find(body, r"starting at\s*([\dT:Z\-]+)"),
                    "flux": cls._find(body, r"flux is above\s*(\d+)"),
                    "cause": cls._find(body, r"caused by (.+?)\."),
                    "activity_id": cls._find(body, r"Activity ID:\s*([\w\-\:]+)"),
                }
            )

        return data

    @classmethod
    def post_format(cls, data: dict) -> str:
        """
        Рендерим окончательный текст в зависимости от типа события.
        """
        msg_type = data["msg_type"]
        if msg_type == "FLR":
            return cls.FLR_TEMPLATE.render(**data)
        elif msg_type == "SEP":
            return cls.SEP_TEMPLATE.render(**data)
        elif msg_type == "CME":
            return cls.CME_TEMPLATE.render(**data)
        elif msg_type in ("IPS", "MPC", "GST"):
            return cls.SIMPLE_TEMPLATE.render(**data)
        elif msg_type == "RBE":
            return cls.RBE_TEMPLATE.render(**data)
        else:
            # на всякий случай — просто header+summary
            return f"[{data['header']}]\n{data['summary_text']}"


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


def get_date_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=1)).isoformat(), today.isoformat()


# Функция для тестирования
async def testing(input_file="output.json", output_file="test_output.txt", trans: bool = False):
    logging.info("Starting the test")

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
            if tr != None:
                new_summary = await tr.translate(text=data["summary_text"], target_lang="RU", test=True)
                data["summary_text"] = new_summary
            message = Formatter.post_format(data)
            outf.write(message + "\n" + ("=" * 80) + "\n")


# асинхронная функция запуска
# !переделать в класс
async def main():
    db = CacheDB(CACHE_DB_PATH)
    cache = EventCache(db)
    client = DonkiClient(NASA_API_KEY)
    fmt = Formatter()
    tr = Translator(DEEPL_AUTH_KEY, db)
    notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)

    start, end = get_date_range()
    events = client.fetch(start, end)

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
        asyncio.run(testing())
    else:
        asyncio.run(main())
