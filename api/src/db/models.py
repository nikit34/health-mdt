"""SQLModel tables — one SQLite file, zero-config."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field, JSON, Column


class User(SQLModel, table=True):
    """User account — same row works for single-user PIN and multi-user OAuth modes."""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    name: str = "You"
    # Identity — populated when AUTH_MODE=oauth; unique when set.
    email: Optional[str] = Field(default=None, index=True, unique=True)
    oauth_provider: Optional[str] = None  # 'google' | None
    oauth_sub: Optional[str] = Field(default=None, index=True)
    avatar_url: Optional[str] = None

    birthdate: Optional[date] = None
    sex: Optional[str] = None  # 'M' | 'F' | 'other'
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    timezone: str = "Europe/Amsterdam"
    # Free-form context the user writes about themselves (conditions, meds, goals)
    context: str = ""
    # Telegram chat linking
    telegram_chat_id: Optional[int] = None

    # Notification preferences
    email_notifications: bool = False
    notification_email: Optional[str] = None  # separate from oauth email if desired
    push_notifications: bool = True  # on by default when subscribed


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


class Conversation(SQLModel, table=True):
    """A chat thread between user and GP — preserves context across turns."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    title: str = ""  # derived from first user message, truncated
    # When False, skip from history lists (user-archived)
    active: bool = True


class ChatMessage(SQLModel, table=True):
    """One message in a Conversation."""
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    role: str  # 'user' | 'assistant'
    content: str
    # Optional metadata — safety flags, follow-ups extracted from assistant text
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON))


class PushSubscription(SQLModel, table=True):
    """Web Push subscription — one per browser per user."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    endpoint: str = Field(index=True)
    p256dh: str
    auth: str
    user_agent: str = ""


class WaitlistSignup(SQLModel, table=True):
    """Landing-page email capture — prospect pool before billing is live.

    No foreign key to User: prospects aren't users yet. IP is stored as a SHA256
    hash so rate-limiting works without keeping PII.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    email: str = Field(index=True)
    note: str = ""
    tier: Optional[str] = None  # 'free' | '9' | '29' | '79' — which plan they clicked
    ip_hash: str = ""
    user_agent: str = ""
    referrer: str = ""


class Medication(SQLModel, table=True):
    """Active or past medication the user is taking.

    Doses are denormalized as free text (e.g. "5 mg") rather than numeric because
    a lot of real-world meds are "1/2 tab PRN" or "as directed". Agents read `name`
    + `dose` + `frequency` as strings.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    name: str  # "Metformin", "Vitamin D3"
    dose: str = ""  # "500 mg", "5000 IU"
    frequency: str = ""  # "twice daily", "weekly", "as needed"
    started_on: Optional[date] = None
    stopped_on: Optional[date] = None
    notes: str = ""
    # If populated: local time HH:MM for daily reminder; scheduler creates Task on time.
    reminder_time: Optional[str] = None

    @property
    def is_active(self) -> bool:
        if not self.stopped_on:
            return True
        return self.stopped_on >= date.today()
