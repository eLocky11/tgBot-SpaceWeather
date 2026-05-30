import logging, os
from dotenv import load_dotenv
load_dotenv()

from src.paths import *
from src.donki import DonkiClient
from src.database import DataBase
from src.formatter import Formatter
from src.notifier import TelegramNotifier


TELEGRAM_TOKEN = os.environ["TG_BOT_SW_TOKEN"]
NASA_API_KEY = os.environ["NASA_API_KEY"]
TG_CHAT_ID = os.environ["TG_CHAN_SW_ID"]
TG_TEST_ID = os.environ["TG_CHAN_TEST_ID"]


class BotApp:
    """
    Main application class for the Space Weather Telegram bot.

    Fetches space weather events from NASA DONKI API, formats them,
    and publishes new (previously unseen) events to a Telegram channel.
    Supports a test mode that redirects output to a test chat and
    disables persistent database writes.

    Attributes:
        test_mode (bool): Whether the app is running in test mode.
        db (DataBase): SQLite database for tracking sent event IDs.
        bot (TelegramNotifier): Telegram bot client for sending messages.
        donki (DonkiClient): NASA DONKI API client.
    """
    def __init__(self, argv) -> None:
        # Logging
        logging.basicConfig(
            filename="logs.log",
            encoding="utf-8",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filemode="a",
        )
        self.test_mode = True if len(argv) > 1 and argv[1] == "test" else False
        if self.test_mode:
            logging.info("Активирован тестовый режим. Отключен доступ к базе данных, отправка в testing чат")
        self.on_init()

    def on_init(self):
        self.db = DataBase(DB_PATH, self.test_mode)
        self.bot = TelegramNotifier(TELEGRAM_TOKEN)
        self.donki = DonkiClient(NASA_API_KEY, DONKI_URL)

# Main cycle
    async def on_run(self):
        logging.info("="*10+"Цикл запущен"+"="*10)

        # 1. Get data
        try:
            events = await self.donki.new_fetch()
        except Exception as e:
            logging.error(f"Ошибка при запросе DONKI API: {e}")

        if not events:
            logging.info("Нет данных от DONKI - завершение.")
            return
        
        # 2. Event handling
        for ev in events:
            m_type = ev.get("messageType")
            m_id   = ev.get("messageID")
            # skip the reports and seps
            if m_type == "Report" or not m_id:
                continue

            # Checking for availability in the database
            if self.db.has_event(m_id):
                continue
            
            # 3. Formatting
            try:
                tpl = Formatter.get_template(m_type)
                ctx = Formatter.extract_context(ev)
                msg = tpl.render(**ctx)
            except Exception as e:
                logging.error(f"Ошибка форматирования события {m_id}: {e}")
                continue

            # 4. Sending and saving from a database
            chat_id = TG_TEST_ID if self.test_mode else TG_CHAT_ID
            try:
                await self.bot.send_notification(msg, chat_id, parse_mode="HTML")
                self.db.add_event(m_id, msg)
                logging.info(f"Событие {m_id} отправлено и сохранено.")
            except Exception as e:
                logging.error(f"Ошибка отправки события {m_id}: {e}")

        # 5. Cleaning up old records
        self.db.remove_old_events()
        logging.info("="*10+"Завершение цикла"+"="*10+"\n"*4)

        self.db.close()
