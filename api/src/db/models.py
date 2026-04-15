"""SQLModel tables — one SQLite file, zero-config."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field, JSON, Column


class User(SQLModel, table=True):
    """Single-user MVP — but schema supports multi-user for future."""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    name: str = "You"
    birthdate: Optional[date] = None
    sex: Optional[str] = None  # 'M' | 'F' | 'other'
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    timezone: str = "Europe/Amsterdam"
    # Free-form context the user writes about themselves (conditions, meds, goals)
    context: str = ""
    # Telegram chat linking
    telegram_chat_id: Optional[int] = None


class Metric(SQLModel, table=True):
    """Time-series metrics from Oura, Apple Health, manual entry.

    `source` ∈ {'oura','apple_health','manual','derived'}.
    `kind` is the metric identifier (e.g. 'hrv_rmssd', 'resting_hr', 'sleep_duration', 'steps').
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ts: datetime = Field(index=True)
    source: str = Field(index=True)
    kind: str = Field(index=True)
    value: float
    unit: str = ""
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON))


class LabResult(SQLModel, table=True):
    """Lab values extracted from PDFs / manual entry, with validity windows."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    drawn_at: date = Field(index=True)
    panel: str  # 'cbc', 'cmp', 'lipids', 'thyroid', 'hba1c', 'vitamin_d', etc.
    analyte: str  # 'hemoglobin', 'ldl', 'tsh', etc.
    value: float
    unit: str
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    flag: Optional[str] = None  # 'L', 'H', 'critical', None
    source_document_id: Optional[int] = Field(default=None, foreign_key="document.id")


class Document(SQLModel, table=True):
    """Scanned medical documents — PDF or photo, processed by vision."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    filename: str
    path: str
    mime: str
    # Extracted structured content (lab panels, diagnoses, prescriptions)
    extracted: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "pending"  # pending | processed | failed
    summary: str = ""


class Checkin(SQLModel, table=True):
    """Free-text check-in from the user (via bot or web)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ts: datetime = Field(default_factory=datetime.utcnow, index=True)
    text: str
    mood: Optional[int] = None  # 1-5
    energy: Optional[int] = None
    sleep_quality: Optional[int] = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class MdtReport(SQLModel, table=True):
    """A consilium — specialist notes + GP synthesis."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    kind: str  # 'weekly', 'monthly', 'ad_hoc'
    # Each specialist's SOAP-structured note keyed by agent name
    specialist_notes: dict = Field(default_factory=dict, sa_column=Column(JSON))
    gp_synthesis: str = ""
    problem_list: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    safety_net: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence_pmids: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Brief(SQLModel, table=True):
    """Daily morning brief — 4-7 sentences from GP."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    for_date: date = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    text: str
    lifestyle_flags: dict = Field(default_factory=dict, sa_column=Column(JSON))
    highlights: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Task(SQLModel, table=True):
    """Task lifecycle: open → in_progress → done | dismissed.

    Optionally exported to Apple Reminders via a shortcut.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_by: str  # 'gp' | 'specialist:cardiologist' | 'user'
    title: str
    detail: str = ""
    priority: str = "normal"  # 'urgent' | 'normal' | 'low'
    due: Optional[date] = None
    status: str = "open"
    closed_at: Optional[datetime] = None
    last_reminded_at: Optional[datetime] = None
    source_report_id: Optional[int] = Field(default=None, foreign_key="mdtreport.id")
    # Apple Reminders URL scheme / x-callback-url
    reminders_url: Optional[str] = None


class PubmedEvidence(SQLModel, table=True):
    """Cached PubMed hits — evidence base for agent conclusions."""
    id: Optional[int] = Field(default=None, primary_key=True)
    fetched_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    query: str = Field(index=True)
    pmid: str = Field(index=True)
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    journal: str = ""
    pub_year: Optional[int] = None
