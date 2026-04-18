"""Seed a demo user with fully populated content — no LLM calls required.

Populates everything the UI renders so you can show the product without:
  - An Anthropic API key
  - A real Oura device
  - A real Apple Health export
  - Real medical documents

Run via docker compose:
    docker compose exec api python -m src.seed

Or directly:
    python -m src.seed

Idempotent: clears prior demo data first.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from .db import (
    Brief,
    ChatMessage,
    Checkin,
    Conversation,
    Document,
    LabResult,
    Medication,
    MdtReport,
    Metric,
    PubmedEvidence,
    Task,
    User,
)
from .db.session import engine, init_db


def seed() -> None:
    init_db()
    random.seed(42)

    with Session(engine) as s:
        # Clear prior demo data (but keep tables)
        for model in (
            ChatMessage, Conversation, Task, Brief, MdtReport, PubmedEvidence,
            Document, LabResult, Medication, Metric, Checkin,
        ):
            s.execute(delete(model))
        s.commit()

        user = s.exec(select(User)).first()
        if not user:
            user = User(
                name="Демо Пациент",
                birthdate=date(1988, 5, 12),
                sex="M",
                height_cm=180,
                weight_kg=78,
                context=(
                    "Бросил курить 6 мес назад (21 pack-year в анамнезе). "
                    "Родитель с ишемической болезнью сердца в 58 лет. "
                    "Цель — держать LDL <2.5, сон >7ч, активность минимум 8k шагов, "
                    "vitamin D в референсе."
                ),
            )
            s.add(user)
            s.commit()
            s.refresh(user)
        else:
            # Refresh context in case it was empty
            user.name = user.name or "Демо Пациент"
            user.context = user.context or (
                "Бросил курить 6 мес назад. Родитель с ИБС. "
                "Цель — LDL <2.5, сон >7ч, 8k+ шагов."
            )
            s.add(user)
            s.commit()

        _seed_metrics(s, user)
        _seed_labs_with_trends(s, user)
        _seed_checkins(s, user)
        _seed_medications(s, user)
        _seed_documents(s, user)
        _seed_pubmed(s)
        reports = _seed_mdt_reports(s, user)
        _seed_briefs(s, user)
        _seed_tasks(s, user, reports)
        _seed_conversations(s, user)

        s.commit()
        _print_summary(s, user)


# --- Metrics: 45 days of Oura-style data ---

def _seed_metrics(s: Session, user: User) -> None:
    now = datetime.utcnow()
    for i in range(45, -1, -1):
        ts = now - timedelta(days=i)
        weekend = ts.weekday() >= 5
        # Downward trend in HRV and upward in RHR over the last week — creates signal
        stress_bump = max(0, (7 - i)) / 7 if i < 7 else 0
        hrv = 45 + random.gauss(0, 4) - 7 * stress_bump
        rhr = 56 + random.gauss(0, 2) + 4 * stress_bump
        sleep = 3600 * (7.2 + random.gauss(0, 0.6) + (0.3 if weekend else 0) - 0.5 * stress_bump)
        steps = int(8500 + random.gauss(0, 2000) + (-1500 if weekend else 0))
        readiness = max(45, min(95, int(78 + random.gauss(0, 7) - 8 * stress_bump)))
        activity = max(35, min(98, int(72 + random.gauss(0, 10))))
        sleep_score = max(40, min(98, int(76 + random.gauss(0, 6) - 6 * stress_bump)))

        kinds = [
            ("hrv_rmssd_night", max(15, hrv), "ms"),
            ("resting_hr", min(90, rhr), "bpm"),
            ("sleep_duration", max(3600, sleep), "seconds"),
            ("sleep_score", sleep_score, "score"),
            ("steps", max(500, steps), "count"),
            ("readiness_score", readiness, "score"),
            ("activity_score", activity, "score"),
            ("active_calories", max(50, 380 + random.gauss(0, 120)), "kcal"),
            ("respiratory_rate_night", 14.5 + random.gauss(0, 0.5), "bpm"),
        ]
        for kind, val, unit in kinds:
            s.add(Metric(
                user_id=user.id, ts=ts, source="oura", kind=kind,
                value=float(val), unit=unit, meta={"seeded": True},
            ))


# --- Labs: 3 draws over last year → show trends ---

def _seed_labs_with_trends(s: Session, user: User) -> None:
    # 3 draws: 12m ago, 6m ago, 1m ago
    draws = [
        date.today() - timedelta(days=365),
        date.today() - timedelta(days=180),
        date.today() - timedelta(days=30),
    ]

    # HbA1c trending up (5.4 → 5.7 → 5.9 — approaching prediabetic)
    for d, val in zip(draws, [5.4, 5.7, 5.9]):
        flag = "H" if val > 5.6 else None
        s.add(LabResult(
            user_id=user.id, drawn_at=d, panel="hba1c",
            analyte="hba1c", value=val, unit="%",
            ref_low=4.0, ref_high=5.6, flag=flag,
        ))

    # LDL rising (2.8 → 3.2 → 3.6 — family history makes this notable)
    for d, val in zip(draws, [2.8, 3.2, 3.6]):
        s.add(LabResult(
            user_id=user.id, drawn_at=d, panel="lipids",
            analyte="ldl_cholesterol", value=val, unit="mmol/L",
            ref_low=0.0, ref_high=3.0, flag="H" if val > 3.0 else None,
        ))

    # Vitamin D — still low after 6m of supplementation (22 → 28 → 31)
    for d, val in zip(draws, [22, 28, 31]):
        flag = "L" if val < 30 else None
        s.add(LabResult(
            user_id=user.id, drawn_at=d, panel="vitamin_d",
            analyte="vitamin_d", value=val, unit="ng/mL",
            ref_low=30, ref_high=100, flag=flag,
        ))

    # Latest draw — full panel
    latest = draws[-1]
    extras = [
        # Lipids — extra analytes
        ("total_cholesterol", 5.6, "mmol/L", 3.0, 5.2, "H", "lipids"),
        ("hdl_cholesterol", 1.15, "mmol/L", 1.0, 1.5, None, "lipids"),
        ("triglycerides", 1.8, "mmol/L", 0.0, 1.7, "H", "lipids"),
        # CBC
        ("hemoglobin", 15.1, "g/dL", 13.0, 17.0, None, "cbc"),
        ("hematocrit", 45, "%", 40, 52, None, "cbc"),
        ("mcv", 88, "fL", 80, 100, None, "cbc"),
        ("platelets", 260, "10^9/L", 150, 400, None, "cbc"),
        ("ferritin", 68, "ng/mL", 30, 400, None, "cbc"),
        # CMP
        ("glucose_fasting", 5.6, "mmol/L", 3.9, 5.5, "H", "cmp"),
        ("creatinine", 87, "umol/L", 62, 106, None, "cmp"),
        ("egfr", 96, "mL/min/1.73m2", 90, 200, None, "cmp"),
        ("alt", 32, "U/L", 0, 40, None, "cmp"),
        ("ast", 26, "U/L", 0, 40, None, "cmp"),
        # Thyroid
        ("tsh", 2.1, "mIU/L", 0.4, 4.0, None, "thyroid"),
        ("free_t4", 15.2, "pmol/L", 9.0, 19.0, None, "thyroid"),
        # B12/folate
        ("b12", 380, "pmol/L", 150, 700, None, "b12"),
    ]
    for analyte, value, unit, lo, hi, flag, panel in extras:
        s.add(LabResult(
            user_id=user.id, drawn_at=latest, panel=panel,
            analyte=analyte, value=value, unit=unit,
            ref_low=lo, ref_high=hi, flag=flag,
        ))


# --- Check-ins ---

def _seed_checkins(s: Session, user: User) -> None:
    now = datetime.utcnow()
    entries = [
        (0, "Проснулся уставшим. 2 чашки кофе с утра.", 3, 2, 3),
        (1, "Хорошо потренировался, чувствую себя бодрее.", 4, 4, 4),
        (2, "Поздно лёг. Стресс на работе.", 2, 2, 2),
        (3, "Болит голова к концу дня — второй раз на этой неделе.", 3, 3, 3),
        (4, "Ел нормально, больше овощей сегодня.", 4, 3, 4),
        (6, "Бросил кофе после обеда — спал лучше.", 4, 4, 5),
        (9, "Выходные, выспался. Длинная прогулка.", 5, 5, 5),
        (12, "Поехал к родителям, сидячее воскресенье.", 3, 3, 4),
        (15, "Сильный стресс из-за дедлайна. Мало спал.", 2, 2, 2),
        (20, "Холодная погода, ленюсь выходить на улицу.", 3, 3, 3),
    ]
    for days_ago, text, mood, energy, sleep_q in entries:
        s.add(Checkin(
            user_id=user.id,
            ts=now - timedelta(days=days_ago, hours=random.randint(6, 22)),
            text=text, mood=mood, energy=energy, sleep_quality=sleep_q, tags=[],
        ))


# --- Medications ---

def _seed_medications(s: Session, user: User) -> None:
    meds = [
        Medication(
            user_id=user.id, name="Vitamin D3",
            dose="4000 IU", frequency="ежедневно утром",
            started_on=date.today() - timedelta(days=180),
            notes="После обнаружения дефицита (22 ng/mL в прошлом году).",
            reminder_time="08:00",
        ),
        Medication(
            user_id=user.id, name="Omega-3 (EPA/DHA)",
            dose="1000 mg", frequency="ежедневно с едой",
            started_on=date.today() - timedelta(days=90),
            notes="Профилактика СС-риска с учётом семейного анамнеза.",
            reminder_time="13:00",
        ),
        Medication(
            user_id=user.id, name="Magnesium glycinate",
            dose="400 mg", frequency="на ночь",
            started_on=date.today() - timedelta(days=45),
            stopped_on=date.today() - timedelta(days=10),
            notes="Пробовал для сна — без заметного эффекта, прекратил.",
        ),
    ]
    for m in meds:
        s.add(m)


# --- Documents ---

def _seed_documents(s: Session, user: User) -> None:
    docs = [
        Document(
            user_id=user.id,
            uploaded_at=datetime.utcnow() - timedelta(days=30),
            filename="lab_2026_03_18.pdf",
            path="/uploads/demo/lab_2026_03_18.pdf",
            mime="application/pdf",
            status="processed",
            summary="Лабораторная панель, клиника «Медицина++», 18.03.2026. "
                    "Липиды, CBC, CMP, HbA1c, тиреоид, B12, vitamin D.",
            extracted={
                "date": "2026-03-18",
                "clinic": "Медицина++",
                "panels": ["lipids", "cbc", "cmp", "hba1c", "thyroid", "b12", "vitamin_d"],
                "highlights": [
                    "HbA1c 5.9% (граница преддиабета)",
                    "LDL 3.6 mmol/L (повышен)",
                    "Vitamin D 31 ng/mL (нижняя граница референса)",
                ],
            },
        ),
        Document(
            user_id=user.id,
            uploaded_at=datetime.utcnow() - timedelta(days=60),
            filename="cardiology_consult_2026_02.pdf",
            path="/uploads/demo/cardiology_consult_2026_02.pdf",
            mime="application/pdf",
            status="processed",
            summary="Консультация кардиолога — ЭКГ, ЭхоКГ в норме. "
                    "Рекомендован контроль LDL, повторная консультация через 6 мес.",
            extracted={
                "date": "2026-02-14",
                "specialist": "Кардиолог",
                "findings": ["ЭКГ без особенностей", "ЭхоКГ: ФВ 62%"],
                "recommendations": [
                    "Контроль липидного профиля через 3 мес",
                    "Оценить 10-летний СС-риск по SCORE2",
                ],
            },
        ),
    ]
    for d in docs:
        s.add(d)


# --- PubMed evidence (cached entries) ---

def _seed_pubmed(s: Session) -> None:
    records = [
        ("lifestyle intervention HbA1c prediabetes",
         "38291847", "Lifestyle interventions for adults with prediabetes: a systematic review",
         "Lancet Diabetes Endocrinol", 2024, ["Chen L", "Ramirez S", "Patel A"]),
        ("LDL target primary prevention family history",
         "37892541", "LDL-C targets in primary prevention: 2024 ESC guideline update",
         "Eur Heart J", 2024, ["Schmidt K", "O'Brien P", "Ivanova M"]),
        ("vitamin D supplementation efficacy serum level",
         "36721094", "Oral vitamin D3 supplementation response: dose-finding meta-analysis",
         "J Clin Endocrinol Metab", 2023, ["Larsson H", "Wong E"]),
        ("HRV decline resting heart rate rise illness",
         "37445218", "Continuous HRV monitoring as early illness signal in athletes",
         "Physiol Meas", 2024, ["Dubois F", "Akiyama R"]),
        ("smoking cessation cardiovascular risk recovery",
         "36912087", "Cardiovascular risk trajectory after smoking cessation: 10-year cohort",
         "JAMA Cardiol", 2023, ["Ng T", "Hoffmann K", "Kumar S"]),
    ]
    for query, pmid, title, journal, year, authors in records:
        s.add(PubmedEvidence(
            query=query, pmid=pmid, title=title, journal=journal, pub_year=year,
            authors=authors, abstract="(demo abstract — сокращено)",
        ))


# --- MDT reports ---

def _seed_mdt_reports(s: Session, user: User) -> list[MdtReport]:
    reports: list[MdtReport] = []

    # Monthly (1 month ago)
    monthly = MdtReport(
        user_id=user.id,
        created_at=datetime.utcnow() - timedelta(days=33),
        kind="monthly",
        specialist_notes=_sample_specialist_notes(window="monthly"),
        gp_synthesis=(
            "За прошедший месяц картина стабильна: сон и активность в норме личной базы, "
            "но есть два медленных тренда, которые требуют внимания. Первый — HbA1c сдвинулся "
            "с 5.7% до 5.9%, это всё ещё пограничный преддиабет, но направление движения не "
            "нравится с учётом семейной истории. Второй — LDL продолжает ползти вверх (3.2 → 3.6), "
            "что в комбинации с отцовской ИБС в 58 делает разговор с кардиологом не «когда-нибудь», "
            "а «в ближайшие 4-6 недель».\n\n"
            "Что работает: полгода без сигарет держатся, HRV восстанавливается к норме по "
            "сравнению с прошлогодними показателями. Физическая активность стабильна 8-10k шагов.\n\n"
            "Что менять: (1) консультация кардиолога с SCORE2-расчётом и обсуждением тактики по LDL, "
            "(2) диетическая переоценка — сдвиг в сторону Mediterranean с ограничением быстрых углеводов, "
            "(3) добавить 2 силовые тренировки в неделю для инсулин-чувствительности.\n\n"
            "Витамин D поднялся до 31 на фоне 4000 IU/день — держим дозу, повтор через 3 мес."
        ),
        problem_list=[
            {"problem": "Повышенный LDL-C при семейной истории ИБС", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(),
             "note": "Тренд 12м: 2.8 → 3.2 → 3.6 mmol/L"},
            {"problem": "HbA1c на границе преддиабета", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(),
             "note": "5.4 → 5.7 → 5.9% за 12 мес"},
            {"problem": "Vitamin D дефицит (в ремиссии на supplementation)", "status": "watchful",
             "since": (date.today() - timedelta(days=365)).isoformat(),
             "note": "22 → 28 → 31 ng/mL на 4000 IU"},
            {"problem": "Post-smoking cessation recovery", "status": "watchful",
             "since": (date.today() - timedelta(days=180)).isoformat(),
             "note": "Бросил 6 мес назад, контроль СС-профиля в течение 2-5 лет"},
        ],
        safety_net=[
            "Немедленно к врачу: любая боль в груди, одышка в покое, перебои сердца",
            "В течение 2 недель к кардиологу: SCORE2 + обсуждение LDL-терапии",
            "Если HbA1c на следующем замере ≥6.0 — к эндокринологу в течение месяца",
        ],
        evidence_pmids=["38291847", "37892541", "36912087"],
    )
    s.add(monthly)
    reports.append(monthly)

    # Weekly, 2 weeks ago
    weekly_prev = MdtReport(
        user_id=user.id,
        created_at=datetime.utcnow() - timedelta(days=14),
        kind="weekly",
        specialist_notes=_sample_specialist_notes(window="weekly_prev"),
        gp_synthesis=(
            "Неделя ровная. HRV и readiness в норме личной базы, сон стабильный 7.2ч. "
            "В чек-инах — пара упоминаний о стрессе на работе, но без объективных маркеров "
            "перегрузки. Никаких новых триггеров. Продолжаем план прошлого месяца: визит "
            "к кардиологу, пересмотр диеты, силовые 2x/нед."
        ),
        problem_list=[
            {"problem": "Повышенный LDL-C при семейной истории ИБС", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(),
             "note": "Ждём визит к кардиологу"},
            {"problem": "HbA1c на границе преддиабета", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(), "note": ""},
        ],
        safety_net=[
            "Если боль в груди — немедленно",
            "Головная боль + повышение АД 2+ дня — к терапевту",
        ],
        evidence_pmids=["37892541"],
    )
    s.add(weekly_prev)
    reports.append(weekly_prev)

    # Weekly, current (last Sunday)
    days_since_sunday = datetime.utcnow().weekday()  # Mon=0..Sun=6
    last_sunday = datetime.utcnow() - timedelta(days=(days_since_sunday + 1) % 7)
    weekly_curr = MdtReport(
        user_id=user.id,
        created_at=last_sunday.replace(hour=8, minute=3),
        kind="weekly",
        specialist_notes=_sample_specialist_notes(window="weekly_curr"),
        gp_synthesis=(
            "На этой неделе есть сигнал, на который стоит обратить внимание. HRV упал на 15% "
            "относительно 30-дневной нормы в течение последних 4 ночей, параллельно resting HR "
            "поднялся на 4 удара — это типичный паттерн нагрузки/лёгкой инфекции/недосыпа. "
            "В чек-инах пациент сам отмечает усталость и головную боль. Лабораторных данных, "
            "указывающих на что-то острое, нет — последние анализы месячной давности, липиды и "
            "метаболика стабильны в своём (повышенном) тренде.\n\n"
            "План: если паттерн HRV/RHR не восстановится за 48ч, стоит рассмотреть проверку "
            "базовых маркеров (CBC + CRP). Иначе — усиленный recovery-протокол: сдвиг отбоя "
            "на 30 мин раньше, отмена интенсивных тренировок 3 дня, заменить zone-2 прогулками."
        ),
        problem_list=[
            {"problem": "Повышенный LDL-C при семейной истории ИБС", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(),
             "note": "Визит к кардиологу назначен (см. Tasks)"},
            {"problem": "HbA1c на границе преддиабета", "status": "active",
             "since": (date.today() - timedelta(days=180)).isoformat(), "note": ""},
            {"problem": "Паттерн снижения HRV + рост RHR (≥4 дня)", "status": "watchful",
             "since": (date.today() - timedelta(days=4)).isoformat(),
             "note": "Если не восстановится за 48ч — CBC+CRP"},
        ],
        safety_net=[
            "Боль в груди, одышка в покое — немедленно",
            "HRV низкая + новые симптомы (температура, кашель) — CBC+CRP в течение 72ч",
            "Если RHR >75 устойчиво неделю — повторная консультация",
        ],
        evidence_pmids=["37445218", "37892541"],
    )
    s.add(weekly_curr)
    reports.append(weekly_curr)

    s.commit()
    for r in reports:
        s.refresh(r)
    return reports


def _sample_specialist_notes(*, window: str) -> dict:
    """Canned specialist notes — realistic but static. window controls what's active."""
    base = {
        "cardiologist": {
            "role": "Кардиолог",
            "soap": {
                "subjective": "Пациент отмечает эпизодическую усталость, головную боль.",
                "objective": "RHR 58 bpm (рост +4 к 30д базе), HRV 38ms (падение 15%).",
                "assessment": "LDL 3.6 mmol/L — выше целевого для умеренного риска, "
                              "семейная история ИБС → реклассификация в повышенный риск.",
                "plan": "SCORE2 расчёт + консультация очно в течение 2 недель. "
                        "Мониторинг RHR/HRV — если не нормализуется за 48ч, CBC+CRP.",
            },
            "narrative": "LDL тренд растущий на фоне семейной истории — основное беспокойство. "
                         "RHR-паттерн этой недели скорее нагрузка/недосып, чем кардиальный.",
            "recommendations": [
                {"title": "Визит к кардиологу — SCORE2 + обсуждение LDL",
                 "detail": "Взять с собой последние 3 липидограммы для динамики.",
                 "priority": "normal", "due_days": 14},
            ],
            "safety_flags": [],
            "evidence_pmids": ["37892541"],
            "confidence": 0.82,
        },
        "endocrinologist": {
            "role": "Эндокринолог",
            "soap": {
                "subjective": "Без специфических жалоб. Упоминания усталости не эндокринные.",
                "objective": "HbA1c 5.9%, glucose fasting 5.6 mmol/L, TSH 2.1 — норма.",
                "assessment": "Преддиабетическое состояние с явным восходящим трендом. "
                              "Vitamin D 31 — нижняя граница на фоне supplementation.",
                "plan": "Повтор HbA1c через 3 мес. Если ≥6.0 — очный визит.",
            },
            "narrative": "Тренд HbA1c за 12 мес (5.4→5.7→5.9) требует внимания. "
                         "Диета и силовые нагрузки — первая линия до медикаментов.",
            "recommendations": [
                {"title": "Пересмотр рациона — Mediterranean + ограничение быстрых углеводов",
                 "detail": "2-недельный трек: записывать еду, потом обсудить с нутрициологом.",
                 "priority": "normal", "due_days": 14},
            ],
            "safety_flags": [],
            "evidence_pmids": ["38291847"],
            "confidence": 0.85,
        },
        "nutritionist": {
            "role": "Нутрициолог",
            "soap": {
                "subjective": "Чек-ины: \"ем нормально, больше овощей\", 2 кофе в день.",
                "objective": "Вес 78 кг стабилен. Данных о конкретных продуктах нет.",
                "assessment": "Без food-logs сложно оценить. Показано начать 2-недельный лог.",
                "plan": "2-недельный пищевой дневник, потом оценка по Mediterranean-индексу.",
            },
            "narrative": "Пока недостаточно данных для детальных рекомендаций. "
                         "Начать с фиксации — без этого любой совет вслепую.",
            "recommendations": [
                {"title": "Вести food-лог 14 дней", "detail": "Любое приложение или заметки.",
                 "priority": "low", "due_days": 1},
            ],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.65,
        },
        "psychiatrist": {
            "role": "Психиатр / Психолог",
            "soap": {
                "subjective": "Упоминания стресса на работе, пропуски тренировок из-за усталости.",
                "objective": "Mood в чек-инах 3/5, energy 3/5 — умеренное снижение 2+ недели.",
                "assessment": "Лёгкий стресс-паттерн без признаков клинической депрессии/тревоги.",
                "plan": "Восстановительные практики, проверить через неделю.",
            },
            "narrative": "Ничего критического. Общая тенденция связана со сном, а не с "
                         "первичным психо-профилем.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.75,
        },
        "oncologist": {
            "role": "Онколог",
            "soap": {
                "subjective": "Нет red flags (потеря веса, ночные поты, узлы).",
                "objective": "21 pack-year + 6 мес с прекращения → в зоне low-dose CT screening "
                             "по USPSTF если возраст будет 50+.",
                "assessment": "Сейчас 37 лет — LDCT не показан до 50. Держать на радаре.",
                "plan": "Возрастной скрининг: колоректальный с 45, LDCT с 50 при сохранении "
                        "статуса former smoker <15 лет.",
            },
            "narrative": "Онко-риск текущий низкий, но курение в анамнезе — фактор для будущих скринингов.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.80,
        },
        "gastroenterologist": {
            "role": "Гастроэнтеролог",
            "soap": {
                "subjective": "Без ЖКТ-жалоб.",
                "objective": "ALT 32, AST 26 — норма. Алкоголь в чек-инах не упоминается.",
                "assessment": "ЖКТ-профиль без особенностей.",
                "plan": "Плановый контроль в рамках общих анализов.",
            },
            "narrative": "Без вопросов — печёночные в норме.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.88,
        },
        "hematologist": {
            "role": "Гематолог",
            "soap": {
                "subjective": "Без жалоб на кровотечения/синяки.",
                "objective": "HGB 15.1, MCV 88, ферритин 68, B12 380 — всё в норме.",
                "assessment": "Гематологический профиль спокойный.",
                "plan": "Контроль в плановые анализы.",
            },
            "narrative": "Всё ок. MCV нормоцитарный, запасы железа достаточные.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.90,
        },
        "nephrologist": {
            "role": "Нефролог",
            "soap": {
                "subjective": "Без жалоб.",
                "objective": "Креатинин 87, eGFR 96 — стадия G1.",
                "assessment": "Почечная функция сохранена.",
                "plan": "Плановый контроль 1x/год при отсутствии рисков.",
            },
            "narrative": "Почки в порядке.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.90,
        },
        "pulmonologist": {
            "role": "Пульмонолог",
            "soap": {
                "subjective": "Без одышки/кашля. 6 мес от прекращения курения.",
                "objective": "SpO2 средняя 97%, respiratory rate 14.5 ночной — норма.",
                "assessment": "Post-cessation recovery идёт ожидаемо.",
                "plan": "LDCT-скрининг не показан (возраст <50). Повтор оценки по мере приближения.",
            },
            "narrative": "Лёгкие восстанавливаются. Риск снижается экспоненциально с месяцами "
                         "воздержания — продолжать не курить.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": ["36912087"],
            "confidence": 0.80,
        },
        # Lifestyle agents
        "sleep": {
            "role": "Sleep-coach",
            "soap": {},
            "narrative": "Сон 7.2ч средний, эффективность 88%. За последнюю неделю задержка "
                         "засыпания выросла до 24 мин (с обычных 12).",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.80,
        },
        "movement": {
            "role": "Movement-coach",
            "soap": {},
            "narrative": "Активность стабильна 8.5k шагов/день. Силовых тренировок мало — "
                         "2 за 2 недели, при цели 2-3/нед.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.75,
        },
        "stress_hrv": {
            "role": "Stress/HRV coach",
            "soap": {},
            "narrative": "HRV 38ms vs 30д нормы 45ms (падение 15%). RHR +4 bpm. "
                         "Паттерн нагрузки 4 дня подряд.",
            "recommendations": [],
            "safety_flags": ["HRV устойчиво снижена 4 дня — смотреть recovery"]
                           if window == "weekly_curr" else [],
            "evidence_pmids": ["37445218"],
            "confidence": 0.85,
        },
        "recovery": {
            "role": "Recovery coach",
            "soap": {},
            "narrative": "Readiness 68 средняя за 4 дня vs 78 обычной. Накопленная нагрузка.",
            "recommendations": [],
            "safety_flags": [],
            "evidence_pmids": [],
            "confidence": 0.82,
        },
    }
    return base


# --- Briefs: last 7 days ---

def _seed_briefs(s: Session, user: User) -> None:
    today = date.today()
    texts = [
        ("Сегодня", 0, "Утром RHR подрос на 4 удара и HRV ниже обычного уже четвёртый день. "
                       "В чек-инах ты сам отметил усталость и головную боль — не похоже на перетрен, "
                       "похоже на накопленный недосып и стресс. Сон в пределах 7ч, но эффективность "
                       "упала. Сегодня лучше без интенсива: zone-2 прогулка 30 мин и отбой на час раньше. "
                       "Если завтра паттерн сохранится — добавим к плану CBC+CRP.",
         ["HRV 38ms — ниже 30д нормы", "RHR рост +4 bpm", "Лёгкий день + ранний отбой"]),
        ("Вчера", 1, "Показатели похожие на предыдущий день — паттерн устойчивый. Сон 7.0ч с "
                     "увеличенной задержкой засыпания. Стресс-маркеры держатся.",
         ["Паттерн держится", "Ограничить кофе после 14:00"]),
        ("Позавчера", 2, "HRV начала падать, пока в пределах вариабельности. Активность на уровне. "
                         "Один чек-ин про стресс на работе.",
         ["Первый день сниженной HRV", "Без изменений в плане"]),
        ("3 дня назад", 3, "Всё в норме. Сон 7.5ч, readiness 81. Тренировка zone-2 прошла с "
                            "нормальным восстановлением.",
         ["Норм день", "HRV 44ms — база"]),
        ("4 дня назад", 4, "Высокий readiness 84. Силовая прошла хорошо. HRV и RHR в норме. "
                            "Ел больше овощей — это заметил сам, отмечу.",
         ["Силовая ок", "Питание в +"]),
        ("5 дней назад", 5, "Восстановительный день после силовой — по плану. Активности мало "
                             "но это нормально в рамках недельного цикла.",
         ["Рекавери день"]),
        ("6 дней назад", 6, "Начало недели. Выспался на выходных, показатели на личной базе.",
         ["Старт недели на базе"]),
    ]
    for label, days_ago, text, highlights in texts:
        flags = {}
        if days_ago == 0:
            flags = {"stress_hrv": ["HRV устойчиво снижена 4 дня"]}
        b = Brief(
            user_id=user.id,
            for_date=today - timedelta(days=days_ago),
            created_at=datetime.utcnow() - timedelta(days=days_ago, hours=22),
            text=text, highlights=highlights, lifestyle_flags=flags,
        )
        s.add(b)


# --- Tasks: mix of open (recent) and closed (old) ---

def _seed_tasks(s: Session, user: User, reports: list[MdtReport]) -> None:
    latest_weekly = reports[-1]
    prev_weekly = reports[-2] if len(reports) > 1 else reports[-1]
    monthly = reports[0]

    def mk(days_ago: int, **kw):
        created_at = datetime.utcnow() - timedelta(days=days_ago)
        t = Task(user_id=user.id, created_at=created_at, **kw)
        s.add(t)
        return t

    # Open — from latest weekly
    mk(2, created_by="gp", title="Пить на 0.5л воды больше сегодня",
       detail="HRV падает, один из факторов — лёгкое обезвоживание на фоне жаркой погоды.",
       priority="low", due=date.today(), source_report_id=latest_weekly.id,
       status="open")
    mk(2, created_by="coach:stress_hrv", title="Дыхание 4-7-8 перед сном 3 дня",
       detail="10 минут, помогает перевести ВНС в парасимпатику до засыпания.",
       priority="normal", due=date.today() + timedelta(days=2),
       status="open")
    mk(2, created_by="coach:recovery", title="Сегодня без интенсивных тренировок",
       detail="Readiness 68 — лучше zone-2 прогулка 30 мин.",
       priority="normal", due=date.today(), status="open")

    # Open — from monthly
    mk(33, created_by="gp", title="Записаться к кардиологу (SCORE2 + LDL)",
       detail="Обсудить 10-летний СС-риск и тактику по LDL с учётом семейной истории.",
       priority="urgent", due=date.today() + timedelta(days=7),
       source_report_id=monthly.id, status="open",
       reminders_url="shortcuts://run-shortcut?name=HealthMDT%20Add&input="
                     "Визит%20к%20кардиологу||SCORE2%20и%20LDL||")

    mk(33, created_by="gp", title="Начать пищевой лог на 14 дней",
       detail="Фиксировать всё, чтобы нутрициолог мог дать конкретные рекомендации.",
       priority="normal", due=date.today() + timedelta(days=1),
       source_report_id=monthly.id, status="open")

    mk(33, created_by="gp", title="Добавить 2 силовые тренировки в неделю",
       detail="Для инсулин-чувствительности на фоне растущего HbA1c.",
       priority="normal", due=date.today() + timedelta(days=3),
       source_report_id=monthly.id, status="open")

    # Closed — old wins
    mk(45, created_by="gp", title="Записаться на повторную липидограмму",
       detail="6 мес после последнего забора.",
       priority="normal", status="done",
       closed_at=datetime.utcnow() - timedelta(days=31),
       source_report_id=monthly.id)

    mk(20, created_by="coach:sleep", title="Отбой в 23:00 3 дня подряд",
       detail="Consistency — важнее длительности.",
       priority="normal", status="done",
       closed_at=datetime.utcnow() - timedelta(days=16))

    mk(60, created_by="user", title="Купить измеритель АД",
       detail="Домашний тонометр для мониторинга.",
       priority="low", status="done",
       closed_at=datetime.utcnow() - timedelta(days=58))


# --- Chat conversations ---

def _seed_conversations(s: Session, user: User) -> None:
    now = datetime.utcnow()

    c1 = Conversation(
        user_id=user.id, title="Почему HRV упала?",
        created_at=now - timedelta(days=1, hours=2),
        updated_at=now - timedelta(days=1, hours=1, minutes=40),
    )
    s.add(c1)
    s.commit()
    s.refresh(c1)
    _add_messages(s, c1.id, [
        ("user", "Почему у меня в последние дни упала HRV?", now - timedelta(days=1, hours=2)),
        ("assistant",
         "Смотрю твои данные за последнюю неделю. HRV упала с ~45мс (твоя 30-дневная база) "
         "до ~38мс за 4 ночи подряд, параллельно resting HR подрос на 4 удара. Это классическая "
         "пара маркеров, и у неё три частых объяснения в порядке вероятности: накопленный недосып "
         "(твоя эффективность сна тоже подсела), стресс (в чек-инах ты сам пишешь про нагрузку "
         "на работе), или лёгкая инфекция в инкубации.\n\n"
         "Пока это не тянет на тревогу — один из этих факторов всегда где-то есть. Но если "
         "паттерн продержится ещё 2-3 дня без видимой причины, имеет смысл сдать общий анализ "
         "крови и CRP, чтобы исключить скрытую инфекцию.\n\n"
         "На сегодня — ранний отбой и zone-2 вместо интенсива. ⚠ Если появится температура, "
         "кашель или необычная боль — не откладывай к врачу.",
         now - timedelta(days=1, hours=1, minutes=45),
         {"safety_flags": ["Если появится температура, кашель или необычная боль — не откладывай к врачу"],
          "confidence": 0.82}),
        ("user", "А я вчера ещё потренировался как обычно. Это могло усугубить?",
         now - timedelta(days=1, hours=1, minutes=43)),
        ("assistant",
         "Да, это добавило нагрузки. При уже сниженной HRV интенсивная тренировка — это "
         "дополнительный стресс, который ВНС не успевает отработать за ночь. Readiness-score "
         "у тебя после той тренировки упал до 64, это низко для твоего обычного уровня.\n\n"
         "Правило для таких дней: если утром HRV ниже 30д нормы на 15%+ или readiness <70 — "
         "заменяй интенсив на zone-2 или полностью отдыхай. Это не лень, это целенаправленное "
         "восстановление.",
         now - timedelta(days=1, hours=1, minutes=40),
         {"confidence": 0.85}),
    ])

    c2 = Conversation(
        user_id=user.id, title="Что с моими анализами липидов?",
        created_at=now - timedelta(days=7, hours=3),
        updated_at=now - timedelta(days=7, hours=2, minutes=45),
    )
    s.add(c2)
    s.commit()
    s.refresh(c2)
    _add_messages(s, c2.id, [
        ("user", "Что с моими анализами липидов? Насколько всё плохо?",
         now - timedelta(days=7, hours=3)),
        ("assistant",
         "Давай по порядку. Твой LDL 3.6 ммоль/л — это выше референса (<3.0) и, что важнее, "
         "выше чем было 6 и 12 месяцев назад (2.8 → 3.2 → 3.6). Тренд растущий.\n\n"
         "Интерпретация зависит от общего СС-риска. У тебя есть два фактора, которые его "
         "повышают: отец с ишемической болезнью в 58 и 21 pack-year курения (хотя ты бросил "
         "6 мес назад — плюс, но анамнез остаётся). При наличии семейной ИБС в возрасте <55 у "
         "мужчин часто пересчитывают таргет LDL на более строгий — <2.5 или даже <1.8.\n\n"
         "Словом: не катастрофа, но и не «само пройдёт». Стоит сходить к кардиологу, посчитать "
         "SCORE2 и обсудить, нужна ли медикаментозная терапия или пока диета + активность.\n\n"
         "⚠ Если когда-либо будет давящая боль в груди, одышка при нагрузке или перебои сердца — "
         "это экстренное, не ждать приёма.",
         now - timedelta(days=7, hours=2, minutes=45),
         {"safety_flags": ["Если когда-либо будет давящая боль в груди, одышка при нагрузке или перебои сердца — это экстренное, не ждать приёма"],
          "confidence": 0.87}),
    ])


def _add_messages(s: Session, conv_id: int, msgs: list[tuple]) -> None:
    for m in msgs:
        role, content, created_at = m[0], m[1], m[2]
        meta = m[3] if len(m) > 3 else {}
        s.add(ChatMessage(
            conversation_id=conv_id, role=role, content=content,
            created_at=created_at, meta=meta,
        ))


# --- Summary ---

def _print_summary(s: Session, user: User) -> None:
    counts = {
        "Metrics": s.exec(select(Metric)).all(),
        "LabResults": s.exec(select(LabResult)).all(),
        "Checkins": s.exec(select(Checkin)).all(),
        "Medications": s.exec(select(Medication)).all(),
        "Documents": s.exec(select(Document)).all(),
        "MdtReports": s.exec(select(MdtReport)).all(),
        "Briefs": s.exec(select(Brief)).all(),
        "Tasks": s.exec(select(Task)).all(),
        "Conversations": s.exec(select(Conversation)).all(),
        "ChatMessages": s.exec(select(ChatMessage)).all(),
        "PubmedEvidence": s.exec(select(PubmedEvidence)).all(),
    }
    print(f"✓ Demo заcиден для user id={user.id} ({user.name})")
    for k, rows in counts.items():
        print(f"  - {k}: {len(rows)}")
    print()
    print("Открывай UI — все страницы уже населены. LLM-ключ не требуется для просмотра,")
    print("кнопки 'Сгенерировать' потребуют ключ только для живой перегенерации.")


if __name__ == "__main__":
    seed()
