import sys, asyncio

from app import BotApp

# Start
if __name__ == "__main__":
    app = BotApp(sys.argv)
    asyncio.run(app.on_run())