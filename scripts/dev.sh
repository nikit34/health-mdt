#!/usr/bin/env bash
# Local dev — run backend and frontend without Docker.
# Useful when hacking on code. For production use scripts/deploy.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан .env — впиши CLAUDE_CODE_OAUTH_TOKEN (или ANTHROPIC_API_KEY) и перезапусти."
  exit 1
fi

export $(grep -v '^#' .env | xargs -I {} echo {} | tr '\n' ' ')

# Start backend
(cd api && python -m venv .venv 2>/dev/null || true
 source .venv/bin/activate
 pip install -e . --quiet
 mkdir -p ../data ../uploads
 python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload) &
API_PID=$!

# Start frontend
(cd web && npm install --silent && npm run dev) &
WEB_PID=$!

echo ""
echo "Backend: http://localhost:8000"
echo "Web:     http://localhost:3000"
echo "Ctrl+C для остановки"

trap "kill $API_PID $WEB_PID 2>/dev/null; exit" INT TERM
wait
