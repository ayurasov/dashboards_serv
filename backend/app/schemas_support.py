"""Pydantic schemas for the tech-support module."""
from typing import Optional
from pydantic import BaseModel


class SupportWeekBase(BaseModel):
    year: int
    week: int
    totalinwork: Optional[float] = None
    availtotal: Optional[float] = None
    newreceived: Optional[float] = None
    renewed: Optional[float] = None
    totalsolvedweek: Optional[float] = None
    ratiosolvedreceived: Optional[float] = None
    rushydrohours: Optional[float] = None
    transnefthours: Optional[float] = None
    roscosmoshours: Optional[float] = None
    bryanskhours: Optional[float] = None
    mchshours: Optional[float] = None
    internalsaleshours: Optional[float] = None
    altostotal: Optional[float] = None
    altos12line: Optional[float] = None
    altos3line: Optional[float] = None
    altosavgtime: Optional[float] = None
    altosavailtotal: Optional[float] = None
    altosavail13: Optional[float] = None
    altosavail47: Optional[float] = None
    altosavail810: Optional[float] = None
    altosrusgemail: Optional[float] = None
    altosrusgtf: Optional[float] = None
    altosotheremail: Optional[float] = None
    altosothertf: Optional[float] = None
    altofficetotal: Optional[float] = None
    altoffice12line: Optional[float] = None
    altoffice3line: Optional[float] = None
    altofficeavgtime: Optional[float] = None
    altofficeavailtotal: Optional[float] = None
    altofficeavail13: Optional[float] = None
    altofficeavail47: Optional[float] = None
    altofficeavail810: Optional[float] = None
    altofficerusgemail: Optional[float] = None
    altofficerusgtf: Optional[float] = None
    altofficeotheremail: Optional[float] = None
    altofficeothertf: Optional[float] = None
    projservertaken: Optional[float] = None
    projserversolved: Optional[float] = None
    projserveravail: Optional[float] = None
    extra: Optional[str] = None


class SupportWeekCreate(SupportWeekBase):
    pass


class SupportWeekUpdate(SupportWeekBase):
    year: Optional[int] = None
    week: Optional[int] = None


class SupportWeekOut(SupportWeekBase):
    id: int
    period: str

    model_config = {"from_attributes": True}
