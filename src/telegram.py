import logging, telebot

bot = telebot.TeleBot(token=token, parse_mode=parse_mode)


# Уведомление Телеграм
class TelegramNotifier:
    def __init__(self, token: str = None, chat_id: str = None, parse_mode: str = "markdown"):
        self.chat_id = chat_id

    @bot.message_handler(commands=["start", "help"])
    def send_welcome(message):
        self.bot