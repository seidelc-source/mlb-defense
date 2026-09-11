"""PUBLIC_MODE guard: visitors read + compute, never mutate."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def public_mode():
    settings = get_settings()
    settings.public_mode = True
    yield
    settings.public_mode = False


def test_ingest_trigger_blocked_in_public_mode(client, public_mode):
    r = client.post("/api/v1/ingest/statcast", params={"season": 2024})
    assert r.status_code == 403
    assert "Read-only" in r.json()["detail"]


def test_injury_mutation_blocked_in_public_mode(client, public_mode):
    r = client.post(
        "/api/v1/players/00000000-0000-0000-0000-000000000000/injury",
        json={"body_part": "hamstring", "severity": "mild"},
    )
    assert r.status_code == 403


def test_reads_still_allowed_in_public_mode(client, public_mode):
    r = client.get("/health")
    assert r.status_code == 200


def test_mutations_allowed_when_not_public(client):
    # Not public: the guard passes the request through to the router
    # (which may fail deeper for other reasons, but NOT with the 403 guard)
    r = client.post("/api/v1/ingest/statcast", params={"season": 2024})
    assert r.status_code != 403 or "Read-only" not in r.text
