import logging, requests, aiohttp


# NASA DONKI API client
class DonkiClient:
    def __init__(self, api_key: str, url: str):
        self.api_key = api_key
        self.url = url

    # Basic fetch (legacy)
    def fetch(self) -> list:
        params = {
            "api_key": self.api_key,
        }
        logging.info(f"Fetching DONKI events data")
        resp = requests.get(self.url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data
    
    # New async fetch
    async def new_fetch(self) -> list:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, params={"api_key": self.api_key}) as resp:
                resp.raise_for_status()
                return await resp.json()