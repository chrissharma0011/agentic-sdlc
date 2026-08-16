import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app, follow_redirects=False)

def test_shorten():
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    assert response.status_code == 200
    assert "short_code" in response.json()

def test_redirect():
    # First, shorten a URL to get a short code
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_code = response.json()["short_code"]

    # Now, test the redirect
    response = client.get(f"/{short_code}")
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com"

def test_stats():
    # First, shorten a URL to get a short code
    response = client.post("/shorten", json={"long_url": "https://example.com"})
    short_code = response.json()["short_code"]

    # Simulate a click (this part would depend on your implementation)
    # Assuming there's a mechanism to increment clicks when the short code is accessed
    client.get(f"/{short_code}")  # This would increment the click count

    # Now, test the stats
    response = client.get(f"/stats/{short_code}")
    assert response.status_code == 200
    assert "clicks" in response.json()