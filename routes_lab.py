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
    DIVISION_OPTIONS, BATCH_OPTIONS, term_filter_options
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
        db.session.query(models.Student)
        .join(models.Enrollment, models.Enrollment.prn == models.Student.prn)
        .filter(
            models.Enrollment.subject_code == subject_code,
            models.Enrollment.semester_id == semester_id,
            models.Enrollment.academic_year == academic_year,
        )
    )
    query = apply_student_batch_filters(query, models.Student, division, batch, semester_id, academic_year)
    students = query.order_by(models.Student.prn).all()
    from term_services import students_in_term
    students=students_in_term(students,semester_id,academic_year)

    prns = [student.prn for student in students]
    marks = models.LabMarks.query.filter(
        models.LabMarks.prn.in_(prns),
        models.LabMarks.subject_code == subject_code,
        models.LabMarks.semester_id == semester_id,
        models.LabMarks.academic_year == academic_year,
    ).all() if prns else []
    marks_by_prn = {row.prn: row for row in marks}

    rows = []
    for student in students:
        lm = marks_by_prn.get(student.prn)
        if lm:
            recalculate_lab_result(lm)

        rows.append({
            'roll_number': student.roll_number,
            "prn": student.prn,
            "name": student.name,
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
        division_options=term_filter_options(selected_semester,academic_year)[0],
        batch_options=term_filter_options(selected_semester,academic_year)[1],
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
    from routes_coursework import preview_upload
    return preview_upload('LAB')


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
