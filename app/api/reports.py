"""Report routes: list, generate, fetch."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owned_brand
from app.models import Brand, Report, ReportType
from app.reports.specs import has_spec
from app.schemas import ReportCreate, ReportDetail, ReportSummary
from app.services import generate_ai_report, generate_money_flow_report

router = APIRouter(prefix="/api/brands/{brand_id}/reports", tags=["reports"])


@router.get("", response_model=list[ReportSummary])
def list_reports(brand: Brand = Depends(get_owned_brand), db: Session = Depends(get_db)):
    return (
        db.query(Report)
        .filter(Report.brand_id == brand.id)
        .order_by(Report.created_at.desc())
        .all()
    )


@router.post("", response_model=ReportDetail, status_code=201)
def create_report(
    body: ReportCreate,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    # money_flow computes its own metrics from connected data.
    if body.type == ReportType.money_flow:
        return generate_money_flow_report(db, brand, body.period_start, body.period_end)

    # Spec-backed report types are narrated from a supplied facts bundle until
    # each grows a live compute path.
    if has_spec(body.type):
        if not body.facts:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Report type '{body.type.value}' requires a 'facts' bundle "
                "(no live compute path yet).",
            )
        return generate_ai_report(
            db, brand, body.type, body.period_start, body.period_end, body.facts
        )

    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"Report type '{body.type.value}' not implemented yet",
    )


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(
    report_id: str,
    brand: Brand = Depends(get_owned_brand),
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if not report or report.brand_id != brand.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return report
