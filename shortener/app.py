from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import random
import string
from datetime import datetime
import time

app = FastAPI()

storage = {}
clicks_count = {}

class ShortenRequest(BaseModel):
    long_url: str

class ShortenResponse(BaseModel):
    short_code: str

class StatsResponse(BaseModel):
    clicks: int

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    dependencies: dict  # Added dependencies field

def generate_short_code(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.post("/shorten", response_model=ShortenResponse)
async def shorten(request: ShortenRequest):
    short_code = generate_short_code()
    retries = 3
    for _ in range(retries):
        try:
            storage[short_code] = request.long_url
            clicks_count[short_code] = 0
            return ShortenResponse(short_code=short_code)
        except Exception:
            time.sleep(1)  # Wait before retrying
    raise HTTPException(status_code=500, detail="Failed to store URL after multiple attempts.")

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="UP", timestamp=datetime.now().isoformat(), dependencies={})  # Added empty dependencies

@app.get("/{short_code}")
async def redirect(short_code: str):
    if short_code not in storage:
        raise HTTPException(status_code=404)
    clicks_count[short_code] += 1
    return RedirectResponse(url=storage[short_code], status_code=307)

@app.get("/stats/{short_code}", response_model=StatsResponse)
async def stats(short_code: str):
    if short_code not in clicks_count:
        raise HTTPException(status_code=404)
    return StatsResponse(clicks=clicks_count[short_code])