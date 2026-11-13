from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.enums import AppRole, PeriodKey, PlanCode

class SourceFreshness(BaseModel):
    name: str
    updated_at: datetime | None = None
    available_through: datetime | None = None
    missing: bool = False
    stale: bool = False

class FreshnessOut(BaseModel):
    status: str
    sources: list[SourceFreshness]
    calculation_stale: bool

class CommercialMetadata(BaseModel):
    data_origin: str = 'unknown'
    freshness: FreshnessOut | None = None


class PeriodOut(BaseModel):
    key: PeriodKey
    start_date: date
    end_date: date


# ---- 4.1 summary ----
class CommercialDeltas(BaseModel):
    new_users_pct: float | None
    mrr_pct: float | None
    active_users_pct: float | None


class CommercialSummaryOut(CommercialMetadata):
    period: PeriodOut
    downloads: int | None
    new_users: int | None
    churned_users: int | None
    churn_rate: float | None
    active_users: int | None
    paying_users: int | None
    paying_share: float | None
    mrr_clp: int | None
    deltas: CommercialDeltas
    computed_at: datetime | None
    as_of: date | None = None


# ---- 4.2 registrations ----
class BucketOut(BaseModel):
    label: str
    start: datetime
    end: datetime


class RegistrationsOut(CommercialMetadata):
    period: PeriodOut
    granularity: str
    buckets: list[BucketOut]
    signups: list[int | None]
    cancellations: list[int | None]
    computed_at: datetime | None


# ---- 4.3 plans ----
class PlanRow(BaseModel):
    plan_code: PlanCode
    name: str
    billing_unit: Literal['account'] = 'account'
    billing_period: Literal['month'] = 'month'
    users: int
    share: float | None
    price_clp: int | None
    mrr_clp: int
    monthly_churn: float


class PlanTotals(BaseModel):
    users: int
    mrr_clp: int
    monthly_churn: float | None


class PlansOut(CommercialMetadata):
    as_of: date
    plans: list[PlanRow]
    totals: PlanTotals
    computed_at: datetime


# ---- 4.4 funnel ----
class FunnelStage(BaseModel):
    stage: str
    name: str
    users: int | None
    rate_vs_first: float | None
    rate_vs_previous: float | None = None
    unavailable_reason: str | None = None


class CohortOption(BaseModel):
    month: str
    accounts: int
    observed_accounts: int
    provisional: bool

class FunnelOut(CommercialMetadata):
    as_of: date | None
    stages: list[FunnelStage]
    computed_at: datetime | None
    cutoff_at: datetime | None = None
    cohort_month: str | None = None
    provisional: bool = True
    accounts: int = 0
    observed_accounts: int = 0
    cohorts: list[CohortOption] = []
    downloads: int | None = None
    downloads_as_of: date | None = None
    downloads_computed_at: datetime | None = None
    downloads_data_origin: str = 'unknown'
    downloads_stale: bool = False


# ---- 6.1 / 6.2 roles ----
class RoleSummaryRow(BaseModel):
    role: AppRole
    active_users: int
    growth_8w: float
    sessions_per_week: float
    avg_session_seconds: int
    retention_30d: float


class RolesSummaryOut(BaseModel):
    days: int
    roles: list[RoleSummaryRow]
    computed_at: datetime


class WeeklySeries(BaseModel):
    role: AppRole
    values: list[int]


class WeeklyPeriod(BaseModel):
    start_date: date
    end_date: date
    is_current_week: bool


class WeeklyActiveOut(BaseModel):
    weeks: list[str]
    series: list[WeeklySeries]
    computed_at: datetime
    week_details: list[WeeklyPeriod]


# ---- 7 features ----
class AdoptionCalculation(BaseModel):
    role: AppRole
    applicable: bool
    status: Literal['calculated', 'not_applicable', 'not_calculable']
    reason: Literal['not_applicable', 'missing_active_users', 'no_active_users', 'missing_usage', 'invalid_data'] | None
    users: int | None
    active_users: int | None


class FeatureAdoptionRow(BaseModel):
    feature_key: str
    name: str
    adoption: list[float | None]
    calculation_details: list[AdoptionCalculation]


class AdoptionOut(BaseModel):
    days: int
    roles: list[AppRole]
    features: list[FeatureAdoptionRow]
    computed_at: datetime


class TopFeature(BaseModel):
    feature_key: str
    name: str
    adoption: float


class TopByRole(BaseModel):
    role: AppRole
    features: list[TopFeature]


class TopOut(BaseModel):
    calculable_only: Literal[True] = True
    top_by_role: list[TopByRole]
    computed_at: datetime


class AdoptionAlert(BaseModel):
    feature_key: str
    name: str
    roles: list[AppRole]
    adoption: list[float]
    expected_low: bool
    note: str | None


class AlertsOut(BaseModel):
    calculable_only: Literal[True] = True
    threshold: float
    alerts: list[AdoptionAlert]
    computed_at: datetime
