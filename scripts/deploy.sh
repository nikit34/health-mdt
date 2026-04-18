#!/usr/bin/env bash
# One-click deploy script for Consilium.
#
#   ./scripts/deploy.sh                     # localhost, prompts for API key
#   ./scripts/deploy.sh health.example.com  # VPS with a domain, enables HTTPS
#
# After deploy, prints:
#   - URL to access the dashboard
#   - Access PIN
#   - QR code (PNG at qr.png, ASCII in terminal) for mobile
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}➜${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*" >&2; }

DOMAIN="${1:-localhost}"

# 1. Check prerequisites
command -v docker >/dev/null 2>&1 || { err "docker не установлен. Установи Docker Desktop или Docker Engine."; exit 1; }
docker compose version >/dev/null 2>&1 || { err "docker compose plugin не установлен."; exit 1; }
ok "Docker готов"

# 2. Bootstrap .env
if [[ ! -f .env ]]; then
  info ".env не найден — создаю из шаблона"
  cp .env.example .env

  # Interactive setup for Claude credentials.
  # Option A (preferred): setup token — uses Claude Pro/Max subscription, no API billing.
  # Option B: classic API key — pay-per-use.
  if [[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo ""
    echo "Нужны Claude-учётные данные. Варианты:"
    echo "  1) Setup token — используй подписку Claude Pro/Max. Получи через 'claude setup-token'."
    echo "  2) API key     — pay-per-use. Получи на https://console.anthropic.com"
    echo ""
    echo "Что впишешь — то и будет использовано. Пустая строка — продолжить без LLM."
    read -r -p "CLAUDE_CODE_OAUTH_TOKEN (или Enter чтобы ввести API key): " USER_TOKEN
    if [[ -n "$USER_TOKEN" ]]; then
      sed -i.bak "s|^CLAUDE_CODE_OAUTH_TOKEN=.*|CLAUDE_CODE_OAUTH_TOKEN=$USER_TOKEN|" .env && rm .env.bak
      ok "Setup token записан (агенты пойдут через подписку)"
    else
      read -r -p "ANTHROPIC_API_KEY: " USER_KEY
      if [[ -n "$USER_KEY" ]]; then
        sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$USER_KEY|" .env && rm .env.bak
        ok "API key записан"
      else
        warn "Без учётных данных агенты не заработают — UI всё равно поднимется"
      fi
    fi
  fi

  # Generate access PIN
  PIN=$(awk 'BEGIN{srand(); printf "%06d", int(rand()*1000000)}')
  sed -i.bak "s|^ACCESS_PIN=.*|ACCESS_PIN=$PIN|" .env && rm .env.bak
  ok "Сгенерирован PIN: $PIN"
else
  ok ".env уже существует — использую"
  PIN=$(grep -E '^ACCESS_PIN=' .env | cut -d'=' -f2)
fi

# 3. Set domain + Caddy site address
sed -i.bak "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env && rm .env.bak
ok "DOMAIN=$DOMAIN"
# For localhost: Caddy needs "http://localhost" to skip auto-HTTPS
# For real domains: just the domain (Caddy handles TLS)
if [[ "$DOMAIN" == "localhost" ]]; then
  export CADDY_SITE_ADDRESS="http://localhost"
else
  export CADDY_SITE_ADDRESS="$DOMAIN"
fi

# 4. Build & start
# First-time build: 3-6 мин. api-образ включает Node.js + @anthropic-ai/claude-code
# (нужен для agents через subscription-путь). Python-deps ставятся через editable install.
info "Сборка контейнеров (первый раз: 3-6 минут, Node + claude CLI качаются в образ)…"
docker compose build --progress=plain 2>&1 | tail -25

info "Запуск стека…"
docker compose up -d

# 5. Wait for health
# 180s margin — первый старт api подгружает claude-agent-sdk + anthropic + weasyprint,
# плюс init_db() накатывает additive migrations.
info "Ожидаю готовности API…"
for i in {1..90}; do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    ok "API здоров"
    break
  fi
  sleep 2
  if [[ $i -eq 90 ]]; then
    err "API не стартовал за 180 секунд. Логи: docker compose logs api"
    exit 1
  fi
done

# 5a. Detect which LLM path is active, for user-friendly output below.
LLM_MODE=$(docker compose exec -T api python -c "
from src.config import get_settings
print(get_settings().llm_auth_mode)
" 2>/dev/null | tr -d '\r\n' || echo "none")

# 6. Print access info
if [[ "$DOMAIN" == "localhost" ]]; then
  URL="http://localhost"
else
  URL="https://$DOMAIN"
fi

# Generate QR code (PNG + ASCII)
QR_URL="${URL}/#pin=${PIN}"
if command -v qrencode >/dev/null 2>&1; then
  qrencode -o qr.png -s 8 "$QR_URL" 2>/dev/null || true
  QR_ASCII=$(qrencode -t UTF8 "$QR_URL" 2>/dev/null || echo "")
elif docker run --rm -i alpine sh -c "apk add --quiet qrencode && qrencode -t UTF8 '$QR_URL'" >/tmp/qr.txt 2>/dev/null; then
  QR_ASCII=$(cat /tmp/qr.txt)
else
  QR_ASCII="(установи qrencode локально для ASCII QR: brew install qrencode)"
fi

# Human-readable LLM path description for the output banner
case "$LLM_MODE" in
  setup_token) LLM_LABEL="✓ Claude Pro/Max subscription (через CLI в api-контейнере)";;
  api_key)     LLM_LABEL="✓ Anthropic API key (pay-per-use, prompt caching)";;
  none)        LLM_LABEL="⚠ LLM не настроен — добавь CLAUDE_CODE_OAUTH_TOKEN или ANTHROPIC_API_KEY в .env";;
  *)           LLM_LABEL="$LLM_MODE";;
esac

cat <<EOF

${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${GREEN}  Consilium запущен${NC}
${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

  URL:    $URL
  PIN:    $PIN
  LLM:    $LLM_LABEL
  Bot:    отправь /start боту (если токен настроен)

  Мобильный QR (отсканируй — попадёшь сразу в дашборд):

$QR_ASCII

  Логи:        docker compose logs -f
  Остановка:   docker compose down
  Обновление:  git pull && docker compose up -d --build

${YELLOW}Первый шаг:${NC} открой $URL, введи PIN и пройди онбординг.
EOF
