#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Setup PostgreSQL server GiroFacile v72"
if ! command -v psql >/dev/null 2>&1; then
  echo "Installo PostgreSQL e client..."
  apt update
  apt install -y postgresql postgresql-client
fi
DB_USER="girofacile"
DB_NAME="girofacile"
DB_PASSWORD="${GIROFACILE_DB_PASSWORD:-$(openssl rand -base64 24 | tr -d '=+/') }"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
echo "DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"
echo "Salva questa DATABASE_URL nel file .env del server."
