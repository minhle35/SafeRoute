#!/usr/bin/env bash
# Finds a free host port within 50 of each service's default and writes
# APP_PORT / PROMETHEUS_PORT / GRAFANA_PORT into .env for docker-compose
# variable substitution. Run before `docker compose up`.
set -euo pipefail

ENV_FILE="$(dirname "$0")/../.env"
RANGE=50

is_free() {
  ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

find_free_port() {
  local base="$1"
  for ((port = base; port < base + RANGE; port++)); do
    if is_free "$port"; then
      echo "$port"
      return 0
    fi
  done
  echo "No free port found in range $base-$((base + RANGE - 1))" >&2
  return 1
}

upsert_env_var() {
  local key="$1" value="$2"
  touch "$ENV_FILE"
  # Ensure the file ends with a newline before appending, otherwise the new
  # var gets glued onto the end of the last existing line.
  if [[ -s "$ENV_FILE" ]] && [[ "$(tail -c1 "$ENV_FILE")" != "" ]]; then
    echo >> "$ENV_FILE"
  fi
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s/^${key}=.*/${key}=${value}/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

app_port=$(find_free_port 8000)
prometheus_port=$(find_free_port 9090)
grafana_port=$(find_free_port 3000)

upsert_env_var APP_PORT "$app_port"
upsert_env_var PROMETHEUS_PORT "$prometheus_port"
upsert_env_var GRAFANA_PORT "$grafana_port"

echo "APP_PORT=$app_port"
echo "PROMETHEUS_PORT=$prometheus_port"
echo "GRAFANA_PORT=$grafana_port"
