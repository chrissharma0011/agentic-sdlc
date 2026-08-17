import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app, follow_redirects=False)

def test_shorten_url():
    response = client.post("/shorten", json={"long_url": "http://example.com"})
    assert response.status_code == 200
    assert "short_code" in response.json()

def test_redirect_url():
    # First, shorten a URL to get a short_code
    shorten_response = client.post("/shorten", json={"long_url": "http://example.com"})
    short_code = shorten_response.json()["short_code"]

    # Now, test the redirect
    response = client.get(f"/{short_code}")
    assert response.status_code == 307
    assert response.headers["location"] == "http://example.com"

def test_stats_url():
    # First, shorten a URL to get a short_code
    shorten_response = client.post("/shorten", json={"long_url": "http://example.com"})
    short_code = shorten_response.json()["short_code"]

    # Now, test the stats
    stats_response = client.get(f"/stats/{short_code}")
    assert stats_response.status_code == 200
    assert "clicks" in stats_response.json()

def test_unknown_short_code_redirect():
    response = client.get("/unknown_code")
    assert response.status_code == 404

def test_unknown_short_code_stats():
    response = client.get("/stats/unknown_code")
    assert response.status_code == 404