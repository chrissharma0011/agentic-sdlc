import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_shorten():
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    assert response.status_code == 200
    assert "short_code" in response.json()

def test_redirect():
    # First, create a short code
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_code = response.json()["short_code"]

    # Test the redirect
    response = client.get(f"/{short_code}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com"

def test_stats():
    # First, create a short code
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_code = response.json()["short_code"]

    # Test the stats
    response = client.get(f"/stats/{short_code}")
    assert response.status_code == 200
    assert "clicks" in response.json()