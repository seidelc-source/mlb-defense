"""Integration tests for API endpoints using httpx AsyncClient.

These tests verify routing, request validation, and response schemas
without requiring a running database — the DB session is overridden
with a mock that returns controlled data.
"""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_session


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def client(mock_session):
    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    yield
    app.dependency_overrides.clear()


PLAYER_ID = uuid.uuid4()


def _mock_player(**overrides):
    defaults = dict(
        id=PLAYER_ID,
        mlbam_id="660271",
        fangraphs_id="19755",
        bbref_id="troutmi01",
        full_name="Mike Trout",
        first_name="Mike",
        last_name="Trout",
        position="CF",
        throws="R",
        bats="R",
        birth_date=date(1991, 8, 7),
        birth_country="USA",
        active=True,
        team_id=uuid.uuid4(),
        pro_debut=date(2011, 7, 8),
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ── Health ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── Players ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_players(client, mock_session):
    player = _mock_player()

    with patch("app.routers.players.PlayerRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.search = AsyncMock(return_value=([player], 1))

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/players")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["players"][0]["full_name"] == "Mike Trout"


@pytest.mark.asyncio
async def test_get_player_not_found(client, mock_session):
    from app.core.exceptions import NotFoundError

    with patch("app.routers.players.PlayerRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_or_raise = AsyncMock(side_effect=NotFoundError("Player", PLAYER_ID))

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/players/{PLAYER_ID}")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_player_detail(client, mock_session):
    player = _mock_player()

    with patch("app.routers.players.PlayerRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_or_raise = AsyncMock(return_value=player)

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/players/{PLAYER_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Mike Trout"
    assert data["position"] == "CF"


# ── Stadiums ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_stadiums(client, mock_session):
    stadium = MagicMock()
    stadium.id = uuid.uuid4()
    stadium.name = "Angel Stadium"
    stadium.city = "Anaheim"
    stadium.state = "CA"
    stadium.latitude = 33.8003
    stadium.longitude = -117.8827
    stadium.mlb_venue_id = "1"
    stadium.altitude_ft = 160
    stadium.roof_type = "open"
    stadium.surface = "grass"
    stadium.outfield_acres = 2.5
    stadium.left_line_ft = 330
    stadium.center_ft = 400
    stadium.right_line_ft = 330
    stadium.park_factor_runs = 1.0
    stadium.park_factor_hr = 1.0

    with patch("app.routers.routers.StadiumRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.list = AsyncMock(return_value=[stadium])

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/stadiums")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Angel Stadium"


# ── Ingest ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_job_not_found(client):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ingest/jobs/nonexistent-id")
    assert resp.status_code == 404


# ── Request validation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spray_invalid_season(client, mock_session):
    # season=0 means "total across seasons", so only negatives are invalid
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/spray/{PLAYER_ID}?season=-1")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_spray_invalid_pitcher_hand(client, mock_session):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/spray/{PLAYER_ID}?pitcher_hand=X")
    assert resp.status_code == 422
