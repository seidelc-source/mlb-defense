#!/usr/bin/env python3
"""Start the MLB Defensive Positioning App with a single command.

Uses Homebrew to install/start PostgreSQL and Redis — no Docker required.
"""

import subprocess
import sys
import os
import signal
import shutil
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")
VENV_PYTHON = os.path.join(BACKEND, ".venv", "bin", "python")
VENV_PIP = os.path.join(BACKEND, ".venv", "bin", "pip")
VENV_ALEMBIC = os.path.join(BACKEND, ".venv", "bin", "alembic")

DB_NAME = "mlbdefense"
DB_USER = "mlb"
DB_PASS = "mlb"

procs: list[subprocess.Popen] = []


def run(cmd, cwd=ROOT, check=True, **kwargs):
    print(f"  >>> {cmd}")
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check, **kwargs)


def run_quiet(cmd, cwd=ROOT):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)


def has(binary):
    return shutil.which(binary) is not None


def section(msg):
    print(f"\n{'=' * 60}\n{msg}\n{'=' * 60}")


def cleanup(sig=None, frame=None):
    print("\n\nShutting down servers...")
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("Servers stopped. (Postgres and Redis are still running via brew services.)")
    print("To stop them: brew services stop postgresql@16 && brew services stop redis")
    sys.exit(0)


# ── Homebrew installs ────────────────────────────────────────────────────────

def ensure_postgres():
    if has("psql"):
        print("  PostgreSQL already installed.")
        return

    section("Installing PostgreSQL via Homebrew...")
    run("brew install postgresql@16")
    # Homebrew puts it in a keg, link it
    run("brew link postgresql@16 --force", check=False)


def ensure_redis():
    if has("redis-server"):
        print("  Redis already installed.")
        return

    section("Installing Redis via Homebrew...")
    run("brew install redis")


def start_service(name):
    result = run_quiet(f"brew services info {name} --json")
    if '"running": true' in result.stdout or '"running":true' in result.stdout:
        print(f"  {name} already running.")
        return
    print(f"  Starting {name}...")
    run(f"brew services start {name}")
    time.sleep(2)


def wait_for_postgres(retries=15):
    for _ in range(retries):
        r = run_quiet("pg_isready -h localhost -p 5432")
        if r.returncode == 0:
            return True
        time.sleep(1)
    return False


def setup_database():
    # Create the role if it doesn't exist
    check = run_quiet(f'psql -h localhost -p 5432 -U {DB_USER} -d postgres -c "SELECT 1"')
    if check.returncode != 0:
        print(f"  Creating database role '{DB_USER}'...")
        run(f'createuser -h localhost -p 5432 -s {DB_USER} 2>/dev/null || true')
        run(
            f'psql -h localhost -p 5432 -d postgres -c '
            f"\"ALTER USER {DB_USER} WITH PASSWORD '{DB_PASS}';\"",
            check=False,
        )
    else:
        print(f"  Role '{DB_USER}' already exists.")

    # Create the database if it doesn't exist
    check = run_quiet(f"psql -h localhost -p 5432 -U {DB_USER} -d {DB_NAME} -c 'SELECT 1'")
    if check.returncode != 0:
        print(f"  Creating database '{DB_NAME}'...")
        run(f"createdb -h localhost -p 5432 -U {DB_USER} {DB_NAME}")
    else:
        print(f"  Database '{DB_NAME}' already exists.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if not has("brew"):
        print("ERROR: Homebrew is required. Install from https://brew.sh", file=sys.stderr)
        sys.exit(1)

    # 1. Install & start Postgres and Redis
    section("Setting up PostgreSQL and Redis...")
    ensure_postgres()
    ensure_redis()
    start_service("postgresql@16")
    start_service("redis")

    print("  Waiting for Postgres to accept connections...")
    if not wait_for_postgres():
        print("ERROR: Postgres did not start in time.", file=sys.stderr)
        sys.exit(1)
    print("  Postgres is ready.")

    setup_database()

    # 2. Backend venv
    if not os.path.exists(VENV_PYTHON):
        section("Creating backend virtual environment...")
        run(f"{sys.executable} -m venv .venv", cwd=BACKEND)
        run(f"{VENV_PIP} install -e '.[dev]'", cwd=BACKEND)
    else:
        print("\n  Backend venv already exists.")

    # 3. Write .env so the backend can connect with password auth
    env_path = os.path.join(BACKEND, ".env")
    if not os.path.exists(env_path):
        section("Writing backend/.env...")
        with open(env_path, "w") as f:
            f.write(f"DATABASE_URL=postgresql+asyncpg://{DB_USER}:{DB_PASS}@localhost:5432/{DB_NAME}\n")
            f.write("REDIS_URL=redis://localhost:6379/0\n")
            f.write("ENVIRONMENT=development\n")
        print("  Created backend/.env")

    # 4. Migrations
    section("Running database migrations...")
    run(f"{VENV_ALEMBIC} upgrade head", cwd=BACKEND)

    # 5. Seed data
    section("Seeding stadiums and teams...")
    run(f"{VENV_PYTHON} -m scripts.seed", cwd=BACKEND, check=False)

    # 6. Frontend deps
    if not os.path.exists(os.path.join(FRONTEND, "node_modules")):
        section("Installing frontend dependencies...")
        run("npm install", cwd=FRONTEND)
    else:
        print("\n  Frontend node_modules already exists.")

    # 7. Start servers
    section("Starting servers...")
    backend = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
        cwd=BACKEND,
    )
    procs.append(backend)

    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND,
    )
    procs.append(frontend)

    print(f"""
{'=' * 60}
  App is running!

  Frontend:  http://localhost:5173
  Backend:   http://localhost:8000
  API Docs:  http://localhost:8000/docs

  Press Ctrl+C to stop the servers.
{'=' * 60}
""")

    for p in procs:
        p.wait()


if __name__ == "__main__":
    main()
