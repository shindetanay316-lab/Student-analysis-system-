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


@analysis_bp.get('/imports/<int:import_job_id>/records')
@login_required
def records(import_job_id):
    from flask import request, abort
    from math import ceil
    from ..services.analysis_filter_service import filter_records
    job = db.get_or_404(ImportJob, import_job_id)
    if job.report is None:
        return redirect(url_for('result_imports.detail', import_job_id=job.id))
    try:
        filtered = filter_records(job.report, request.args)
    except ValueError as error:
        abort(400, str(error))
    pages = max(1, ceil(filtered['count']/25))
    page = max(1,min(request.args.get('page',1,type=int),pages))
    start = (page-1)*25
    def page_url(number):
        args=request.args.to_dict();args['page']=number
        return url_for('result_analysis.records',import_job_id=job.id,**args)
    return render_template('result_data/analysis/records.html',job=job,filtered=filtered,
        records=filtered['records'][start:start+25],page=page,pages=pages,start=start,page_url=page_url)
