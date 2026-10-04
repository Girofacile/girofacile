#!/bin/sh
set -eu
python -m app.migrations
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
