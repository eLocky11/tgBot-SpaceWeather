import logging


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