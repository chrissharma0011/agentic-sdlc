from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
import random
import string

app = FastAPI()

storage = {}
click_counts = {}


class ShortenRequest(BaseModel):
    long_url: str


def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!doctype html><html><head><title>URL Shortener</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }
input { width: 100%; padding: 10px; font-size: 1rem; box-sizing: border-box; }
button { margin-top: 10px; padding: 10px 20px; font-size: 1rem; cursor: pointer; }
#result { margin-top: 20px; padding: 15px; background: #f4f4f4; border-radius: 8px; display: none; word-break: break-all; }
.count { color: #666; font-size: 0.9rem; }
</style></head><body>
<h1>URL Shortener</h1>
<p>Paste a link, get a short one.</p>
<input id="url" placeholder="https://example.com" />
<button onclick="shorten()">Shorten</button>
<div id="result"></div>
<script>
async function shorten() {
  const url = document.getElementById('url').value;
  if (!url) return;
  const res = await fetch('/shorten', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({long_url: url})});
  const data = await res.json();
  const short = window.location.origin + '/' + data.short_code;
  const box = document.getElementById('result');
  box.style.display = 'block';
  box.innerHTML = 'Short link: <a href="' + short + '" target="_blank">' + short + '</a>'
    + '<div class="count">clicks: <span id="c">0</span> (refresh after clicking)</div>';
  loadCount(data.short_code);
}
async function loadCount(code) {
  const res = await fetch('/stats/' + code);
  if (res.ok) { const d = await res.json(); document.getElementById('c').textContent = d.clicks; }
}
</script>
</body></html>
"""


@app.post("/shorten")
async def shorten_url(request: ShortenRequest):
    code = generate_short_code()
    storage[code] = request.long_url
    click_counts[code] = 0
    return {"short_code": code}


@app.get("/stats/{short_code}")
async def get_stats(short_code: str):
    if short_code not in click_counts:
        raise HTTPException(status_code=404, detail="not found")
    return {"clicks": click_counts[short_code]}


@app.get("/{short_code}", response_class=RedirectResponse, status_code=307)
async def redirect_to_long_url(short_code: str):
    long_url = storage.get(short_code)
    if long_url is None:
        raise HTTPException(status_code=404, detail="not found")
    click_counts[short_code] += 1
    return RedirectResponse(url=long_url)
