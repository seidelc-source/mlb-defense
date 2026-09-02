# Starting Up the MLB Defensive Positioning App

## Prerequisites

- **Docker & Docker Compose** (for PostgreSQL and Redis)
- **Python 3.11+** (backend)
- **Node.js 18+** and **npm** (frontend)

---

## Option A: Local Development (recommended)

### 1. Start the data stores

From the project root:

```bash
docker compose up db redis -d
```

This launches:
- **PostgreSQL 16** on `localhost:5432` (user: `mlb`, password: `mlb`, database: `mlbdefense`)
- **Redis 7** on `localhost:6379`

Verify they're healthy:

```bash
docker compose ps
```

### 2. Set up the backend

```bash
cd backend
```

#### Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate    # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

#### Create a `.env` file (optional)

The defaults work out of the box with the Docker containers above. If you need to override anything, create `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://mlb:mlb@localhost:5432/mlbdefense
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
LOG_LEVEL=INFO
```

#### Run database migrations

```bash
alembic upgrade head
```

#### Seed reference data (stadiums and teams)

```bash
python -m scripts.seed
```

This loads all 30 MLB stadiums (with coordinates, wall distances, altitudes, roof types) and all 30 teams.

#### Load real data (players, pitches, fielding, spray profiles)

```bash
python -m scripts.ingest_all --season 2024 --start 2024-06-01 --end 2024-06-30
```

This pulls team rosters from the MLB Stats API, Statcast pitch data via
pybaseball for the date range, fielding leaderboards (OAA / sprint speed),
and then aggregates batter spray profiles. Re-runs are idempotent.

Verify everything end-to-end (with the backend running):

```bash
python -m scripts.smoke
```

#### Start the backend server

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now live at **http://localhost:8000**. Docs at **http://localhost:8000/docs**.

### 3. Set up the frontend

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend is now live at **http://localhost:5173**.

### 4. Run tests

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

---

## Option B: Full Docker Compose

Run everything in containers (backend, frontend, database, Redis):

```bash
docker compose up --build
```

| Service  | URL                        |
| -------- | -------------------------- |
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |
| API Docs | http://localhost:8000/docs |
| Postgres | localhost:5432             |
| Redis    | localhost:6379             |

---

## Verifying the setup

1. **Health check**: `curl http://localhost:8000/health` should return `{"status":"ok","version":"0.1.0"}`
2. **API docs**: Open http://localhost:8000/docs in a browser
3. **Frontend**: Open http://localhost:5173 — you should see the nav bar with Field View, Spray Analysis, Players, and Ingest tabs

---

## Stopping everything

```bash
# If using Option A:
# Ctrl+C in each terminal running uvicorn / npm run dev, then:
docker compose down

# To also delete the database volume:
docker compose down -v
```

---

## Troubleshooting

| Problem | Fix |
| ------- | --- |
| `pg_isready` fails | Wait a few seconds for Postgres to finish initializing, or check `docker compose logs db` |
| `ModuleNotFoundError` | Make sure the venv is activated: `source .venv/bin/activate` |
| Port 5432 already in use | Another Postgres is running locally. Stop it or change the port in `docker-compose.yml` |
| Port 8000 or 5173 in use | Kill the existing process: `lsof -ti:8000 \| xargs kill` |
| Alembic migration fails | Ensure the database is running and the `DATABASE_URL` matches your Postgres credentials |
| Frontend can't reach API | The frontend proxies to `http://localhost:8000`. Make sure the backend is running. |
