"""SQLAlchemy models for the mock Hospital Information System (HIS)."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Hospital(Base):
    __tablename__ = "hospitals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    locality: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, default="hospital")  # hospital | clinic
    address: Mapped[str] = mapped_column(String, default="")
    network_plans: Mapped[str] = mapped_column(String, default="")  # comma-separated plan ids


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    specialty: Mapped[str] = mapped_column(String, index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    rating: Mapped[float] = mapped_column(Float)
    fee: Mapped[int] = mapped_column(Integer)
    tele_fee: Mapped[int] = mapped_column(Integer)
    experience_years: Mapped[int] = mapped_column(Integer)
    languages: Mapped[str] = mapped_column(String)  # comma-separated
    tele_available: Mapped[bool] = mapped_column(Boolean, default=False)
    in_person: Mapped[bool] = mapped_column(Boolean, default=True)


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)  # ISO yyyy-mm-dd
    start: Mapped[str] = mapped_column(String)  # HH:MM
    end: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)  # in_person | tele
    status: Mapped[str] = mapped_column(String, index=True, default="free")  # free|booked|held|cancelled
    hold_expires: Mapped[float | None] = mapped_column(Float, nullable=True)
    held_by: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class InsurancePlan(Base):
    __tablename__ = "insurance_plans"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    coverage_pct: Mapped[int] = mapped_column(Integer)  # in-network OPD coverage
    out_of_network_pct: Mapped[int] = mapped_column(Integer)
    copay: Mapped[int] = mapped_column(Integer)
    tele_covered: Mapped[bool] = mapped_column(Boolean)
    annual_opd_limit: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(String, default="")


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    locality: Mapped[str] = mapped_column(String)
    insurance_plan_id: Mapped[str] = mapped_column(ForeignKey("insurance_plans.id"))
    preferred_time: Mapped[str | None] = mapped_column(String, nullable=True)  # morning|evening
    preferred_mode: Mapped[str | None] = mapped_column(String, nullable=True)  # in_person|tele
    usual_doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, default="English")
    source: Mapped[str] = mapped_column(String, default="seed")  # seed | registered (created from the UI)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class FamilyLink(Base):
    __tablename__ = "family_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    relative_id: Mapped[str] = mapped_column(String)
    relation: Mapped[str] = mapped_column(String)  # relative is the patient's <relation>


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    doctor_id: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(String)
    specialty: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, default="in_person")
    slot_time: Mapped[str] = mapped_column(String, default="")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    patient_name: Mapped[str] = mapped_column(String, default="")
    slot_id: Mapped[str] = mapped_column(String, index=True)
    doctor_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="booked")  # booked|cancelled|rescheduled
    created_at: Mapped[float] = mapped_column(Float)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(String, default="")


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    specialty: Mapped[str] = mapped_column(String)
    doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    date_from: Mapped[str] = mapped_column(String)
    date_to: Mapped[str] = mapped_column(String)
    time_pref: Mapped[str | None] = mapped_column(String, nullable=True)
    locality: Mapped[str | None] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(String, default="any")
    status: Mapped[str] = mapped_column(String, default="waiting")  # waiting|offered|fulfilled|expired
    created_at: Mapped[float] = mapped_column(Float)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String)  # sms|email
    to: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String, default="info")
    created_at: Mapped[float] = mapped_column(Float)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Offer(Base):
    """A proactive offer (event-driven) waiting for the patient's confirmation."""

    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    event_id: Mapped[str] = mapped_column(String)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # reschedule|waitlist_fill
    old_appointment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    waitlist_id: Mapped[str | None] = mapped_column(String, nullable=True)
    slot_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|accepted|declined|failed
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[float] = mapped_column(Float)


class Memory(Base):
    """Episodic / preference memory. Mirrored into the vector store for semantic recall."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String)  # preference|episode|fact
    source: Mapped[str] = mapped_column(String, default="seed")
    created_at: Mapped[float] = mapped_column(Float)


class BlackboardWrite(Base):
    __tablename__ = "blackboard_writes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    agent: Mapped[str] = mapped_column(String)
    ts: Mapped[float] = mapped_column(Float)
    section: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)


class RunRecord(Base):
    __tablename__ = "runs"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, default="chat")  # chat|event|proactive
    user_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="running")
    outcome: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text, default="{}")
