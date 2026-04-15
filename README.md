# health-mdt

> Мультиагентный персональный health-ассистент. Разворачивается за 2 минуты,
> работает с Oura, Apple Health, медицинскими документами и чек-инами.
> Команда из 8 LLM-специалистов под координацией GP-агента синтезирует ежедневные
> брифы, еженедельные MDT-отчёты и задачи с полным жизненным циклом.

[English ↓](#english)

---

## Что это

Персональный мультидисциплинарный health-ассистент. Под капотом:

- **13 LLM-агентов**: 9 MDT-специалистов (Кардиолог, Эндокринолог, Нутрициолог, Психиатр,
  Онколог, Гастроэнтеролог, Гематолог, Нефролог, Пульмонолог — методологии ESC/ADA/ESMO/
  KDIGO/GOLD/и др.) + 4 lifestyle-коуча (Sleep/Movement/Stress/Recovery).
- **GP-координатор** (методология RCGP): SOAP-мышление, проблем-лист, watchful waiting,
  safety net, план с action/monitor/review.
- **Доказательная база**: PubMed API + Semantic Scholar (параллельно) — каждый MDT-отчёт
  содержит ссылки с обоснованиями.
- **Данные**: Oura (API), Apple Health (XML-импорт), медицинские документы (PDF/фото →
  Claude vision → структурированные лабы с валидностью).
- **Выходы**: утренний бриф (4-7 предложений, 06:30), еженедельный GP-отчёт (воскресенье),
  задачи с экспортом в Apple Reminders, **PDF-отчёт «для врача»**.
- **Каналы**: веб-дашборд (mobile-first) со **стриминг-чатом** как в ChatGPT,
  Telegram-бот, QR для быстрого доступа.
- **Auth**: PIN (single-user) или Google OAuth (multi-user) — переключается одной env-переменной.

## Запуск за 2 минуты

Требуется: **Docker** + **git**.

```bash
git clone https://github.com/nikit34/health-mdt.git
cd health-mdt
./scripts/deploy.sh
```

Скрипт:
1. Спросит `ANTHROPIC_API_KEY` (получить на [console.anthropic.com](https://console.anthropic.com)).
2. Сгенерирует 6-значный PIN и сохранит в `.env`.
3. Соберёт контейнеры (`api`, `web`, `bot`, `caddy`), стартанёт стек.
4. Распечатает URL (`http://localhost`), PIN и ASCII-QR для мобильного.

Открой URL, введи PIN, пройди онбординг (профиль + источники данных) — готово.

### Деплой на VPS

```bash
./scripts/deploy.sh health.example.com
```

Caddy автоматически выдаст HTTPS-сертификат через Let's Encrypt. DNS должен
указывать на сервер (A/AAAA запись).

### Посмотреть без реальных данных

После старта:

```bash
docker compose exec api python -m src.seed
```

Засеет 30 дней метрик, липидный профиль (LDL повышен), vit D низкий, HbA1c на границе.
Сразу можно нажать «Сгенерировать бриф» и «Собрать консилиум» в UI.

## Архитектура

```
 Web / Bot / QR
      │
   Caddy (HTTPS)
      │
 ┌────┼─────┐
 │    │     │
Web  API   Bot
  ╲   │   ╱
   SQLite
      │
   Orchestrator  ──▶  PubMed (cached)
      │
 ┌────┼────────────┐
 │    │            │
Lifestyle    MDT specialists
(4 agents)   (4 agents)
      ╲     ╱
       GP (synthesis)
      ╱        ╲
  Brief     Weekly MDT
              ╲
            Tasks → Apple Reminders
```

Подробности: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Что реализовано

| Модуль | Статус | Примечание |
|---|---|---|
| MDT consilium + GP synthesis | ✅ | 9 специалистов (одна строка — добавить ещё) |
| Lifestyle agents (Sleep/Movement/Stress/Recovery) | ✅ | Ежедневные ноты |
| GP methodology (SOAP + safety net + problem list + watchful waiting) | ✅ | По RCGP |
| Evidence: PubMed + Semantic Scholar | ✅ | Параллельный fetch, кэш 14 дней |
| Lab validity windows | ✅ | Старые анализы ≠ текущее состояние |
| Oura integration | ✅ | Sleep, HRV, readiness, activity, stress |
| Apple Health XML import | ✅ | Streaming parser (сотни МБ — без проблем) |
| Medical docs extraction | ✅ | Claude vision → структурированные лабы |
| Daily brief (06:30) | ✅ | 4-7 предложений, автоматически |
| Weekly MDT (Sun 08:00) | ✅ | Автоматически |
| **Streaming chat (SSE)** | ✅ | GP отвечает токен-за-токеном как в ChatGPT |
| **PDF-экспорт MDT для живого врача** | ✅ | WeasyPrint шаблон, print-friendly |
| Task lifecycle (open→done/dismissed + follow-up) | ✅ | Stale>7d reminders |
| Apple Reminders export | ✅ | Через iOS Shortcut (см. docs/apple-reminders.md) |
| Telegram bot | ✅ | /brief, /ask, /checkin, /report, /tasks, /done |
| Web UI (dashboard, reports, chat, tasks, documents, settings) | ✅ | Mobile-first, dark theme |
| **PIN auth или Google OAuth (multi-user)** | ✅ | Переключается AUTH_MODE |
| **Allowlist email-ов для OAuth** | ✅ | OAUTH_ALLOWED_EMAILS=... |
| QR deep-link | ✅ | URL вида `/#pin=123456` авто-логин |
| One-click deploy (Docker + Caddy) | ✅ | `./scripts/deploy.sh domain` |
| Prompt caching | ✅ | Стабильные system prompts → ~90% экономии |

## Режимы авторизации

**PIN (single-user)** — дефолт. Подходит, когда инстанс развёрнут для одного владельца.
Генерируется при первом запуске `./scripts/deploy.sh`.

**Google OAuth (multi-user)** — для случая «развернул на своём хосте, даю доступ команде
или семье». В `.env`:
```bash
AUTH_MODE=oauth
OAUTH_GOOGLE_CLIENT_ID=...
OAUTH_GOOGLE_CLIENT_SECRET=...
OAUTH_ALLOWED_EMAILS=you@example.com,wife@example.com  # опц, без — любой Google-аккаунт
```
Credentials создаются на [console.cloud.google.com](https://console.cloud.google.com):
- Application type: Web application
- Authorized redirect URI: `https://<твой-домен>/api/auth/oauth/google/callback`

Каждый user получает свою строку в БД, свои метрики/лабы/отчёты.
Схема уже скопирована из коробки на multi-tenant (per-user foreign keys везде).

## Что бы доделал дальше

- Per-user Telegram pairing UI flow (сейчас в multi-user режиме чат привяжется к
  единственному юзеру или будет отказ).
- Трекинг доз лекарств и reminders по ним.
- Постгрес-бэкенд для high-scale (SQLModel уже портативен — поменять `DATABASE_URL`).
- Web Push для утренних брифов (сейчас через Telegram или email — TODO email).
- Больше специалистов (добавить в `registry.py`).

## Стек

- **Backend**: Python 3.12, FastAPI, SQLModel (SQLite), APScheduler, anthropic SDK,
  authlib (OAuth), sse-starlette (streaming), weasyprint (PDF).
- **LLM**: Claude Sonnet 4.6 (агенты), опционально Opus 4.6 для месячного синтеза.
- **Frontend**: Next.js 14, TypeScript, Tailwind — dark theme, mobile-first.
- **Bot**: python-telegram-bot.
- **Deploy**: Docker Compose + Caddy (автоматический HTTPS через Let's Encrypt).
- **Data**: lxml (streaming Apple Health), pypdf, httpx.
- **Evidence**: PubMed E-utilities + Semantic Scholar (параллельно, кэш 14 дней).

## Безопасность и данные

- Всё хранится **локально** в `./data/health.db` (SQLite). Ни один запрос с медицинскими
  данными не уходит никому, кроме API Anthropic (для агентов), PubMed (для evidence) и
  Oura (для пулла твоих же данных).
- `.env` не коммитится. `data/`, `uploads/` в `.gitignore`.
- PIN-авторизация (PIN генерируется при деплое, сессии TTL 30 дней).

**Важно**: health-mdt — не медицинский прибор и не заменяет врача. Это инструмент для
информированного самонаблюдения. Агенты обучены не ставить диагнозов и давать
safety-net триггеры для обращения к живому специалисту.

## Лицензия

MIT. См. [LICENSE](LICENSE).

---

<a name="english"></a>
## English

**health-mdt** is a multi-agent personal health assistant. 8 LLM specialists + a GP
coordinator agent produce daily briefs, weekly MDT reports grounded in PubMed evidence,
and tasks exported to Apple Reminders. Reads from Oura, Apple Health XML, medical
documents (via Claude vision) and free-text check-ins.

Deploy in 2 minutes on any host with Docker:

```bash
git clone https://github.com/nikit34/health-mdt.git
cd health-mdt
./scripts/deploy.sh                    # local
./scripts/deploy.sh health.example.com # VPS with auto-HTTPS
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design details.

**Disclaimer**: Informational tool only. Not a medical device. Consult a physician for
medical decisions.
