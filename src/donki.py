import logging, requests


# NASA DONKI API client
class DonkiClient:
    def __init__(self, api_key: str, url: str):
        self.api_key = api_key
        self.url = url

    def fetch(self) -> list:
        params = {
            "api_key": self.api_key,
        }
        logging.info(f"Fetching DONKI events data")
        resp = requests.get(self.url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data