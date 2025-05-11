import logging

from telegram import Bot


# Уведомление Телеграм
class TelegramNotifier(Bot):
    def __init__(self, token: str = None) -> None:
        super().__init__(token)

    async def send_notification(self, message: str, chat_id: str,  parse_mode: str = "MarkdownV2") -> None:
        try: 
            await self.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logging.info(f"Message delivered into Telegram. Chat ID: {chat_id}")
        except Exception as e:
            logging.error(f"send_notification error: {e}")