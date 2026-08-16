from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import random
import string

app = FastAPI()

storage = {}
click_counts = {}

class ShortenRequest(BaseModel):
    long_url: str

class ShortenResponse(BaseModel):
    short_code: str

def generate_short_code(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.post("/shorten", response_model=ShortenResponse)
def shorten_url(request: ShortenRequest):
    short_code = generate_short_code()
    storage[short_code] = request.long_url
    click_counts[short_code] = 0
    return ShortenResponse(short_code=short_code)

@app.get("/{short_code}", response_class=RedirectResponse, status_code=307)
def redirect_to_long_url(short_code: str):
    long_url = storage.get(short_code)
    if long_url is None:
        raise HTTPException(status_code=404, detail="Short code not found")
    click_counts[short_code] += 1
    return RedirectResponse(url=long_url)

@app.get("/stats/{short_code}")
def get_stats(short_code: str):
    if short_code not in click_counts:
        raise HTTPException(status_code=404, detail="Short code not found")
    return {"clicks": click_counts[short_code]}

@app.get("/health")
def health_check():
    return {"status": "healthy"}