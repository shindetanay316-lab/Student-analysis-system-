from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import db
from ..models import (
    ExamReport,
    ImportJob,
    ReportStudent,
    ResultComponent,
    SubjectResult,
)
from ..services.analysis_service import build_report_analysis


analysis_bp = Blueprint(
    "result_analysis", __name__, url_prefix="/result-data/analysis"
)


@analysis_bp.get("/")
@login_required
def index():
    latest_job = db.session.scalar(
        db.select(ImportJob)
        .where(ImportJob.report.has())
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    if latest_job is None:
        flash("Upload and extract a result PDF before opening analysis.", "warning")
        return redirect(url_for("result_imports.upload"))
    return redirect(url_for("result_analysis.dashboard", import_job_id=latest_job.id))


@analysis_bp.get("/imports/<int:import_job_id>")
@login_required
def dashboard(import_job_id: int):
    statement = (
        db.select(ImportJob)
        .where(ImportJob.id == import_job_id)
        .options(
            selectinload(ImportJob.report).selectinload(ExamReport.subjects),
            selectinload(ImportJob.report).selectinload(ExamReport.corrections),
            selectinload(ImportJob.report)
            .selectinload(ExamReport.students)
            .selectinload(ReportStudent.summary),
            selectinload(ImportJob.report)
            .selectinload(ExamReport.students)
            .selectinload(ReportStudent.subject_results)
            .selectinload(SubjectResult.components)
            .selectinload(ResultComponent.assessment),
        )
    )
    job = db.first_or_404(statement)
    if job.report is None:
        flash("Extract this PDF before opening its analysis dashboard.", "warning")
        return redirect(url_for("result_imports.detail", import_job_id=job.id))

    analysis = build_report_analysis(job.report)
    return render_template(
        "result_data/analysis/dashboard.html",
        job=job,
        report=job.report,
        analysis=analysis,
    )
