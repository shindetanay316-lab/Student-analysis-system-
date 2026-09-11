from io import BytesIO

from flask import Blueprint, flash, redirect, send_file, url_for
from flask_login import login_required

from models import db
from ..models import ImportJob
from ..services.export_service import (
    ExportArtifact,
    build_csv_export,
    build_excel_export,
    build_json_export,
)


exports_bp = Blueprint(
    "result_exports", __name__, url_prefix="/result-data/exports"
)


@exports_bp.get("/imports/<int:import_job_id>/results.xlsx")
@login_required
def excel(import_job_id: int):
    return _download(import_job_id, build_excel_export)


@exports_bp.get("/imports/<int:import_job_id>/results.csv")
@login_required
def csv(import_job_id: int):
    return _download(import_job_id, build_csv_export)


@exports_bp.get("/imports/<int:import_job_id>/results.json")
@login_required
def json(import_job_id: int):
    return _download(import_job_id, build_json_export)


def _download(import_job_id: int, builder):
    job = db.get_or_404(ImportJob, import_job_id)
    try:
        artifact: ExportArtifact = builder(job)
    except ValueError as error:
        flash(str(error), "warning")
        return redirect(url_for("result_imports.detail", import_job_id=job.id))

    return send_file(
        BytesIO(artifact.data),
        mimetype=artifact.mimetype,
        as_attachment=True,
        download_name=artifact.filename,
        max_age=0,
    )
