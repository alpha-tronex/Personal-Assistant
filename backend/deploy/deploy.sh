#!/usr/bin/env bash
# Runs on the Hetzner box only, as alphathiam, invoked by the forced-command
# GitHub Actions deploy key (see backend/deploy/README.md). Installed at
# /opt/assistant/deploy.sh — that copy is what runs; this one is the source.
set -euo pipefail

cd /opt/assistant/repo
git fetch origin main
git reset --hard origin/main

GIT_SHA=$(git rev-parse --short=7 HEAD)
export GIT_SHA

cd backend
# Build before touching the running container so downtime is just the swap.
docker compose -f docker-compose.prod.yml build

# One-time cutover (2026-10): the original container was started with a bare
# `docker run`, so compose doesn't own it and `up` would fail on the name.
# Remove it only if it isn't compose-managed; a no-op on every later deploy.
if docker inspect personal-assistant >/dev/null 2>&1 \
   && [ -z "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' personal-assistant)" ]; then
  echo "Replacing hand-started personal-assistant container with the compose-managed one."
  docker rm -f personal-assistant
fi

docker compose -f docker-compose.prod.yml up -d
docker image prune -f

# Both the real app (:8000) and the public demo (:8001) must report the new SHA.
healthy() {
  curl -fsS "http://127.0.0.1:$1/healthz" | grep -q "\"version\":\"${GIT_SHA}\""
}
for _ in $(seq 1 12); do
  if healthy 8000 && healthy 8001; then
    echo "Deploy healthy at ${GIT_SHA} (app + demo)."
    exit 0
  fi
  sleep 5
done

echo "health check failed: /healthz on :8000 and :8001 never both reported version ${GIT_SHA}" >&2
docker compose -f docker-compose.prod.yml logs --tail 50
exit 1
