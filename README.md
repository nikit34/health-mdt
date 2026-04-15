# health-mdt

> Мультиагентный персональный health-ассистент. Разворачивается за 2 минуты,
> работает с Oura, Apple Health, медицинскими документами и чек-инами.
> Команда из 8 LLM-специалистов под координацией GP-агента синтезирует ежедневные
> брифы, еженедельные MDT-отчёты и задачи с полным жизненным циклом.

[English ↓](#english)

---

## Что это

Персональный мультидисциплинарный health-ассистент. Под капотом:

- **8 агентов-специалистов**: Кардиолог, Эндокринолог, Нутрициолог, Психиатр
  (методологии ESC/ADA/EFSA/biopsychosocial) + Sleep/Movement/Stress/Recovery coaches.
- **GP-координатор** (методология RCGP): SOAP-мышление, проблем-лист, watchful waiting,
  safety net, план с action/monitor/review.
- **Доказательная база**: PubMed API — каждый MDT-отчёт содержит PMID с обоснованиями.
- **Данные**: Oura (API), Apple Health (XML-импорт), медицинские документы (PDF/фото →
  Claude vision → структурированные лабы с валидностью).
- **Выходы**: утренний бриф (4-7 предложений, 06:30), еженедельный GP-отчёт (воскресенье),
  задачи с экспортом в Apple Reminders.
- **Каналы**: веб-дашборд (mobile-first), Telegram-бот, QR для быстрого доступа.

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
| MDT consilium + GP synthesis | ✅ | 4 специалиста (легко расширить — одна строка в registry) |
| Lifestyle agents (Sleep/Movement/Stress/Recovery) | ✅ | Ежедневные ноты |
| GP methodology (SOAP + safety net + problem list + watchful waiting) | ✅ | По RCGP |
| Evidence grounding (PubMed API) | ✅ | С кэшем на 14 дней |
| Lab validity windows | ✅ | Старые анализы ≠ текущее состояние |
| Oura integration | ✅ | Sleep, HRV, readiness, activity, stress |
| Apple Health XML import | ✅ | Streaming parser (сотни МБ — без проблем) |
| Medical docs extraction | ✅ | Claude vision → структурированные лабы |
| Daily brief (06:30) | ✅ | 4-7 предложений, автоматически |
| Weekly MDT (Sun 08:00) | ✅ | Автоматически |
| Task lifecycle (open→done/dismissed + follow-up) | ✅ | Stale>7d reminders |
| Apple Reminders export | ✅ | Через iOS Shortcut (см. docs/apple-reminders.md) |
| Telegram bot | ✅ | /brief, /ask, /checkin, /report, /tasks, /done |
| Web UI (dashboard, reports, chat, tasks, documents, settings) | ✅ | Mobile-first, dark theme |
| PIN auth + QR deep-link | ✅ | URL вида `/#pin=123456` авто-логин |
| One-click deploy (Docker + Caddy) | ✅ | `./scripts/deploy.sh domain` |
| Prompt caching | ✅ | Стабильные system prompts → ~90% экономии |

## Что бы доделал дальше

- Стриминг GP-ответов в чате (SSE каркас подключён — нужен handler).
- Больше специалистов из поста (Онколог, Гастро, Гематолог, Нефролог, Пульмонолог) —
  добавление одной строки в `api/src/agents/registry.py`.
- Google Scholar grounding (кроме PubMed) для клинических гайдлайнов.
- Трекинг доз лекарств и reminders по ним.
- Мульти-пользовательский режим (OAuth, schema уже поддерживает).
- Постгрес-бэкенд для high-scale (SQLModel уже портативен — поменять `DATABASE_URL`).
- Экспорт отчётов в PDF для похода к живому врачу.

## Стек

- **Backend**: Python 3.12, FastAPI, SQLModel (SQLite), APScheduler, anthropic SDK.
- **LLM**: Claude Sonnet 4.6 (агенты), опционально Opus 4.6 для месячной синтеза.
- **Frontend**: Next.js 14, TypeScript, Tailwind.
- **Bot**: python-telegram-bot.
- **Deploy**: Docker Compose + Caddy (автоматический HTTPS).
- **Data**: lxml (streaming Apple Health), pypdf, httpx.

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
