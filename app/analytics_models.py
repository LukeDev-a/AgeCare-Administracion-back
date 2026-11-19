"""Observaciones mínimas para cohortes; sin staff ni contenido clínico."""
import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models import pk, ts_now, PortableJSON

class AnalyticsAccount(Base):
    __tablename__ = 'analytics_accounts'
    __table_args__ = (UniqueConstraint('data_origin', 'external_id'),)
    id: Mapped[uuid.UUID] = pk()
    external_id: Mapped[str] = mapped_column(String(120))
    profile: Mapped[str] = mapped_column(String(12))
    data_origin: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class AnalyticsActivity(Base):
    __tablename__ = 'analytics_activity'
    __table_args__ = (UniqueConstraint('data_origin', 'external_id'),)
    id: Mapped[uuid.UUID] = pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('analytics_accounts.id'), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60))
    data_origin: Mapped[str] = mapped_column(String(12))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class AnalyticsPayment(Base):
    __tablename__ = 'analytics_payments'
    __table_args__ = (UniqueConstraint('data_origin', 'external_id'),)
    id: Mapped[uuid.UUID] = pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('analytics_accounts.id'), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    data_origin: Mapped[str] = mapped_column(String(12))
    amount_minor: Mapped[int] = mapped_column(Integer)
    successful: Mapped[bool] = mapped_column(Boolean)
    subscription_active: Mapped[bool] = mapped_column(Boolean)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class AnalyticsSource(Base):
    __tablename__ = 'analytics_sources'
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    data_origin: Mapped[str] = mapped_column(String(12), primary_key=True)
    available_through: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = ts_now()
    revision: Mapped[int] = mapped_column(Integer, default=1)

class AnalyticsCohortSnapshot(Base):
    __tablename__ = 'analytics_cohort_snapshots'
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    data_origin: Mapped[str] = mapped_column(String(12), primary_key=True)
    payload: Mapped[dict] = mapped_column(PortableJSON)
    source_signature: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = ts_now()


class UsageAccount(Base):
    """Identidad sintética solo para actividad/adopción, sin login ni directorio."""
    __tablename__ = 'analytics_usage_accounts'
    id: Mapped[uuid.UUID] = pk()
    profile: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_origin: Mapped[str] = mapped_column(String(12), default='demo')
    __table_args__ = (CheckConstraint("profile IN ('family','caregiver','elder','doctor')", name='ck_usage_profile'),)


class UsageSession(Base):
    """Sesión de demostración: duración y funciones del mismo usuario/instante."""
    __tablename__ = 'analytics_usage_sessions'
    id: Mapped[uuid.UUID] = pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('analytics_usage_accounts.id'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    feature_keys: Mapped[list] = mapped_column(PortableJSON)
    data_origin: Mapped[str] = mapped_column(String(12), default='demo')
    __table_args__ = (
        CheckConstraint('duration_seconds > 0', name='ck_usage_duration'),
        Index('ix_usage_sessions_time_account', 'started_at', 'account_id'),
    )
