from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import random
import string
from datetime import datetime

app = FastAPI()

# In-memory storage
url_storage = {}
click_counts = {}

class ShortenRequest(BaseModel):
    long_url: str

class ShortenResponse(BaseModel):
    short_code: str

class StatsResponse(BaseModel):
    clicks: int

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

def generate_short_code(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

@app.post("/shorten", response_model=ShortenResponse)
async def shorten_url(request: ShortenRequest):
    short_code = generate_short_code()
    url_storage[short_code] = request.long_url
    click_counts[short_code] = 0
    return ShortenResponse(short_code=short_code)

@app.get("/{short_code}")
async def redirect_to_long_url(short_code: str):
    long_url = url_storage.get(short_code)
    if long_url is None:
        raise HTTPException(status_code=404, detail="URL not found")
    click_counts[short_code] += 1
    return RedirectResponse(url=long_url, status_code=307)

@app.get("/stats/{short_code}", response_model=StatsResponse)
async def get_stats(short_code: str):
    clicks = click_counts.get(short_code, 0)
    return StatsResponse(clicks=clicks)