"""Observaciones mínimas para cohortes; sin staff ni contenido clínico."""
import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Date, ForeignKey, UniqueConstraint
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
