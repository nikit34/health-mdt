#!/usr/bin/env bash
# One-command DEMO — zero UX friction.
#
#   ./scripts/demo.sh
#
# What it does:
#   1. Bootstraps .env (no API key required — you can still use UI without LLM).
#   2. Generates a PIN.
#   3. Builds + starts the stack.
#   4. Seeds the DB with a fully lived-in demo user:
#      — 45 days of metrics, 12m of lab trends, 3 meds, 2 docs,
#        2 MDT reports + 1 monthly, 7 daily briefs, 9 tasks, 2 chats.
#   5. Opens the browser straight onto the dashboard with auto-login via URL hash.
#
# You see the product populated in < 3 minutes, with zero clicks of onboarding.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${B}➜${NC} $*"; }
ok()    { echo -e "${G}✓${NC} $*"; }
warn()  { echo -e "${Y}⚠${NC} $*"; }

command -v docker >/dev/null 2>&1 || { echo "docker не установлен"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose не установлен"; exit 1; }

# 1. .env — no API key prompt (demo runs without LLM)
if [[ ! -f .env ]]; then
  info "Создаю .env из шаблона (LLM-ключ не спрашиваю — демо работает и без него)"
  cp .env.example .env
fi

# 2. Always regenerate PIN for demo (overwrite previous if any)
PIN=$(awk 'BEGIN{srand(); printf "%06d", int(rand()*1000000)}')
if grep -q '^ACCESS_PIN=' .env; then
  sed -i.bak "s|^ACCESS_PIN=.*|ACCESS_PIN=$PIN|" .env && rm -f .env.bak
else
  echo "ACCESS_PIN=$PIN" >> .env
fi
if grep -q '^DOMAIN=' .env; then
  sed -i.bak "s|^DOMAIN=.*|DOMAIN=localhost|" .env && rm -f .env.bak
else
  echo "DOMAIN=localhost" >> .env
fi
ok "PIN: $PIN"

export CADDY_SITE_ADDRESS="http://localhost"

# 3. Build + up
info "Сборка и запуск (2-4 мин в первый раз)…"
docker compose build --progress=plain 2>&1 | tail -10
docker compose up -d

# 4. Wait for API
info "Жду готовности API…"
for i in {1..60}; do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    ok "API здоров"
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "API не стартовал за 120с. Логи: docker compose logs api"
    exit 1
  fi
done

# 5. Seed
info "Засеваю демо-данные…"
docker compose exec -T api python -m src.seed
ok "Данные на месте"

# 6. Open browser straight on populated dashboard (auto-login via URL hash)
URL="http://localhost/#pin=${PIN}"
info "Открываю браузер на $URL"
if [[ "$OSTYPE" == "darwin"* ]]; then
  open "$URL" 2>/dev/null || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" 2>/dev/null || true
elif command -v wslview >/dev/null 2>&1; then
  wslview "$URL" 2>/dev/null || true
fi

cat <<EOF

${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${G}  health-mdt — DEMO запущен${NC}
${G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

  URL:   http://localhost
  PIN:   $PIN  (auto-login уже в ссылке)

  ${Y}Что показать:${NC}

  ${B}/${NC}          — дашборд: утренний бриф + метрики (HRV, RHR, сон, шаги)
                + открытые задачи
  ${B}/reports${NC}   — 3 отчёта (monthly + 2 weekly) с SOAP-нотами 9 специалистов,
                GP-синтезом, problem list, safety net, PubMed-ссылками,
                кнопкой «Скачать PDF»
  ${B}/chat${NC}      — 2 готовых диалога с GP в истории (HRV-вопрос и липиды);
                можно задать новый вопрос — потребует LLM-ключ
  ${B}/tasks${NC}     — 6 открытых задач (от GP, коучей), 3 закрытых
  ${B}/medications${NC} — 3 препарата (2 активных + 1 прекращённый)
  ${B}/documents${NC} — 2 обработанных документа (лаб-панель, консультация)

  ${Y}Если захочешь живую генерацию:${NC}
    добавь ANTHROPIC_API_KEY или CLAUDE_CODE_OAUTH_TOKEN в .env
    docker compose restart api
    → кнопки «Сгенерировать» и стриминг-чат оживут

  Остановить:  docker compose down
  Перезасеять: docker compose exec api python -m src.seed

EOF
