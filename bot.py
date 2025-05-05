import os, sys, json, asyncio, logging

from src.donki import DonkiClient
from src.database import DataBase
from src.formatter import Formatter
from src.telegram import TelegramNotifier
from src.translator import Translator


"""
ПОРЯДОК РАБОТЫ ПРИЛОЖЕНИЯ:
-...
-сохранение в бд
-отправка сообщений
"""


# Логирование
logging.basicConfig(
    filename="logs.log",  # Имя файла
    encoding="utf-8",  # Кодировка
    level=logging.INFO,  # Уровень - DEBUG: минимальный уровень логирования
    format="%(asctime)s - %(levelname)s - %(message)s",  # формат сообщений
    filemode="w",  # Мод - перезапись в файл
)

# Конфигурация
TELEGRAM_TOKEN = "8121913581:AAEcplN7VQ9r2uvAelVbCegaxCQPusdFBgk"
CHAT_ID = "-1002514102114"
NASA_API_KEY = "5RqBZjQI4rrfEXoNIwpbEKdYF57IVQkyzBGX1d2h"
DEEPL_AUTH_KEY = "c5a6de6d-01ab-46d1-8e8f-0e2946813d0f:fx"
DATABASE_PATH = "data.db"
DONKI_URL = "https://api.nasa.gov/DONKI/notifications"



# Функция для тестирования
async def formate_test(
    input_file="donki_output.json", output_file="out_orig.txt", trans: bool = False
):
    logging.info("Starting Formatter test")

    db = DataBase(DATABASE_PATH)
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
                data["summary_text"] = await tr.translate(
                    text=data["summary_text"], target_lang="RU", test=True
                )
                if data["notes"]:
                    data["notes"] = await tr.translate(
                        data["notes"], target_lang="RU", test=True
                    )
            message = Formatter.post_format(data)
            outf.write(message + "\n" + ("=" * 80) + "\n")


async def donki_test(output_file="donki_output.json"):
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
    db = DataBase(DATABASE_PATH)
    client = DonkiClient(NASA_API_KEY, DONKI_URL)
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
