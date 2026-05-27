# ─────────────────────────────────────────────────────────────────────────────
#  routes_external.py
#  ECE Student Management System  |  CSMSS Chh. Shahu College of Engineering
# ─────────────────────────────────────────────────────────────────────────────

import io
import os
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify,
    send_file, flash, redirect, url_for, session, current_app
)
from flask_login import current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

from models import db
import models as models
from calculations import validate_external_marks
from external_report_utils import build_external_data
from external_excel_utils import generate_external_excel_report
from final_result_utils import generate_sgpa_cgpa_excel_report
from batch_utils import (
    clean_filter, apply_student_batch_filters, batch_label,
    DIVISION_OPTIONS, BATCH_OPTIONS
)
from academic_utils import (
    get_academic_year_for_semester,
    visible_theory_subjects_query,
    get_semester_row,
)
from stability_utils import (
    safe_int,
    update_sgpa_cgpa_safe,
    flash_sgpa_warnings,
)

external_bp = Blueprint("external", __name__, url_prefix="")


# ── Helpers ───────────────────────────────────────────────────────────────────

def admin_or_teacher_required(f):
    """Allow only logged-in ADMIN/TEACHER users."""
    from functools import wraps

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


def _visible_theory_subjects_query(semester_id=None):
    """Shared database-driven visible theory subject query."""
    return visible_theory_subjects_query(semester_id)


def _academic_year_for_semester(semester_id=None, fallback="2024-25"):
    return get_academic_year_for_semester(semester_id, fallback)


def _get_subject_students(subject_code, semester_id, academic_year, division="", batch=""):
    """Return enrolled students with current external marks using bulk lookups.

    This avoids one Student + TheoryMarks + ExternalMarks query per student.
    """
    student_query = (
        db.session.query(models.Student)
        .join(models.Enrollment, models.Enrollment.prn == models.Student.prn)
        .filter(
            models.Enrollment.subject_code == subject_code,
            models.Enrollment.semester_id == semester_id,
            models.Enrollment.academic_year == academic_year,
        )
    )
    student_query = apply_student_batch_filters(student_query, models.Student, division, batch)
    students = student_query.order_by(models.Student.prn).all()

    prns = [s.prn for s in students]
    if not prns:
        return []

    tm_rows = models.TheoryMarks.query.filter(
        models.TheoryMarks.prn.in_(prns),
        models.TheoryMarks.subject_code == subject_code,
        models.TheoryMarks.semester_id == semester_id,
        models.TheoryMarks.academic_year == academic_year,
    ).all()
    ext_rows = models.ExternalMarks.query.filter(
        models.ExternalMarks.prn.in_(prns),
        models.ExternalMarks.subject_code == subject_code,
        models.ExternalMarks.semester_id == semester_id,
        models.ExternalMarks.academic_year == academic_year,
    ).all()

    tm_lookup = {r.prn: r for r in tm_rows}
    ext_lookup = {r.prn: r for r in ext_rows}

    rows = []
    for student in students:
        tm_row = tm_lookup.get(student.prn)
        ext_row = ext_lookup.get(student.prn)

        ext_val = None
        if tm_row and tm_row.external is not None:
            ext_val = float(tm_row.external)
        elif ext_row and ext_row.external_marks is not None:
            ext_val = float(ext_row.external_marks)

        rows.append({
            "student_id": student.prn,
            "prn": student.prn,
            "name": student.name,
            "external_marks": ext_val,
            "locked": ext_row.locked if ext_row else False,
        })
    return rows


# ── ROUTE: /external  (main page) ────────────────────────────────────────────

@external_bp.route("/external", methods=["GET"])
@admin_or_teacher_required
def external_marks_page():
    semesters = models.Semester.query.order_by(models.Semester.semester_id).all()
    active_sem = models.Semester.query.filter_by(is_active=True).first()

    sem_id = request.args.get("semester_id", active_sem.semester_id if active_sem else None, type=int)
    subject_code = request.args.get("subject_code", "").strip()
    academic_year = request.args.get("academic_year", "").strip()
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if sem_id and not academic_year:
        academic_year = _academic_year_for_semester(
            sem_id,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )
    elif not academic_year:
        academic_year = current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")

    subjects = []
    selected_semester = None
    selected_subject = None
    students_data = []

    # Load selected semester only if semester_id exists
    if sem_id:
        selected_semester = models.Semester.query.filter_by(
            semester_id=sem_id,
            academic_year=academic_year
        ).first()

        if not selected_semester:
            # Fallback: get the first semester matching semester_id to retrieve its correct academic year
            selected_semester = models.Semester.query.filter_by(semester_id=sem_id).first()
            if selected_semester:
                academic_year = selected_semester.academic_year

        if selected_semester:
            subjects = _visible_theory_subjects_query(sem_id).all()

    # Load selected subject only if subject_code exists
    if subject_code and sem_id:
        selected_subject = _visible_theory_subjects_query(sem_id).filter(
            models.Subject.subject_code == subject_code
        ).first()
        if selected_subject:
            students_data = _get_subject_students(subject_code, sem_id, academic_year, division, batch)

    # Dashboard stats for this subject
    submitted_count = sum(1 for s in students_data if s["external_marks"] is not None)
    locked_count    = sum(1 for s in students_data if s["locked"])
    pass_count      = sum(
        1 for s in students_data
        if s["external_marks"] is not None and float(s["external_marks"]) >= 20
    )
    pass_pct = round(pass_count / len(students_data) * 100, 1) if students_data else 0

    return render_template(
        "external.html",
        semesters=semesters,
        subjects=subjects,
        students_data=students_data,
        selected_sem_id=sem_id,
        selected_subject_code=subject_code,
        selected_subject=selected_subject,
        selected_semester=selected_semester,
        academic_year=academic_year,
        submitted_count=submitted_count,
        locked_count=locked_count,
        pass_pct=pass_pct,
        total_students=len(students_data),
        selected_division=division,
        selected_batch=batch,
        division_options=DIVISION_OPTIONS,
        batch_options=BATCH_OPTIONS,
        batch_label=batch_label(division, batch),
    )


# ── ROUTE: /external/save  (AJAX POST — save draft) ──────────────────────────

@external_bp.route("/external/save", methods=["POST"])
@admin_or_teacher_required
def save_external_marks():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data received"}), 400

    subject_code  = data.get("subject_code")
    semester_id   = safe_int(data.get("semester_id"), default=None, minimum=1, maximum=8)
    academic_year = str(data.get("academic_year") or "").strip()
    marks_list    = data.get("marks", [])

    if not all([subject_code, semester_id, academic_year]):
        return jsonify({"success": False, "error": "Missing subject/semester/year"}), 400

    errors = []
    saved  = 0

    for item in marks_list:
        student_id = item.get("student_id")
        ext_val    = item.get("external_marks")

        # Skip blank entries (save draft allows partial)
        if ext_val is None or str(ext_val).strip() == "":
            continue

        valid, err = validate_external_marks(ext_val, "THEORY")
        if not valid:
            student = models.Student.query.get(student_id)
            errors.append(f"{student.prn if student else student_id}: {err}")
            continue

        # Upsert
        row = models.ExternalMarks.query.filter_by(
            prn=student_id,
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()

        if row is None:
            row = models.ExternalMarks(
                prn=student_id,
                subject_code=subject_code,
                semester_id=semester_id,
                academic_year=academic_year,
            )
            db.session.add(row)

        if row.locked:
            student = models.Student.query.get(student_id)
            errors.append(f"{student.prn}: record is locked")
            continue

        row.external_marks = float(ext_val)
        row.updated_at     = datetime.utcnow()
        saved += 1

    db.session.commit()

    return jsonify({
        "success": True,
        "saved":   saved,
        "errors":  errors,
        "message": f"Saved {saved} record(s)." + (f" {len(errors)} error(s)." if errors else ""),
    })


# ── ROUTE: /external/lock  (AJAX POST) ───────────────────────────────────────

@external_bp.route("/external/lock", methods=["POST"])
@admin_or_teacher_required
def lock_external_subject():
    """Lock all external marks entries for a subject."""
    data = request.get_json() or {}
    subject_code  = data.get("subject_code")
    semester_id   = safe_int(data.get("semester_id"), default=None, minimum=1, maximum=8)
    academic_year = str(data.get("academic_year") or "").strip()

    if not all([subject_code, semester_id, academic_year]):
        return jsonify({"success": False, "error": "Missing subject/semester/year"}), 400

    rows = models.ExternalMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year,
    ).all()

    for row in rows:
        row.locked = True
    db.session.commit()

    # Trigger SGPA/CGPA recalculation for all students in this subject.
    # Do not silently ignore failures; return warnings to the page/JS caller.
    student_ids = list({r.prn for r in rows})
    warnings = []
    for sid in student_ids:
        ok, msg = update_sgpa_cgpa_safe(sid, semester_id, academic_year, db, models)
        if not ok:
            warnings.append(f"{sid}: {msg}")

    return jsonify({
        "success": True,
        "locked_count": len(rows),
        "warnings": warnings,
        "warning_count": len(warnings),
    })


# ── ROUTE: /upload-external  (POST — Excel upload) ───────────────────────────

@external_bp.route("/upload-external", methods=["GET", "POST"])
@admin_or_teacher_required
def upload_external():
    from external_excel_utils import parse_external_upload
    if request.method == "GET":
        semesters = models.Semester.query.order_by(models.Semester.semester_id).all()
        subjects  = _visible_theory_subjects_query().all()
        return render_template("upload_external.html", semesters=semesters, subjects=subjects)

    file          = request.files.get("file")
    subject_code  = request.form.get("subject_code", "").strip()
    semester_id   = request.form.get("semester_id", type=int)
    academic_year = request.form.get("academic_year", "").strip()

    if not semester_id:
        flash("Please select a semester.", "error")
        return redirect(url_for("external.upload_external"))

    if not academic_year:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    if not file or not file.filename.endswith(".xlsx"):
        flash("Please upload a valid .xlsx file.", "error")
        return redirect(url_for("external.upload_external"))

    subj = _visible_theory_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not subj:
        flash("Subject not found.", "error")
        return redirect(url_for("external.upload_external"))

    success, result_data, count = parse_external_upload(
        file, subject_code, semester_id, academic_year
    )

    if not success:
        error_msgs = [f"Row {e['row']}: {e['col']} — {e['msg']}" for e in result_data]
        flash('Upload failed. Errors:<br>' + '<br>'.join(error_msgs), 'error')
        return redirect(url_for("external.external_marks_page",
                                semester_id=semester_id, subject_code=subject_code,
                                academic_year=academic_year))

    errors  = []
    saved   = 0
    skipped = 0
    affected_prns = []

    for rec in result_data:
        prn = rec["prn"]
        ext_val = rec["external_marks"]
        is_absent = rec.get("absent", False)

        student = models.Student.query.filter_by(prn=prn).first()
        if not student:
            errors.append(f"PRN '{prn}' not found in database")
            continue

        if is_absent or ext_val is None:
            skipped += 1
            continue

        # Check locked
        ext_row = models.ExternalMarks.query.filter_by(
            prn=student.prn,
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()

        if ext_row and ext_row.locked:
            errors.append(f"PRN ({prn}): record is locked — cannot overwrite")
            continue

        existing = models.TheoryMarks.query.filter_by(
            prn=student.prn,
            subject_code=subject_code,
            semester_id=semester_id,
            academic_year=academic_year
        ).first()

        # Phase C cleanup:
        # External upload should not create empty TheoryMarks rows when internal
        # marks have not been uploaded yet. Keep the official external value in
        # ExternalMarks. If a TheoryMarks row already exists, sync/recalculate it.
        if existing is not None:
            existing.external = float(ext_val)
            from final_result_utils import recalculate_theory_result
            recalculate_theory_result(existing)

        # Ensure ExternalMarks table is also updated to keep lock status and dashboard stats working
        if ext_row is None:
            ext_row = models.ExternalMarks(
                prn=student.prn,
                subject_code=subject_code,
                semester_id=semester_id,
                academic_year=academic_year,
            )
            db.session.add(ext_row)
        ext_row.external_marks = float(ext_val)
        ext_row.updated_at = datetime.utcnow()

        affected_prns.append(student.prn)
        saved += 1

    db.session.commit()

    sgpa_warnings = []
    for prn in sorted(set(affected_prns)):
        ok, msg = update_sgpa_cgpa_safe(prn, semester_id, academic_year, db, models)
        if not ok:
            sgpa_warnings.append(f"{prn}: {msg}")

    flash(f"Upload complete: {saved} saved, {skipped} skipped (blank), {len(errors)} error(s).", 
          "success" if not errors and not sgpa_warnings else "warning")
    
    if errors:
        session["upload_errors"] = errors[:50]  # store up to 50 errors in session
        shown_errors = "<br>".join(errors[:10])
        extra = len(errors) - min(len(errors), 10)
        if extra > 0:
            shown_errors += f"<br>...and {extra} more error(s)."
        flash("Some rows were not saved:<br>" + shown_errors, "warning")

    flash_sgpa_warnings(flash, sgpa_warnings)

    return redirect(url_for("external.external_marks_page",
                            semester_id=semester_id, subject_code=subject_code,
                            academic_year=academic_year))


# ── ROUTE: /download-external-template ───────────────────────────────────────

@external_bp.route("/download-external-template")
@admin_or_teacher_required
def download_external_template():
    from external_excel_utils import generate_external_template

    subject_code  = request.args.get("subject_code")
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    subj = _visible_theory_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not academic_year:
        academic_year = _academic_year_for_semester(
            semester_id,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )
    sem = get_semester_row(semester_id, academic_year)

    if not subj or not sem:
        flash("Invalid subject or semester.", "error")
        return redirect(url_for("external.external_marks_page"))

    students_data = _get_subject_students(subject_code, semester_id, academic_year, division, batch)

    meta = {
        "subject_code": subject_code,
        "subject_name": subj.subject_name,
        "semester_id": semester_id,
        "academic_year": academic_year,
        "division": division,
        "batch": batch,
        "batch_label": batch_label(division, batch),
    }

    buf, filename = generate_external_template(meta, students_data)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# ── ROUTE: /download-external-report/excel ───────────────────────────────────

@external_bp.route("/download-external-report/excel")
@admin_or_teacher_required
def download_external_report_excel():
    subject_code  = request.args.get("subject_code")
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    if not academic_year:
        academic_year = _academic_year_for_semester(
            semester_id,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )

    subj = _visible_theory_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not subj:
        flash("Subject not found.", "error")
        return redirect(url_for("external.external_marks_page"))

    data, meta = build_external_data(subject_code, semester_id, academic_year, division=division, batch=batch)
    if not data:
        flash("No data found for the report.", "error")
        return redirect(url_for("external.external_marks_page"))

    buf, filename = generate_external_excel_report(meta, data)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ── ROUTE: /download-external-report/pdf ─────────────────────────────────────

@external_bp.route("/download-external-report/pdf")
@admin_or_teacher_required
def download_external_report_pdf():
    """External marks PDF report with common logo/college header."""
    from reportlab.platypus import Image

    subject_code  = request.args.get("subject_code")
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")
    division = clean_filter(request.args.get("division", ""))
    batch = clean_filter(request.args.get("batch", ""))

    subj = _visible_theory_subjects_query(semester_id).filter(models.Subject.subject_code == subject_code).first()
    if not subj:
        flash("Subject not found.", "error")
        return redirect(url_for("external.external_marks_page"))

    if not academic_year:
        academic_year = _academic_year_for_semester(semester_id, current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25"))

    data, meta = build_external_data(subject_code, semester_id, academic_year, division=division, batch=batch)
    if not data:
        flash("No data found for the report.", "error")
        return redirect(url_for("external.external_marks_page"))

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    elements = []

    page_width = landscape(A4)[0] - 2.4 * cm
    left_logo_path = os.path.join(current_app.root_path, "static", "images", "left_logo.jpg")
    right_logo_path = os.path.join(current_app.root_path, "static", "images", "right_logo.png")

    BLACK = colors.black
    GREEN = colors.HexColor("#D5F5E3")
    RED = colors.HexColor("#FADBD8")
    GREY = colors.HexColor("#F2F3F4")
    HEADER = colors.HexColor("#D9EAF7")

    title_style = ParagraphStyle(
        "college_header",
        fontSize=13,
        fontName="Times-Bold",
        textColor=BLACK,
        alignment=1,
        leading=17,
    )
    small_style = ParagraphStyle(
        "small",
        fontSize=8,
        fontName="Times-Roman",
        textColor=BLACK,
        alignment=1,
        leading=10,
    )

    left_logo = Image(left_logo_path, width=55, height=55) if os.path.exists(left_logo_path) else ""
    right_logo = Image(right_logo_path, width=55, height=55) if os.path.exists(right_logo_path) else ""

    header = Table([
        [
            left_logo,
            Paragraph(
                "Chhatrapati Shahu Maharaj Shikshan Sanstha's<br/>"
                "CSMSS Chh. Shahu College of Engineering<br/>"
                "Kanchanwadi, Chhatrapati Sambhajinagar – 431011<br/>"
                "Department of Electronics and Computer Engineering",
                title_style,
            ),
            right_logo,
        ]
    ], colWidths=[2 * cm, page_width - 4 * cm, 2 * cm])
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 8))

    report_title = Table([[Paragraph("External Marks Report", title_style)]], colWidths=[page_width])
    report_title.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(report_title)

    meta_table = Table([
        [
            Paragraph(f"Subject Code : {subj.subject_code}", small_style),
            Paragraph(f"Subject Name : {subj.subject_name}", small_style),
            Paragraph(f"Semester : {semester_id}", small_style),
            Paragraph(f"A.Y. : {academic_year}", small_style),
            Paragraph(f"Date : {datetime.now().strftime('%d %b %Y')}", small_style),
        ]
    ], colWidths=[page_width * 0.16, page_width * 0.34, page_width * 0.14, page_width * 0.16, page_width * 0.20])
    meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8))

    table_data = [[
        "SR", "PRN", "Student Name", "Internal (/40)", "External (/60)",
        "Total (/100)", "Grade", "GP", "Result"
    ]]

    marks_list = []
    pass_c = fail_c = pending_c = 0

    for i, s in enumerate(data, 1):
        ext = s["external"]
        internal = s["internal"]
        total = s["total"]
        status = s["status"]

        if ext is not None:
            marks_list.append(ext)
        if status == "PASS":
            pass_c += 1
        elif status == "FAIL":
            fail_c += 1
        else:
            pending_c += 1

        table_data.append([
            str(i),
            s["prn"],
            s["name"],
            str(internal) if internal is not None else "—",
            str(ext) if ext is not None else "—",
            str(total) if total is not None else "—",
            s["grade"] or "—",
            str(s["grade_point"]) if s["grade_point"] is not None else "—",
            status,
        ])

    tbl = Table(
        table_data,
        colWidths=[1.0*cm, 3.4*cm, 6.3*cm, 2.3*cm, 2.3*cm, 2.3*cm, 1.7*cm, 1.7*cm, 2.1*cm],
        repeatRows=1,
    )
    tbl_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "LEFT"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])

    for i, s in enumerate(data, 1):
        status = s["status"]
        if status == "PASS":
            tbl_style.add("BACKGROUND", (8, i), (8, i), GREEN)
        elif status == "FAIL":
            tbl_style.add("BACKGROUND", (8, i), (8, i), RED)
        else:
            tbl_style.add("BACKGROUND", (8, i), (8, i), GREY)

    tbl.setStyle(tbl_style)
    elements.append(tbl)
    elements.append(Spacer(1, 14))

    avg_marks = round(sum(marks_list)/len(marks_list), 2) if marks_list else 0
    pass_pct = round(pass_c/len(marks_list)*100, 1) if marks_list else 0

    summary_data = [
        ["Total Students", "Entered", "Pass", "Fail", "Pending", "Pass%", "Highest", "Lowest", "Average"],
        [str(len(data)), str(len(marks_list)), str(pass_c), str(fail_c), str(pending_c), f"{pass_pct}%",
         str(max(marks_list)) if marks_list else "—",
         str(min(marks_list)) if marks_list else "—",
         str(avg_marks)],
    ]
    sum_tbl = Table(summary_data, colWidths=[page_width / 9] * 9)
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(sum_tbl)
    elements.append(Spacer(1, 30))

    sig_tbl = Table([["Subject Teacher", "HOD", "Principal"]], colWidths=[page_width/3]*3)
    sig_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, -1), "Times-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 30),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, BLACK),
    ]))
    elements.append(sig_tbl)

    doc.build(elements)
    output.seek(0)

    filename = f"External_Report_{subject_code}_Sem{semester_id}.pdf"
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)


# ── ROUTE: /external/stats  (JSON — dashboard cards) ─────────────────────────

@external_bp.route("/external/stats")
@admin_or_teacher_required
def external_stats():
    """JSON endpoint for dashboard cards."""
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")

    if not semester_id:
        active = models.Semester.query.filter_by(is_active=True).first()
        semester_id   = active.semester_id   if active else 1
        academic_year = active.academic_year if active else ""

    if semester_id and not academic_year:
        academic_year = _academic_year_for_semester(
            semester_id,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )

    theory_subjects = _visible_theory_subjects_query(semester_id).all()

    total_subjects  = len(theory_subjects)
    submitted = 0
    pending   = 0
    pass_count = 0
    total_entered = 0

    for subj in theory_subjects:
        rows = models.ExternalMarks.query.filter_by(
            subject_code=subj.subject_code,
            semester_id=semester_id,
            academic_year=academic_year,
        ).all()
        if rows:
            submitted += 1
            for r in rows:
                if r.external_marks is not None:
                    total_entered += 1
                    if float(r.external_marks) >= 20:
                        pass_count += 1
        else:
            pending += 1

    pass_pct = round(pass_count / total_entered * 100, 1) if total_entered else 0

    return jsonify({
        "external_submitted": submitted,
        "external_pending":   pending,
        "external_pass_pct":  pass_pct,
        "total_subjects":     total_subjects,
    })


@external_bp.route("/download-sgpa-cgpa/excel")
@admin_or_teacher_required
def download_sgpa_cgpa_excel():
    semester_id = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "").strip()

    if not semester_id:
        flash("Please select semester first.", "error")
        return redirect(url_for("external.external_marks_page"))

    if not academic_year:
        academic_year = _academic_year_for_semester(
            semester_id,
            current_app.config.get("CURRENT_ACADEMIC_YEAR", "2024-25")
        )

    output, filename = generate_sgpa_cgpa_excel_report(
        semester_id=semester_id,
        academic_year=academic_year
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
