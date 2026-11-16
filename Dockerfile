FROM python:3.12-slim-bookworm

# Match the PostgreSQL 16 server used by docker-compose, including restore tools.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock

COPY app ./app
COPY static ./static
COPY scripts ./scripts

# Utente senza privilegi (uid 10001). Sul server le cartelle montate (backups, data/ztl)
# devono appartenere a questo uid: vedi deploy/README.md.
RUN useradd --system --uid 10001 --no-create-home --home-dir /app girofacile \
    && mkdir -p /app/backups /app/data/ztl \
    && chown -R girofacile:girofacile /app/backups /app/data
USER girofacile

EXPOSE 8000

# DATABASE_URL, APP_SECRET e credenziali devono essere fornite dall'ambiente.
CMD ["sh", "/app/scripts/start_app.sh"]
