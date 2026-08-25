"""Tech Support dashboard models."""
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, Date,
    UniqueConstraint,
)
from .database import Base


class TechSupportWeek(Base):
    """One data row per client per ISO week.

    The table mirrors the columns visible in the HTML dashboard:
    client, year, week, SLA %, incidents total/critical/resolved, avg_response_time,
    avg_resolution_time, nps, notes.
    """
    __tablename__ = "tech_support_weeks"
    id = Column(Integer, primary_key=True)
    client = Column(String(200), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)   # ISO week number 1-53
    # SLA
    sla_pct = Column(Float, nullable=True)       # % SLA выполнен
    # Incidents
    incidents_total = Column(Integer, nullable=True)
    incidents_critical = Column(Integer, nullable=True)
    incidents_resolved = Column(Integer, nullable=True)
    # Time metrics (hours)
    avg_response_h = Column(Float, nullable=True)   # среднее время реакции
    avg_resolution_h = Column(Float, nullable=True) # среднее время решения
    # Satisfaction
    nps = Column(Float, nullable=True)           # NPS или CSI балл
    notes = Column(Text, default="")
    created_at = Column(String(30), default=lambda: datetime.datetime.utcnow().isoformat())
    updated_at = Column(String(30), default=lambda: datetime.datetime.utcnow().isoformat(),
                        onupdate=lambda: datetime.datetime.utcnow().isoformat())

    __table_args__ = (
        UniqueConstraint("client", "year", "week", name="uq_ts_client_year_week"),
    )

    @property
    def period_key(self):
        return f"{self.year}-W{self.week:02d}"


class TechSupportTrafficRule(Base):
    """Editable SLA/metric threshold rules for tech support.

    Each rule belongs to a metric_key (e.g. 'sla_pct', 'avg_response_h') and
    stores green/yellow numeric thresholds plus the direction.
    """
    __tablename__ = "ts_traffic_rules"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String(80), unique=True, nullable=False, index=True)
    label = Column(String(200), nullable=False, default="")
    green_threshold = Column(Float, nullable=True)
    yellow_threshold = Column(Float, nullable=True)
    direction = Column(String(30), nullable=False, default="higher_is_better")
    enabled = Column(Boolean, default=True)
