from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import db
from ..forms import PDFUploadForm
from ..models import DataCorrection, ImportJob, ReportStudent
from ..services.import_service import (
    DuplicateImportError,
    InvalidPDFError,
    create_import_job,
    delete_import_job,
)
from ..services.extraction_service import ExtractionFailedError, extract_import_job
from ..services.review_service import (
    ReviewError,
    apply_student_corrections,
    confirm_import,
)
from ..services.validation_service import validate_report


imports_bp = Blueprint(
    "result_imports", __name__, url_prefix="/result-data/imports"
)


@imports_bp.get("/")
@login_required
def history():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().upper()
    page = request.args.get("page", 1, type=int)
    statement = db.select(ImportJob).order_by(ImportJob.created_at.desc())
    if query:
        statement = statement.where(ImportJob.original_filename.ilike(f"%{query}%"))
    allowed_statuses = {
        ImportJob.STATUS_UPLOADED,
        ImportJob.STATUS_EXTRACTING,
        ImportJob.STATUS_REVIEW_REQUIRED,
        ImportJob.STATUS_READY,
        ImportJob.STATUS_FAILED,
    }
    if status in allowed_statuses:
        statement = statement.where(ImportJob.status == status)
    pagination = db.paginate(statement, page=max(page, 1), per_page=20, error_out=False)
    return render_template(
        "result_data/imports/history.html",
        pagination=pagination,
        query=query,
        selected_status=status,
    )


@imports_bp.route("/new", methods=["GET", "POST"])
@login_required
def upload():
    form = PDFUploadForm()
    if form.validate_on_submit():
        try:
            job = create_import_job(
                form.pdf_file.data, current_app.config["RESULT_DATA_UPLOAD_FOLDER"]
            )
        except InvalidPDFError as error:
            form.pdf_file.errors.append(str(error))
        except DuplicateImportError as error:
            flash(str(error), "warning")
            return redirect(url_for("result_imports.detail", import_job_id=error.import_job_id))
        else:
            try:
                extract_import_job(job, current_app.config["UPLOAD_FOLDER"])
            except ExtractionFailedError as error:
                flash(f"PDF uploaded, but extraction failed: {error}", "danger")
            else:
                flash("PDF uploaded and extracted successfully.", "success")
            return redirect(url_for("result_imports.detail", import_job_id=job.id))

    return render_template("result_data/imports/upload.html", form=form)


@imports_bp.get("/<int:import_job_id>")
@login_required
def detail(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    return render_template("result_data/imports/detail.html", job=job)


@imports_bp.post("/<int:import_job_id>/delete")
@login_required
def delete(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    confirmation = request.form.get("confirm_import_id", "").strip()
    if confirmation != str(job.id):
        flash(f"Enter {job.id} exactly to confirm permanent deletion.", "danger")
        return redirect(url_for("result_imports.detail", import_job_id=job.id))

    deleted_job_id = job.id
    try:
        source_deleted = delete_import_job(
            job, current_app.config["RESULT_DATA_UPLOAD_FOLDER"]
        )
    except InvalidPDFError as error:
        db.session.rollback()
        current_app.logger.error(
            "Refused unsafe source path while deleting import #%s.", deleted_job_id
        )
        flash(str(error), "danger")
        return redirect(url_for("result_imports.detail", import_job_id=deleted_job_id))
    if source_deleted:
        flash(f"Import #{deleted_job_id} and its source PDF were deleted.", "success")
    else:
        current_app.logger.warning(
            "Import #%s was deleted, but its source PDF could not be removed.",
            deleted_job_id,
        )
        flash(
            f"Import #{deleted_job_id} was deleted, but the source PDF requires "
            "manual cleanup from the upload directory.",
            "warning",
        )
    return redirect(url_for("result_imports.history"))


@imports_bp.get("/<int:import_job_id>/students")
@login_required
def students(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    if job.report is None:
        flash("Extract the PDF before reviewing students.", "warning")
        return redirect(url_for("result_imports.detail", import_job_id=job.id))

    query = request.args.get("q", "").strip()
    result_status = request.args.get("result_status", "").strip().upper()
    validation_status = request.args.get("validation_status", "").strip().upper()
    page = request.args.get("page", 1, type=int)
    statement = (
        db.select(ReportStudent)
        .where(ReportStudent.report_id == job.report.id)
        .order_by(ReportStudent.seat_number)
    )
    if query:
        statement = statement.where(
            or_(
                ReportStudent.seat_number.ilike(f"%{query}%"),
                ReportStudent.name.ilike(f"%{query}%"),
            )
        )
    if result_status in {"PASS", "FAIL", "CANCEL"}:
        statement = statement.where(ReportStudent.result_status == result_status)
    if validation_status in {"VALID", "WARNING", "ERROR", "SKIPPED"}:
        statement = statement.where(
            ReportStudent.validation_status == validation_status
        )
    pagination = db.paginate(statement, page=max(page, 1), per_page=25, error_out=False)
    return render_template(
        "result_data/imports/students.html",
        job=job,
        pagination=pagination,
        query=query,
        selected_result_status=result_status,
        selected_validation_status=validation_status,
    )


@imports_bp.get("/<int:import_job_id>/students/<int:student_id>")
@login_required
def student_detail(import_job_id: int, student_id: int):
    job, student = _job_and_student(import_job_id, student_id)
    previous_student = db.session.scalar(
        db.select(ReportStudent)
        .where(
            ReportStudent.report_id == student.report_id,
            ReportStudent.id < student.id,
        )
        .order_by(ReportStudent.id.desc())
        .limit(1)
    )
    next_student = db.session.scalar(
        db.select(ReportStudent)
        .where(
            ReportStudent.report_id == student.report_id,
            ReportStudent.id > student.id,
        )
        .order_by(ReportStudent.id.asc())
        .limit(1)
    )
    corrections = db.session.scalars(
        db.select(DataCorrection)
        .where(DataCorrection.student_id == student.id)
        .order_by(DataCorrection.created_at.desc(), DataCorrection.id.desc())
    ).all()
    return render_template(
        "result_data/imports/student_detail.html",
        job=job,
        student=student,
        previous_student=previous_student,
        next_student=next_student,
        corrections=corrections,
    )


@imports_bp.route(
    "/<int:import_job_id>/students/<int:student_id>/edit", methods=["GET", "POST"]
)
@login_required
def edit_student(import_job_id: int, student_id: int):
    job, student = _job_and_student(import_job_id, student_id)
    if request.method == "POST":
        try:
            summary = apply_student_corrections(
                job, student, request.form, current_user
            )
            db.session.commit()
        except ReviewError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash(
                f"Saved {summary.changed_fields} corrected fields. Validation now "
                f"has {summary.validation.error_count} errors and "
                f"{summary.validation.warning_count} warnings.",
                "success" if summary.validation.error_count == 0 else "warning",
            )
            return redirect(
                url_for(
                    "result_imports.student_detail",
                    import_job_id=job.id,
                    student_id=student.id,
                )
            )
    return render_template(
        "result_data/imports/student_edit.html", job=job, student=student
    )


@imports_bp.post("/<int:import_job_id>/confirm")
@login_required
def confirm(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    try:
        confirm_import(
            job,
            current_user,
            acknowledge_warnings=request.form.get("acknowledge_warnings") == "1",
            notes=request.form.get("confirmation_notes"),
        )
        db.session.commit()
    except ReviewError as error:
        db.session.rollback()
        flash(str(error), "danger")
    else:
        flash("Import confirmed. The validated dataset is ready to use.", "success")
    return redirect(url_for("result_imports.detail", import_job_id=job.id))


@imports_bp.post("/<int:import_job_id>/extract")
@login_required
def extract(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    try:
        extract_import_job(job, current_app.config["RESULT_DATA_UPLOAD_FOLDER"])
    except ExtractionFailedError as error:
        flash(f"Extraction failed: {error}", "danger")
    else:
        flash(
            "PDF extracted and validated successfully. The records are ready for review.",
            "success",
        )
    return redirect(url_for("result_imports.detail", import_job_id=job.id))


@imports_bp.post("/<int:import_job_id>/validate")
@login_required
def validate(import_job_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    if job.report is None:
        flash("Extract the PDF before running validation.", "warning")
        return redirect(url_for("result_imports.detail", import_job_id=job.id))

    summary = validate_report(job.report)
    if summary.error_count and job.status == ImportJob.STATUS_READY:
        job.status = ImportJob.STATUS_REVIEW_REQUIRED
        job.confirmed_at = None
        job.confirmed_by_id = None
        job.confirmation_notes = None
    db.session.commit()
    flash(
        f"Validation complete: {summary.error_count} errors and "
        f"{summary.warning_count} warnings.",
        "success" if summary.error_count == 0 else "warning",
    )
    return redirect(url_for("result_imports.detail", import_job_id=job.id))


def _job_and_student(import_job_id: int, student_id: int):
    job = db.get_or_404(ImportJob, import_job_id)
    if job.report is None:
        abort(404)
    student = db.session.get(ReportStudent, student_id)
    if student is None or student.report_id != job.report.id:
        abort(404)
    return job, student
