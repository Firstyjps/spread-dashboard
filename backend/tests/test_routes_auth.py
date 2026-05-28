"""Smoke tests for API key auth + read endpoints.

Run inside the backend container:
    docker exec spread-dashboard-backend-1 pytest -q tests/test_routes_auth.py

These tests use FastAPI's TestClient and the in-memory `:memory:` DB by
overriding the db_path setting. They never touch the production DB and
never make real exchange calls.
"""
import os
import pytest

os.environ["API_KEY"] = "test-key-do-not-use-in-prod"
os.environ["DB_PATH"] = ":memory:"

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

settings.api_key = "test-key-do-not-use-in-prod"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_no_auth_required(client):
    r = client.get("/api/v1/health")
    # /health may 200 or 502 if exchanges are unreachable in test env — but never 401
    assert r.status_code != 401


def test_execute_requires_api_key(client):
    r = client.post("/api/v1/execute", json={"symbol": "XAUTUSDT", "side": "LONG_LIGHTER", "amount": 0.001})
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_execute_rejects_wrong_key(client):
    r = client.post(
        "/api/v1/execute",
        headers={"X-API-Key": "wrong-key"},
        json={"symbol": "XAUTUSDT", "side": "LONG_LIGHTER", "amount": 0.001},
    )
    assert r.status_code == 401


def test_reload_config_requires_api_key(client):
    r = client.post("/api/v1/reload-config")
    assert r.status_code == 401


def test_auto_hedge_start_requires_api_key(client):
    r = client.post("/api/v1/auto-hedge/start", json={"symbol": "XAUTUSDT"})
    assert r.status_code == 401


def test_sl_tp_start_requires_api_key(client):
    r = client.post("/api/v1/sl-tp/start", json={"symbol": "XAUTUSDT"})
    assert r.status_code == 401


def test_spreads_history_no_auth(client):
    r = client.get("/api/v1/spreads/history?symbol=XAUTUSDT&days=90")
    # In test env, DB is empty in :memory:, expect 200 with empty history
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "XAUTUSDT"
    assert body["days"] == 90
    assert isinstance(body["history"], list)
    assert "stats" in body


def test_alerts_no_auth(client):
    r = client.get("/api/v1/alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
