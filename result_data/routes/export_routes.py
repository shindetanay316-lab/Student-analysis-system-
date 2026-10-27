from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, send_file, url_for
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


@exports_bp.get('/imports/<int:import_job_id>/results.pdf')
@login_required
def pdf(import_job_id):
    from ..services.export_service import build_pdf_export
    return _download(import_job_id, build_pdf_export)


@exports_bp.get('/imports/<int:import_job_id>/details.xlsx')
@login_required
def detailed_excel(import_job_id):
    from ..services.export_service import build_detailed_excel_export
    return _download(import_job_id, build_detailed_excel_export)


@exports_bp.route('/imports/<int:import_job_id>/report-settings', methods=['GET','POST'])
@login_required
def settings(import_job_id):
    from datetime import date
    from flask import request, abort
    from ..models import ResultReportSettings
    from ..services.faculty_report_service import report_options, SIGNATURES
    job = db.get_or_404(ImportJob,import_job_id)
    if job.report is None:
        return redirect(url_for('result_imports.detail',import_job_id=job.id))
    if request.method == 'POST':
        raw = request.form.get('report_date','')
        try: date.fromisoformat(raw)
        except ValueError: abort(400,'Enter a valid report date.')
        def field(name,maximum):
            value=request.form.get(name,'').strip()
            if len(value)>maximum: abort(400,'A report setting is too long.')
            return value
        data={'report_date':raw,
            'signatures':{key:field('signature_'+key,150) for key,_ in SIGNATURES},
            'faculty':{s.subject_code:field('faculty_'+str(s.id),200) for s in job.report.subjects}}
        if job.report_settings is None:
            job.report_settings=ResultReportSettings(data=data)
        else: job.report_settings.data=data
        db.session.commit()
        flash('Report settings saved. PDF and Excel will use these names.','success')
        return redirect(url_for('result_exports.settings',import_job_id=job.id))
    return render_template('result_data/exports_settings.html',job=job,options=report_options(job),signatures=SIGNATURES)
