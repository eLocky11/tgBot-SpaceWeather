import sys, asyncio, logging


from src.keys import *
from src.donki import DonkiClient
from src.database import DataBase
from src.formatter import Formatter
from src.notifier import TelegramNotifier


# Класс запуска и управления
class BotApp:
    def __init__(self, argv) -> None:
        # Логирование
        logging.basicConfig(
            filename="logs.log",  # Имя файла
            encoding="utf-8",  # Кодировка
            level=logging.INFO,  # Уровень - DEBUG: минимальный уровень логирования
            format="%(asctime)s - %(levelname)s - %(message)s",  # формат сообщений
            filemode="a",  # Мод - дополнение
        )

        self.on_init()

# Инициализатор
    def on_init(self):
        self.db = DataBase(DB_PATH)
        self.bot = TelegramNotifier(TELEGRAM_TOKEN)
        self.donki = DonkiClient(NASA_API_KEY, DONKI_URL)

# Цикл бота
    async def on_run(self):
        logging.info("="*10+"Цикл запущен"+"="*10)

        # 1. получаем данные
        try:
            events = await self.donki.new_fetch()
        except Exception as e:
            logging.error(f"Ошибка при запросе DONKI API: {e}")

        if not events:
            logging.info("Нет данных от DONKI - завершение.")
            return
        
        # 2. обработка каждого события
        for ev in events:
            m_type = ev.get("messageType")
            m_id   = ev.get("messageID")
            # пропускаем репорты и сепы
            if m_type == "Report" or not m_id:
                continue

            # проверяем наличие в бд
            if self.db.has_event(m_id):
                continue
            
            # 3. форматирование
            try:
                tpl = Formatter.get_template(m_type)
                ctx = Formatter.extract_context(ev)
                msg = tpl.render(**ctx)
            except Exception as e:
                logging.error(f"Ошибка форматирования события {m_id}: {e}")
                continue

            # 4. отправление и сохранение с бд
            try:
                await self.bot.send_notification(msg, TG_TEST_ID, parse_mode="HTML")
                self.db.add_event(m_id, msg)
                logging.info(f"Событие {m_id} отправлено и сохранено.")
            except Exception as e:
                logging.error(f"Ошибка отправки события {m_id}: {e}")

        # 5. чистим старые записи
        self.db.remove_old_events()
        logging.info("="*10+"Завершение цикла"+"="*10+"\n"*4)

        self.db.close()


# Запуск
if __name__ == "__main__":
    app = BotApp(sys.argv)
    asyncio.run(app.on_run())
