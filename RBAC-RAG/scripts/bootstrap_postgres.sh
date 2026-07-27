#!/usr/bin/env bash
# Sentry RAG - Postgres + pgvector bootstrap
# Installs PostgreSQL 15 + pgvector 0.7.4, creates the sentry_rag DB, and wires up
# supervisor to run postgres. Idempotent — safe to re-run after a pod restart.

set -euo pipefail

log() { echo "[bootstrap $(date +%H:%M:%S)] $*"; }

# --- 1) Ensure PostgreSQL 15 is installed ---
if [ ! -x /usr/lib/postgresql/15/bin/postgres ]; then
  log "Installing PostgreSQL 15..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y >/dev/null 2>&1 || true
  apt-get install -y postgresql postgresql-contrib postgresql-server-dev-15 build-essential git >/dev/null
else
  log "PostgreSQL 15 already installed."
fi

# Ensure postgres user exists
if ! id postgres >/dev/null 2>&1; then
  log "ERROR: postgres system user missing after install."
  exit 1
fi

# --- 2) Build & install pgvector if not present ---
if [ ! -f /usr/lib/postgresql/15/lib/vector.so ] && [ ! -f /usr/share/postgresql/15/extension/vector.control ]; then
  log "Building pgvector 0.7.4 from source..."
  rm -rf /tmp/pgvector-build
  git clone --depth 1 --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector-build >/dev/null 2>&1
  ( cd /tmp/pgvector-build && PG_CONFIG=/usr/lib/postgresql/15/bin/pg_config make >/dev/null 2>&1 && PG_CONFIG=/usr/lib/postgresql/15/bin/pg_config make install >/dev/null 2>&1 )
  rm -rf /tmp/pgvector-build
else
  log "pgvector already present."
fi

# --- 3) Configure trust auth + runtime dir ---
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql

cat > /etc/postgresql/15/main/pg_hba.conf <<'EOF'
local   all             postgres                                trust
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
EOF

# --- 4) Supervisor entry for postgres ---
cat > /etc/supervisor/conf.d/postgres.conf <<'EOF'
[program:postgres]
command=/usr/lib/postgresql/15/bin/postgres -D /var/lib/postgresql/15/main -c config_file=/etc/postgresql/15/main/postgresql.conf
user=postgres
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/postgres.out.log
stderr_logfile=/var/log/supervisor/postgres.err.log
priority=100
EOF

# --- 5) Start / reload postgres via supervisor ---
if pgrep -x supervisord >/dev/null 2>&1; then
  supervisorctl reread >/dev/null 2>&1 || true
  supervisorctl update >/dev/null 2>&1 || true
  supervisorctl start postgres >/dev/null 2>&1 || true
else
  log "Supervisord not running; starting it..."
  supervisord -c /etc/supervisor/supervisord.conf >/dev/null 2>&1 &
fi

# --- 6) Wait for postgres to accept connections ---
for i in $(seq 1 30); do
  if sudo -u postgres /usr/lib/postgresql/15/bin/pg_isready -q; then
    log "Postgres is ready."
    break
  fi
  sleep 1
done

# --- 7) Create DB + enable pgvector (idempotent) ---
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='sentry_rag'" | grep -q 1; then
  log "Creating database sentry_rag..."
  sudo -u postgres psql -c "CREATE DATABASE sentry_rag;" >/dev/null
fi
sudo -u postgres psql -d sentry_rag -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
sudo -u postgres psql -d sentry_rag -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null

log "Bootstrap complete. sentry_rag DB + pgvector ready."
