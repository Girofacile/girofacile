#!/usr/bin/env bash
# The pinned official image includes bash/coreutils, but not curl or wget.
# Compose's timeout bounds connection/read time; no dataset-dependent coordinate.
set -euo pipefail
exec 3<>/dev/tcp/127.0.0.1/${OSRM_HEALTH_PORT:-5000}
printf 'GET /nearest/v1/driving/0,0?number=1 HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
response=$(cat <&3)
[[ "$response" == HTTP/1.*' 200 '* ]]
[[ "$response" =~ \"code\"[[:space:]]*:[[:space:]]*\"Ok\" ]]
[[ "$response" =~ \"waypoints\"[[:space:]]*:[[:space:]]*\[[[:space:]]*\{ ]]
