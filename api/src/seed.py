"""Seed a demo user with 30 days of realistic metrics + a sample lab panel.

Run inside the api container or with venv activated:
    python -m src.seed
or via docker compose:
    docker compose exec api python -m src.seed

Idempotent-ish: clears existing demo data first.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from .db import Checkin, LabResult, Metric, Task, User
from .db.session import engine, init_db


def seed() -> None:
    init_db()
    random.seed(42)

    with Session(engine) as s:
        # Clear prior seed
        s.execute(delete(Metric))
        s.execute(delete(LabResult))
        s.execute(delete(Checkin))
        s.execute(delete(Task))
        s.commit()

        # Ensure user exists
        user = s.exec(select(User)).first()
        if not user:
            user = User(
                name="Демо",
                birthdate=date(1988, 5, 12),
                sex="M",
                height_cm=180,
                weight_kg=78,
                context="Бросил курить 6 мес назад. Родитель с ишемической болезнью сердца. Цель — держать LDL <2.0, сон >7ч, активность минимум 8k шагов.",
            )
            s.add(user)
            s.commit()
            s.refresh(user)

        now = datetime.utcnow()
        # 30 days of metrics
        for i in range(30, -1, -1):
            ts = now - timedelta(days=i)
            # Add plausible, correlated values
            weekend = ts.weekday() >= 5
            # HRV: ~45ms baseline, slight downward trend last week
            hrv = 45 + random.gauss(0, 4) - (i < 7) * 6
            # Resting HR: ~56 baseline, slight rise last week
            rhr = 56 + random.gauss(0, 2) + (i < 7) * 3
            # Sleep duration (seconds)
            sleep = 3600 * (7.2 + random.gauss(0, 0.8) - (weekend * -0.3))
            # Steps
            steps = int(8500 + random.gauss(0, 2200) - (weekend * -1500))
            # Readiness
            readiness = max(40, min(95, int(78 + random.gauss(0, 8) - (i < 7) * 6)))
            # Activity score
            activity = max(30, min(98, int(72 + random.gauss(0, 10))))
            # Sleep score
            sleep_score = max(30, min(98, int(76 + random.gauss(0, 7) - (i < 7) * 4)))

            metrics = [
                ("hrv_rmssd_night", max(15, hrv), "ms"),
                ("resting_hr", min(90, rhr), "bpm"),
                ("sleep_duration", max(3600, sleep), "seconds"),
                ("sleep_score", sleep_score, "score"),
                ("steps", max(500, steps), "count"),
                ("readiness_score", readiness, "score"),
                ("activity_score", activity, "score"),
                ("active_calories", max(50, 380 + random.gauss(0, 120)), "kcal"),
            ]
            for kind, val, unit in metrics:
                s.add(Metric(
                    user_id=user.id, ts=ts, source="oura", kind=kind,
                    value=float(val), unit=unit, meta={"seeded": True},
                ))

        # Lab panel — 3 months ago
        lab_date = date.today() - timedelta(days=90)
        lipids = [
            ("total_cholesterol", 5.4, "mmol/L", 3.0, 5.2, "H"),
            ("ldl_cholesterol", 3.6, "mmol/L", 0.0, 3.0, "H"),
            ("hdl_cholesterol", 1.2, "mmol/L", 1.0, 1.5, None),
            ("triglycerides", 1.3, "mmol/L", 0.0, 1.7, None),
        ]
        for analyte, value, unit, lo, hi, flag in lipids:
            s.add(LabResult(
                user_id=user.id, drawn_at=lab_date, panel="lipids",
                analyte=analyte, value=value, unit=unit,
                ref_low=lo, ref_high=hi, flag=flag,
            ))

        cbc = [
            ("hemoglobin", 15.1, "g/dL", 13.0, 17.0, None),
            ("hematocrit", 45, "%", 40, 52, None),
            ("ferritin", 68, "ng/mL", 30, 400, None),
        ]
        for analyte, value, unit, lo, hi, flag in cbc:
            s.add(LabResult(
                user_id=user.id, drawn_at=lab_date, panel="cbc",
                analyte=analyte, value=value, unit=unit,
                ref_low=lo, ref_high=hi, flag=flag,
            ))

        metabolic = [
            ("glucose_fasting", 5.6, "mmol/L", 3.9, 5.5, "H"),
            ("hba1c", 5.7, "%", 4.0, 5.6, "H"),
            ("tsh", 2.1, "mIU/L", 0.4, 4.0, None),
            ("vitamin_d", 22, "ng/mL", 30, 100, "L"),
        ]
        for analyte, value, unit, lo, hi, flag in metabolic:
            panel = "hba1c" if analyte == "hba1c" else "vitamin_d" if analyte == "vitamin_d" else "cmp" if analyte == "glucose_fasting" else "thyroid"
            s.add(LabResult(
                user_id=user.id, drawn_at=lab_date, panel=panel,
                analyte=analyte, value=value, unit=unit,
                ref_low=lo, ref_high=hi, flag=flag,
            ))

        # Check-ins
        for i, text in enumerate([
            "Спал нормально, но устал к вечеру. 2 чашки кофе.",
            "Много работы, стресс, пропустил пробежку.",
            "Отличный сон, давно так не высыпался.",
            "Вчера тренировался сильно — сегодня чувствую усталость.",
            "Болит голова к концу дня второй раз на этой неделе.",
        ]):
            s.add(Checkin(
                user_id=user.id,
                ts=now - timedelta(days=i * 2),
                text=text,
                mood=random.choice([3, 4, 3, 5]),
                energy=random.choice([3, 2, 4, 3]),
                sleep_quality=random.choice([4, 3, 5, 4]),
                tags=[],
            ))

        s.commit()
        print(f"✓ Demo data seeded for user id={user.id}")
        print("  - 30 дней метрик (HRV, RHR, sleep, steps, readiness)")
        print("  - Липидный профиль (LDL повышен), HbA1c на границе, vitamin D низкий")
        print("  - 5 чек-инов")
        print("  Запусти: POST /reports/brief/generate и /reports/mdt/run в UI — увидишь консилиум.")


if __name__ == "__main__":
    seed()
