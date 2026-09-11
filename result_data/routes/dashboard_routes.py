from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from models import db
from ..models import ImportJob, ValidationIssue


dashboard_bp = Blueprint("result_data", __name__, url_prefix="/result-data")


@dashboard_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(status="unavailable", database="error"), 503
    return jsonify(status="ok", database="ok"), 200


@dashboard_bp.get("/")
@login_required
def index():
    total_imports = db.session.scalar(
        db.select(func.count()).select_from(ImportJob)
    ) or 0
    uploaded = db.session.scalar(
        db.select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.status == ImportJob.STATUS_UPLOADED)
    ) or 0
    ready = db.session.scalar(
        db.select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.status == ImportJob.STATUS_READY)
    ) or 0
    review_required = db.session.scalar(
        db.select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.status == ImportJob.STATUS_REVIEW_REQUIRED)
    ) or 0
    failed = db.session.scalar(
        db.select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.status == ImportJob.STATUS_FAILED)
    ) or 0
    validation_errors = db.session.scalar(
        db.select(func.count())
        .select_from(ValidationIssue)
        .where(ValidationIssue.severity == ValidationIssue.SEVERITY_ERROR)
    ) or 0
    recent_imports = db.session.scalars(
        db.select(ImportJob).order_by(ImportJob.created_at.desc()).limit(10)
    ).all()

    return render_template(
        "result_data/dashboard.html",
        total_imports=total_imports,
        uploaded=uploaded,
        review_required=review_required,
        ready=ready,
        failed=failed,
        validation_errors=validation_errors,
        recent_imports=recent_imports,
    )
