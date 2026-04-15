# Архитектура health-mdt

```
                ┌────────────────────────────────────────────┐
                │                 USER ENTRY                 │
                │  Web UI (/)   Telegram bot   QR-код / PIN  │
                └───────────────────┬────────────────────────┘
                                    │
                              Caddy (HTTPS)
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
          ┌──▼──┐               ┌───▼───┐              ┌───▼──┐
          │ Web │               │  API  │              │ Bot  │
          │Next │──/api────────▶│FastAPI│              │ PTB  │
          └─────┘               └──┬─┬──┘              └──┬───┘
                                   │ │                    │
                          scheduler│ │ agents             │
                                   │ │                    │
                     ┌─────────────┘ └──┐                 │
                     ▼                   ▼                 │
                ┌────────┐        ┌────────────┐           │
                │ SQLite │◀───────│ Orchestrator│──────────┘
                └────────┘        └─────┬──────┘
                                        │
              ┌─────────────┬───────────┼───────────┬──────────────┐
              ▼             ▼           ▼           ▼              ▼
          Sleep/Move/Stress/Recovery    Cardiologist  Endocrinologist   ...
          (lifestyle agents)            (MDT specialists)
                                        │
                                        ▼
                                    GP synthesis
                                  (SOAP + problem list
                                  + safety net + plan)
                                        │
                   ┌────────────────────┼────────────────────┐
                   ▼                    ▼                    ▼
             Daily brief          Weekly MDT            Task lifecycle
                                                       (→ Apple Reminders)

          ┌──────────────────────┐         ┌──────────────────────┐
          │   Data ingest        │         │   Evidence           │
          │  • Oura API          │         │  • PubMed API        │
          │  • Apple Health XML  │         │  (cached per query)  │
          │  • Documents (vision)│         └──────────────────────┘
          │  • User check-ins    │
          └──────────────────────┘
```

## Слои

### 1. Ingestion
- **Oura**: поллинг v2 API, идемпотентный upsert в `metric`.
- **Apple Health**: стримовый XML парсер (`lxml.iterparse`), чтобы файлы 200+ MB не
  требовали 2 GB RAM.
- **Документы**: Claude vision извлекает лабораторные панели в структуру (`document.extracted`)
  и пишет значения в `lab_result`.
- **Check-ins**: свободный текст с опциональными mood/energy/sleep_quality.

### 2. Context building (`agents/context.py`)
Для каждого запуска агента собирается контекст-бандл:
- метрики за окно с 30-дневным baseline и delta%;
- лабы с флагом `valid: age_days <= window`;
- чек-ины;
- открытые задачи (чтобы не дублировать);
- заметки о пробелах в данных.

### 3. Agents (`agents/registry.py`)
- 9 **специалистов**: Cardiologist (ESC), Endocrinologist (ADA), Nutritionist (EFSA),
  Psychiatrist (biopsychosocial), Oncologist (ESMO/NCCN), Gastroenterologist (Rome IV/AASLD),
  Hematologist (ASH/WHO), Nephrologist (KDIGO), Pulmonologist (GOLD/GINA/USPSTF).
- 4 **lifestyle** агента (Sleep, Movement, Stress/HRV, Recovery) — ежедневные короткие ноты.
- **GP** — координирующий слой, методология RCGP: SOAP, watchful waiting, safety net.

### 4. Orchestration (`agents/orchestrator.py`)
- **MDT consilium**: lifestyle → specialists (parallel, 9 workers) → PubMed + Semantic Scholar
  (параллельно в своём пуле) → GP synthesis.
- **Daily brief**: lifestyle → GP (4-7 предложений).
- **Streaming chat** (`routes/chat.py`): GP отвечает через `messages.stream()`, SSE
  из sse-starlette, буферинг отключён в Caddy (`flush_interval -1`).
- LLM вызовы кэшируются на уровне system prompt (`cache_control: ephemeral`) —
  стабильная часть промпта (методология + роль) даёт ~90% экономии на повторах.

### 5. Tasks
- Создаются GP (из plan.action), специалистами (через recommendations) или вручную.
- Lifecycle: open → in_progress → done | dismissed.
- Follow-up: scheduler раз в сутки выставляет `last_reminded_at` у задач >7 дней в open.
- Apple Reminders: каждая задача имеет `reminders_url` — `shortcuts://` scheme,
  который на iOS запускает один шорткат «HealthMDT Add».

### 6. Reports
- **Daily brief** — короткий бриф GP, утром 06:30.
- **Weekly MDT** — полный консилиум, воскресенье 08:00.
- **Ad-hoc** — по кнопке в вебе или `/report` в боте.
- **PDF для врача** (`reports/pdf_export.py`) — WeasyPrint рендерит A4 с типографикой
  под печать: пациент → проблем-лист → GP-синтез → safety net → ноты специалистов
  (с SOAP-развёрткой) → PubMed-ссылки → дисклеймер. Никаких emoji/ярких цветов.

### 7. Auth modes
- **PIN** (дефолт): `ACCESS_PIN` в `.env`, in-memory session store, токен в `localStorage`.
  QR deep-link `/#pin=XXXXXX` для мгновенного авто-логина с телефона.
- **OAuth Google** (`AUTH_MODE=oauth`): authlib + starlette SessionMiddleware для OIDC-потока,
  подписанные cookies через itsdangerous (`SESSION_SECRET` персистится в `data/session_secret`),
  allowlist email-ов через `OAUTH_ALLOWED_EMAILS`.
- Все routes унифицированы через `auth_deps.get_current_user()` — user scoping работает
  одинаково в обоих режимах, миграция между ними — без изменения кода роутов.

## Decisions & trade-offs

| Выбор | Альтернатива | Почему |
|---|---|---|
| SQLite + SQLModel | Postgres + Supabase | Zero-config; один volume; достаточно для single-user MVP |
| Python 3.12 + FastAPI | Bun/TypeScript backend | Лучшая экосистема для AI/scientific (lxml, PubMed parsers, Anthropic SDK) |
| Anthropic SDK напрямую | LangGraph / LangChain | Меньше магии; полный контроль над prompt caching и traces |
| PIN-auth | OAuth / email | Single-user MVP — PIN достаточно, деплой за 2 минуты |
| 4 специалиста (не 9) | Полный MDT из поста | MVP-фокус; добавить остальных — одна строка в `registry.py` |
| Caddy | nginx + certbot | Автоматический HTTPS из коробки, одна строка конфига |
| Next.js standalone output | SPA + static hosting | SSR даст быстрый TTI на мобилках, где чаще заходят через QR |
| Prompt caching ephemeral | без кэша | Стабильные system prompts = ~90% экономии токенов на репетитивных запусках |
| Parallel specialists | sequential | LLM вызовы I/O-bound, threads безопасны с Anthropic SDK |

## Расширение

- **Больше специалистов**: добавить в `agents/registry.py`, пополнить `MDT_SPECIALISTS`.
- **Больше источников**: новый модуль в `src/integrations/`, маршрут в `routes/sources.py`,
  форма в `web/src/app/onboarding`.
- **Мульти-пользовательский режим**: поменять PIN-auth на OAuth, `User` уже индексирован.
- **Постгрес**: поменять `DATABASE_URL`, модели SQLModel уже портативны.
- **Streaming responses**: `sse_starlette` подключён — нужен только handler для стриминга
  ответа GP в вебе.
