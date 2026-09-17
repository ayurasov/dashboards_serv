"""PDF export router."""
import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..deps import get_current_user
from ..services.pdf_export import (
    generate_dashboard_pdf, generate_summary_pdf, generate_registry_pdf,
    generate_benchmarks_pdf, generate_partnerships_pdf, generate_partnerships_summary_pdf,
)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _month_range(d1: datetime.date, d2: datetime.date) -> list[datetime.date]:
    """Inclusive list of first-of-month dates between d1 and d2 (any order)."""
    if d1 > d2:
        d1, d2 = d2, d1
    out = []
    while d1 <= d2:
        out.append(d1)
        d1 = datetime.date(d1.year + (d1.month == 12), d1.month % 12 + 1, 1)
    return out


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/dashboard")
def export_dashboard(
    from_month: str = "",
    to_month: str = "",
    period: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # The exported report covers the same month range the dashboard shows.
    months_filter = None
    if from_month or to_month:
        try:
            y1, m1 = (from_month or to_month).split("-")
            y2, m2 = (to_month or from_month).split("-")
            d1 = datetime.date(int(y1), int(m1), 1)
            d2 = datetime.date(int(y2), int(m2), 1)
            months_filter = [d.strftime("%Y-%m") for d in _month_range(d1, d2)]
        except ValueError:
            months_filter = None
    period_label = period or ""
    if not period_label and months_filter:
        period_label = f"{months_filter[0]} — {months_filter[-1]}"
    pdf_bytes = generate_dashboard_pdf(db, period_label=period_label or "все месяцы",
                                       months_filter=months_filter)
    # Content-Disposition is a Latin-1 header: keep the filename ASCII-safe.
    file_suffix = "_".join(months_filter[:2]).replace("-", "") if months_filter else (period or "all")
    if not file_suffix or not file_suffix.isascii():
        file_suffix = "all"
    return _pdf(pdf_bytes, f"hr_dashboard_{file_suffix}.pdf")


@router.get("/summary")
def export_summary(
    period_type: str = "quarter",
    from_period: str = "",
    to_period: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = generate_summary_pdf(db, period_type=period_type,
                                from_period=from_period, to_period=to_period)
    return _pdf(data, f"hr_summary_{period_type}.pdf")


@router.get("/registry")
def export_registry(
    month: str = "",
    event_type: str = "",
    department: str = "",
    search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = generate_registry_pdf(db, month_key=month, event_type=event_type,
                                department=department, search=search)
    return _pdf(data, "hr_registry.pdf")


@router.get("/benchmarks")
def export_benchmarks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _pdf(generate_benchmarks_pdf(db), "hr_benchmarks.pdf")


@router.get("/partnerships")
def export_partnerships(
    status: str = "",
    almi_product: str = "",
    direction: str = "",
    type: str = "",
    search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = generate_partnerships_pdf(db, status=status, almi_product=almi_product,
                                     direction=direction, type_=type, search=search)
    return _pdf(data, "partnerships_registry.pdf")


@router.get("/partnerships-summary")
def export_partnerships_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _pdf(generate_partnerships_summary_pdf(db), "partnerships_summary.pdf")
