import pytest
from fastapi.testclient import TestClient
from app import app, URLMapping

client = TestClient(app)
url_mapping = URLMapping()

def test_shorten_url():
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    assert response.status_code == 200
    assert "short_url" in response.json()

def test_redirect_to_long_url():
    # First, shorten a URL to get a short URL
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_url = response.json()["short_url"]

    # Now, redirect using the short URL
    response = client.get(f"/{short_url}")
    assert response.status_code == 200
    assert response.url == "https://example.com"

def test_click_count():
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_url = response.json()["short_url"]

    # Redirect to increment click count
    client.get(f"/{short_url}")
    client.get(f"/{short_url}")

    # Check click count
    click_count = url_mapping.get_click_count(short_url)
    assert click_count == 2

def test_invalid_short_url():
    response = client.get("/invalid_short_url")
    assert response.status_code == 404
    assert response.json() == {"detail": "Short URL not found"}