"""PDF export router."""
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


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/dashboard")
def export_dashboard(
    period: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    months_filter = None
    period_label = period or "все месяцы"
    pdf_bytes = generate_dashboard_pdf(db, period_label=period_label, months_filter=months_filter)
    return _pdf(pdf_bytes, f"hr_dashboard_{period or 'all'}.pdf")


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
