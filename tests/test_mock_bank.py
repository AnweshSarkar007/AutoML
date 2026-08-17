"""Smoke tests for the mock bank backend. TestClient only — no live server."""

from backend import data
from backend.app import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(app)


def test_login_succeeds_with_valid_credentials():
    response = _client().post(
        "/api/login", json={"username": data.USERNAME, "password": data.PASSWORD}
    )

    assert response.status_code == 200
    assert "session_id" in response.cookies


def test_login_fails_with_invalid_credentials():
    response = _client().post("/api/login", json={"username": data.USERNAME, "password": "wrong"})

    assert response.status_code == 401
    assert "session_id" not in response.cookies


def test_two_sessions_get_different_account_ids():
    client_a = _client()
    client_a.post("/api/login", json={"username": data.USERNAME, "password": data.PASSWORD})
    ids_a = {account["id"] for account in client_a.get("/api/accounts").json()}

    client_b = _client()
    client_b.post("/api/login", json={"username": data.USERNAME, "password": data.PASSWORD})
    ids_b = {account["id"] for account in client_b.get("/api/accounts").json()}

    assert ids_a.isdisjoint(ids_b)
