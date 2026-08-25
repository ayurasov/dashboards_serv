"""Support module models — imported by models.py via star-import.

Kept separate to avoid growing models.py further.
"""
import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, UniqueConstraint
from .database import Base


class SupportWeekRecord(Base):
    """One row per ISO week of tech-support activity."""
    __tablename__ = "support_week_records"

    id = Column(Integer, primary_key=True)
    period = Column(String(20), nullable=False, unique=True)  # e.g. '2026-W32'
    year = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("year", "week", name="uq_support_year_week"),)

    # Core KPIs
    totalinwork = Column(Float, nullable=True)     # tickets in work
    availtotal = Column(Float, nullable=True)      # availability minutes total
    newreceived = Column(Float, nullable=True)     # new tickets
    renewed = Column(Float, nullable=True)         # renewed tickets
    totalsolvedweek = Column(Float, nullable=True) # tickets solved this week
    ratiosolvedreceived = Column(Float, nullable=True)  # solved/received ratio

    # Client hours
    rushydrohours = Column(Float, nullable=True)
    transnefthours = Column(Float, nullable=True)
    roscosmoshours = Column(Float, nullable=True)
    bryanskhours = Column(Float, nullable=True)
    mchshours = Column(Float, nullable=True)
    internalsaleshours = Column(Float, nullable=True)  # internal + SALES

    # AlterOS tickets
    altostotal = Column(Float, nullable=True)
    altos12line = Column(Float, nullable=True)
    altos3line = Column(Float, nullable=True)
    altosavgtime = Column(Float, nullable=True)    # avg close time, hours
    altosavailtotal = Column(Float, nullable=True)
    altosavail13 = Column(Float, nullable=True)
    altosavail47 = Column(Float, nullable=True)
    altosavail810 = Column(Float, nullable=True)

    # AlterOS channels
    altosrusgemail = Column(Float, nullable=True)
    altosrusgtf = Column(Float, nullable=True)
    altosotheremail = Column(Float, nullable=True)
    altosothertf = Column(Float, nullable=True)

    # AlterOffice tickets
    altofficetotal = Column(Float, nullable=True)
    altoffice12line = Column(Float, nullable=True)
    altoffice3line = Column(Float, nullable=True)
    altofficeavgtime = Column(Float, nullable=True)
    altofficeavailtotal = Column(Float, nullable=True)
    altofficeavail13 = Column(Float, nullable=True)
    altofficeavail47 = Column(Float, nullable=True)
    altofficeavail810 = Column(Float, nullable=True)

    # AlterOffice channels
    altofficerusgemail = Column(Float, nullable=True)
    altofficerusgtf = Column(Float, nullable=True)
    altofficeotheremail = Column(Float, nullable=True)
    altofficeothertf = Column(Float, nullable=True)

    # Project Server
    projservertaken = Column(Float, nullable=True)
    projserversolved = Column(Float, nullable=True)
    projserveravail = Column(Float, nullable=True)

    extra = Column(Text, nullable=True)  # JSON string for future fields

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
