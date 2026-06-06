from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import current_user

from models import db
import models as models
from final_result_utils import recalculate_lab_result
from lab_excel_utils import generate_lab_template, parse_lab_upload, generate_lab_excel_report
from lab_report_utils import build_lab_report_data, generate_lab_pdf_report
from batch_utils import (
    clean_filter, apply_student_batch_filters, batch_label,
    DIVISION_OPTIONS, BATCH_OPTIONS
)
from academic_utils import (
    get_academic_year_for_semester,
    visible_lab_subjects_query,
)
from stability_utils import update_sgpa_cgpa_safe, flash_sgpa_warnings

lab_bp = Blueprint("lab", __name__, url_prefix="")


def admin_or_teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        if current_user.role not in ["ADMIN", "TEACHER"]:
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def _academic_year_for_semester(semester_id=None, fallback="2024-25"):
    return get_academic_year_for_semester(semester_id, fallback)


def _visible_lab_subjects_query(semester_id=None):
    return visible_lab_subjects_query(semester_id)


def _get_lab_students(subject_code, semester_id, academic_year, division="", batch=""):
    query = (
        models.Enrollment.query
        .filter_by(
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        )
        .join(models.Student, models.Enrollment.prn == models.Student.prn)
    )
    query = apply_student_batch_filters(query, models.Student, division, batch)
    enrollments = query.order_by(models.Student.prn).all()

    rows = []
    for enr in enrollments:
        stu = models.Student.query.get(enr.prn)
        lm = models.LabMarks.query.filter_by(
            prn=enr.prn,
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()
        if lm:
            recalculate_lab_result(lm)

        rows.append({
            "prn": enr.prn,
            "name": stu.name if stu else "",
            "ca1": float(lm.ca1) if lm and getattr(lm, "ca1", None) is not None else None,
            "ca2": float(lm.ca2) if lm and getattr(lm, "ca2", None) is not None else None,
            "internal": float(lm.internal) if lm and lm.internal is not None else None,
            "external": float(lm.external) if lm and lm.external is not None else None,
            "total_marks": float(lm.total_marks) if lm and lm.total_marks is not None else None,
            "grade": lm.grade if lm else None,
            "status": "PASS" if lm and lm.is_passed is True else ("FAIL" if lm and lm.is_passed is False else "PENDING"),
        })
    return rows


@lab_bp.route("/lab", methods=["GET"])
@admin_or_teacher_required
def lab_marks_page():
    semesters = models.Semester.query.order_by(models.Semester.semester_id).all()
    active_sem = models.Semester.query.filter_by(is_active=True).first()

    selected_semester = request.args.get("semester_id", active_sem.semester_id if active_sem else None, type=int)
    subject_code = request.args.get("subject_code", "").strip()
    academic_year = request.args.get("academic_year", "").strip()
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if selected_semester and not academic_year:
        academic_year = _academic_year_for_semester(
            selected_semester,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )

    subjects = _visible_lab_subjects_query(selected_semester).all() if selected_semester else []
    selected_subject = None
    students_data = []

    if subject_code and selected_semester:
        selected_subject = _visible_lab_subjects_query(selected_semester).filter(
            models.Subject.subject_code == subject_code
        ).first()
        if selected_subject:
            students_data = _get_lab_students(subject_code, selected_semester, academic_year, division, batch)

    entered_count = sum(1 for s in students_data if s["total_marks"] is not None)
    pass_count = sum(1 for s in students_data if s["status"] == "PASS")
    fail_count = sum(1 for s in students_data if s["status"] == "FAIL")
    pending_count = len(students_data) - entered_count

    return render_template(
        "lab.html",
        semesters=semesters,
        subjects=subjects,
        selected_semester=selected_semester,
        selected_subject_code=subject_code,
        selected_subject=selected_subject,
        academic_year=academic_year,
        students_data=students_data,
        entered_count=entered_count,
        pass_count=pass_count,
        fail_count=fail_count,
        pending_count=pending_count,
        total_students=len(students_data),
        selected_division=division,
        selected_batch=batch,
        division_options=DIVISION_OPTIONS,
        batch_options=BATCH_OPTIONS,
        batch_label=batch_label(division, batch),
    )


@lab_bp.route("/download-lab-template")
@admin_or_teacher_required
def download_lab_template():
    subject_code = request.args.get("subject_code", "").strip()
    semester_id = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "").strip()
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if not semester_id or not subject_code:
        flash("Please select semester and lab subject first.", "error")
        return redirect(url_for("lab.lab_marks_page"))

    if not academic_year:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    subj = _visible_lab_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not subj:
        flash("Lab/project subject not found.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, division=division, batch=batch))

    students = _get_lab_students(subject_code, semester_id, academic_year, division, batch)
    if not students:
        flash("No students enrolled in this lab/project subject.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    meta = {
        "subject_code": subject_code,
        "subject_name": subj.subject_name,
        "semester_id": semester_id,
        "academic_year": academic_year,
        "division": division,
        "batch": batch,
        "batch_label": batch_label(division, batch),
    }
    buf, filename = generate_lab_template(meta, students)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@lab_bp.route("/upload-lab", methods=["POST"])
@admin_or_teacher_required
def upload_lab():
    file = request.files.get("lab_file")
    subject_code = request.form.get("subject_code", "").strip()
    semester_id = request.form.get("semester_id", type=int)
    academic_year = request.form.get("academic_year", "").strip()
    division = clean_filter(request.form.get("division", ""))
    batch = clean_filter(request.form.get("batch", ""))

    if not semester_id or not subject_code:
        flash("Missing semester or lab subject.", "error")
        return redirect(url_for("lab.lab_marks_page"))

    if not academic_year:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    if not file or not file.filename.endswith(".xlsx"):
        flash("Please upload a valid .xlsx lab marks file.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    subj = _visible_lab_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not subj:
        flash("Lab/project subject not found.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, division=division, batch=batch))

    success, result_data, count = parse_lab_upload(file, subject_code, semester_id, academic_year)
    if not success:
        error_msgs = [f"Row {e['row']}: {e['col']} - {e['msg']}" for e in result_data]
        flash("Upload failed. Errors:<br>" + "<br>".join(error_msgs), "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    saved = 0
    skipped = 0
    affected_prns = []

    for rec in result_data:
        if rec.get("absent"):
            skipped += 1
            continue

        prn = rec["prn"]
        lab_row = models.LabMarks.query.filter_by(
            prn=prn,
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()

        if lab_row is None:
            lab_row = models.LabMarks(
                prn=prn,
                subject_code=subject_code,
                semester_id=semester_id,
                academic_year=academic_year,
            )
            db.session.add(lab_row)

        lab_row.ca1 = float(rec["ca1"])
        lab_row.ca2 = float(rec["ca2"])
        lab_row.internal = float(rec["ca1"] + rec["ca2"])
        lab_row.external = float(rec["external"])
        recalculate_lab_result(lab_row)

        saved += 1
        affected_prns.append(prn)

    db.session.commit()

    sgpa_warnings = []
    for prn in sorted(set(affected_prns)):
        ok, msg = update_sgpa_cgpa_safe(prn, semester_id, academic_year, db, models)
        if not ok:
            sgpa_warnings.append(f"{prn}: {msg}")

    flash(
        f"Lab marks upload complete: {saved} saved, {skipped} skipped blank/pending rows.",
        "success" if not sgpa_warnings else "warning"
    )
    flash_sgpa_warnings(flash, sgpa_warnings)
    return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))


@lab_bp.route("/download-lab-report/excel")
@admin_or_teacher_required
def download_lab_report_excel():
    subject_code = request.args.get("subject_code", "").strip()
    semester_id = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "").strip()
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if not academic_year and semester_id:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    data, meta = build_lab_report_data(subject_code, semester_id, academic_year, division=division, batch=batch)
    if not data:
        flash("No lab report data found.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    buf, filename = generate_lab_excel_report(meta, data)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@lab_bp.route("/download-lab-report/pdf")
@admin_or_teacher_required
def download_lab_report_pdf():
    subject_code = request.args.get("subject_code", "").strip()
    semester_id = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "").strip()
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if not academic_year and semester_id:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    data, meta = build_lab_report_data(subject_code, semester_id, academic_year, division=division, batch=batch)
    if not data:
        flash("No lab report data found.", "error")
        return redirect(url_for("lab.lab_marks_page", semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    buf, filename = generate_lab_pdf_report(meta, data)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)
