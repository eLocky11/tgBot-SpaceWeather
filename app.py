import os, sys, json, asyncio, logging

from enum import Enum

from src.keys import *
from src.donki import DonkiClient
from src.database import DataBase
from src.formatter import Formatter
from src.translator import Translator
from src.notifier import TelegramNotifier


# Варианты запуска
class Mode(Enum):
    REGULAR = 1  # без аргументов
    FORMATTER_TEST = 2  # ftest
    TRANSLATE_TEST = 3  # ttest
    MESSAGE_TEST = 4  # mtest


# Класс запуска и управления
class BotApp:
    def __init__(self, argv) -> None:
        # Логирование
        logging.basicConfig(
            filename="logs.log",  # Имя файла
            encoding="utf-8",  # Кодировка
            level=logging.INFO,  # Уровень - DEBUG: минимальный уровень логирования
            format="%(asctime)s - %(levelname)s - %(message)s",  # формат сообщений
            filemode="w",  # Мод - перезапись в файл
        )
        self.db_test_mode = False
        # Определяем режим
        if len(argv) > 1 and argv[1] == "ftest":
            self.mode = Mode.FORMATTER_TEST
            if len(argv) > 2 and argv[2] == "db":
                self.db_test_mode = True
        elif len(argv) > 1 and argv[1] == "ttest":
            self.mode = Mode.TRANSLATE_TEST
            if len(argv) > 2 and argv[2] == "db":
                self.db_test_mode = True
        elif len(argv) > 1 and argv[1] == "mtest":
            self.mode = Mode.MESSAGE_TEST
            if len(argv) > 2 and argv[2] == "db":
                self.db_test_mode = True
        else:
            self.mode = Mode.REGULAR
            self.db_test_mode = False

        self.on_init()

# Инициализатор
    def on_init(self):
        db_path = "data/db.db"
        self.db = DataBase(db_path, self.db_test_mode)
        self.tr = Translator(DEEPL_AUTH_KEY, self.db)
        self.bot = TelegramNotifier(TELEGRAM_TOKEN)
        self.donki = DonkiClient(NASA_API_KEY, DONKI_URL)

# Запускаторинатор
    async def on_run(self):
        if self.mode == Mode.FORMATTER_TEST:
            await self._running_ftest()
        elif self.mode == Mode.TRANSLATE_TEST:
            await self._running_ttest()
        elif self.mode == Mode.MESSAGE_TEST:
            await self._running_mtest()
        else:
            await self._running()

# Цикл приложения
    async def _running(self):
        logging.info("Запуск главного цикла получения и отправки уведомлений...")

        # Шаг 1: Получаем данные с помощью асинхронного запроса
        try:
            data = await self.donki.new_fetch()
        except Exception as e:
            logging.error(f"Ошибка при запросе DONKI API: {e}")
            return
        
        if not data:
            logging.warning("Нет данных от DONKI — завершение работы.")
            return
        
        to_send = []

        # Шаг 2: Обрабатываем события
        for ev in data:
            if ev.get("messageType") == "Report":
                continue
            event_id = ev.get("messageID")

            # Шаг 3: Пропускаем уже отправленные
            if self.db.has_event(event_id):
                continue

            # Шаг 4: Предварительное форматирование
            pre_data = Formatter.pre_format(ev)

            # Шаг 5: Перевод строк
            # Перевод lines
            translated_lines = []
            for line in pre_data.get("lines", []):
                texts, delims = Formatter.split_line(line)
                translated = await self.tr.on_translate(texts)
                translated_lines.append(Formatter.rejoin_line(translated, delims))
            pre_data["lines"] = translated_lines

            # Перевод notes
            translated_notes = []
            for note in pre_data.get("notes", []):
                texts, delims = Formatter.split_line(note)
                translated = await self.tr.on_translate(texts)
                translated_notes.append(Formatter.rejoin_line(translated, delims))
            pre_data["notes"] = translated_notes

            # Шаг 6: Финальное форматирование
            msg = Formatter.post_format(pre_data)

            # Сохраняем для отправки
            to_send.append((event_id, msg))

        if not to_send:
            logging.info("Нет новых событий для отправки.")
            return

        # Шаг 7: Отправка сообщений и добавление в БД
        for event_id, msg in to_send:
            try:
                await self.bot.send_notification(msg, TG_CHAT_ID, parse_mode="HTML")
                self.db.add_events([(event_id, msg, None)])
                logging.info(f"Отправлено событие: {event_id}")
            except Exception as e:
                logging.error(f"Ошибка при отправке события {event_id}: {e}")

        # Шаг 8: Очистка старых записей
        self.db.remove_old_events()
        logging.info("Завершение цикла.")


    def _testing_json(self):
        json_file = "donki_output.json"
        data = None
        # Проверяем наличие локального файла
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not data:
                    data = None
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"Не удалось прочитать {json_file}: {e}")
                data = None

        # Если нет данных, запрашиваем из API и сохраняем
        if data is None:
            client = DonkiClient(NASA_API_KEY, DONKI_URL)
            try:
                data = client.fetch()
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logging.info(f"Данные сохранены в {json_file}")
            except Exception as e:
                logging.error(f"Ошибка при запросе DONKI API: {e}")
        return data


# Тест форматирования
    async def _running_ftest(self):
        logging.info("Запуск тестового режима форматирования...")
        data = self._testing_json()
        names = ["format_pre.txt", "format_post.txt"]

        # Прогон через форматтер
        pre_list = []
        post_list = []
        for ev in data:
            if ev.get("messageType") == "Report":
                continue
            pre = Formatter.pre_format(ev)
            post = Formatter.post_format(pre)
            pre_list.append(pre)
            post_list.append(post)

        # Сохраняем результаты
        try:
            with open(names[0], "w", encoding="utf-8") as f:
                json.dump(pre_list, f, ensure_ascii=False, indent=2)
            with open(names[1], "w", encoding="utf-8") as f:
                f.write("\n\n".join(post_list))
            logging.info(
                "Результаты форматирования сохранены в format_pre.txt и format_post.txt"
            )
            print(
                "Тест форматирования завершён. Файлы format_pre.txt и format_post.txt созданы."
            )
        except IOError as e:
            logging.error(f"Ошибка при сохранении результатов: {e}")

# Тест форматирования
    async def _running_ttest(self):
        logging.info("Запуск тестового режима переводчика...")
        data = self._testing_json()
        names = ["trans_pre.txt", "trans_post.txt"]

        # Прогон через форматтер
        pre_list, post_list = [], []
        for ev in data:
            if ev.get("messageType") == "Report":
                continue
            pre_data = Formatter.pre_format(ev)
            pre_list.append(pre_data)

            lines = pre_data.get("lines", [])
            new_lines = []
            for orig in lines:
                texts, delims = Formatter.split_line(orig)
                tr_texts = await self.tr.on_translate(texts)
                new_lines.append(Formatter.rejoin_line(tr_texts, delims))
            pre_data["lines"] = new_lines

            notes = pre_data.get("notes", [])
            new_notes = []
            for orig in notes:
                texts, delims = Formatter.split_line(orig)
                tr_texts = await self.tr.on_translate(texts)
                new_notes.append(Formatter.rejoin_line(tr_texts, delims))
            pre_data["notes"] = new_notes


            post = Formatter.post_format(pre_data)
            post_list.append(post)

        # Сохраняем результаты
        try:
            with open(names[0], "w", encoding="utf-8") as f:
                json.dump(pre_list, f, ensure_ascii=False, indent=2)
            with open(names[1], "w", encoding="utf-8") as f:
                f.write("\n\n".join(post_list))
            logging.info(
                "Результаты форматирования сохранены в trans_pre.txt и trans_post.txt"
            )
            print(
                "Тест переводчика завершён. Файлы trans_pre.txt и trans_post.txt созданы."
            )
        except IOError as e:
            logging.error(f"Ошибка при сохранении результатов: {e}")

# Тестирование отправки сообщений
    async def _running_mtest(self):
        logging.info("Тестирование отправки сообщений в телеграм...")
        chat_id = "-1002340163534" # тестовый
        file_name = "notification.txt"
        with open(file_name, "r", encoding="utf-8") as f:
            message = f.read()
            await self.bot.send_notification(message, chat_id, parse_mode="HTML")


# Запуск
if __name__ == "__main__":
    app = BotApp(sys.argv)
    asyncio.run(app.on_run())
