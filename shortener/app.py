from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Dict
import random
import string

app = FastAPI()

class URLMapping:
    def __init__(self):
        self.url_map: Dict[str, Dict] = {}

    def shorten_url(self, long_url: str) -> str:
        short_url = self.generate_short_url()
        self.url_map[short_url] = {"long_url": long_url, "click_count": 0}
        return short_url

    def generate_short_url(self) -> str:
        characters = string.ascii_letters + string.digits
        short_url = ''.join(random.choices(characters, k=6))
        while short_url in self.url_map:
            short_url = ''.join(random.choices(characters, k=6))
        return short_url

    def get_long_url(self, short_url: str) -> str:
        if short_url in self.url_map:
            self.url_map[short_url]["click_count"] += 1
            return self.url_map[short_url]["long_url"]
        raise HTTPException(status_code=404, detail="Short URL not found")

    def get_click_count(self, short_url: str) -> int:
        if short_url in self.url_map:
            return self.url_map[short_url]["click_count"]
        raise HTTPException(status_code=404, detail="Short URL not found")

url_mapping = URLMapping()

class URLRequest(BaseModel):
    long_url: HttpUrl

@app.post("/shorten")
def shorten_url(request: URLRequest):
    short_url = url_mapping.shorten_url(request.long_url)
    return {"short_url": short_url}

@app.get("/{short_url}")
def redirect_to_long_url(short_url: str):
    long_url = url_mapping.get_long_url(short_url)
    return {"long_url": long_url}

@app.get("/stats/{short_url}")
def get_click_count(short_url: str):
    click_count = url_mapping.get_click_count(short_url)
    return {"click_count": click_count}