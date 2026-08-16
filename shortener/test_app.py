import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app, follow_redirects=False)

def test_shorten_url():
    response = client.post("/shorten", json={"long_url": "http://example.com"})
    assert response.status_code == 200
    assert "short_code" in response.json()

def test_redirect_url():
    # First, shorten the URL to get the short_code
    response = client.post("/shorten", json={"long_url": "http://example.com"})
    short_code = response.json()["short_code"]

    # Now, test the redirect
    response = client.get(f"/{short_code}")
    assert response.status_code == 307
    assert response.headers["location"] == "http://example.com"

def test_stats_url():
    # First, shorten the URL to get the short_code
    response = client.post("/shorten", json={"long_url": "http://example.com"})
    short_code = response.json()["short_code"]

    # Check initial clicks
    response = client.get(f"/stats/{short_code}")
    assert response.status_code == 200
    assert response.json()["clicks"] == 0

    # Simulate a click
    client.get(f"/{short_code}")

    # Check clicks after one access
    response = client.get(f"/stats/{short_code}")
    assert response.status_code == 200
    assert response.json()["clicks"] == 1

def test_not_found_redirect():
    response = client.get("/nonexistent")
    assert response.status_code == 404

def test_not_found_stats():
    response = client.get("/stats/nonexistent")
    assert response.status_code == 404