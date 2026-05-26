# ─────────────────────────────────────────────────────────────────────────────
#  routes_external.py
#  ECE Student Management System  |  CSMSS Chh. Shahu College of Engineering
# ─────────────────────────────────────────────────────────────────────────────

import io
import os
from datetime import datetime

import pandas as pd
from flask import (
    Blueprint, render_template, request, jsonify,
    send_file, flash, redirect, url_for, session, current_app
)
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers as xl_numbers
)
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)

from models import db
import models as models
from calculations import (
    compute_final_result,
    validate_external_marks,
    update_sgpa_cgpa_for_student
)
from external_report_utils import build_external_data
from external_excel_utils import generate_external_excel_report
from final_result_utils import generate_sgpa_cgpa_excel_report

external_bp = Blueprint("external", __name__, url_prefix="")


# ── Helpers ───────────────────────────────────────────────────────────────────

def admin_or_teacher_required(f):
    """Decorator — both ADMIN and TEACHER can access external marks."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


def _get_subject_students(subject_code, semester_id, academic_year):
    """Return list of enrolled students with their current external marks."""
    enrollments = (
        models.Enrollment.query
        .filter_by(subject_code=subject_code, semester_id=semester_id,
                   academic_year=academic_year)
        .join(models.Student, models.Enrollment.prn == models.Student.prn)
        .order_by(models.Student.prn)
        .all()
    )

    rows = []
    for enr in enrollments:
        student = models.Student.query.get(enr.prn)
        tm_row = models.TheoryMarks.query.filter_by(
            prn=enr.prn,
            subject_code=subject_code,
            academic_year=academic_year,
        ).first()
        ext_row = models.ExternalMarks.query.filter_by(
            prn=enr.prn,
            subject_code=subject_code,
            academic_year=academic_year,
        ).first()

        ext_val = None
        if tm_row and tm_row.external is not None:
            ext_val = float(tm_row.external)
        elif ext_row and ext_row.external_marks is not None:
            ext_val = float(ext_row.external_marks)

        rows.append({
            "student_id":    enr.prn,
            "prn":           enr.prn,
            "name":          student.name if student else "",
            "external_marks": ext_val,
            "locked":        ext_row.locked if ext_row else False,
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

    if not academic_year:
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
            subjects = (
                models.Subject.query
                .filter_by(semester_id=sem_id, subject_type="THEORY", is_audit=False)
                .order_by(models.Subject.subject_code)
                .all()
            )

    # Load selected subject only if subject_code exists
    if subject_code and sem_id:
        selected_subject = models.Subject.query.filter_by(
            subject_code=subject_code,
            semester_id=sem_id
        ).first()
        if selected_subject:
            students_data = _get_subject_students(subject_code, sem_id, academic_year)

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
    )


# ── ROUTE: /external/save  (AJAX POST — save draft) ──────────────────────────

@external_bp.route("/external/save", methods=["POST"])
@admin_or_teacher_required
def save_external_marks():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data received"}), 400

    subject_code  = data.get("subject_code")
    semester_id   = data.get("semester_id")
    academic_year = data.get("academic_year")
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
def lock_external_subject():
    """Lock all external marks entries for a subject."""
    data = request.get_json()
    subject_code  = data.get("subject_code")
    semester_id   = data.get("semester_id")
    academic_year = data.get("academic_year")

    rows = models.ExternalMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year,
    ).all()

    for row in rows:
        row.locked = True
    db.session.commit()

    # Trigger SGPA/CGPA recalculation for all students in this subject
    student_ids = list({r.prn for r in rows})
    for sid in student_ids:
        try:
            update_sgpa_cgpa_for_student(sid, semester_id, academic_year, db, models)
        except Exception as e:
            pass  # log but don't abort

    return jsonify({"success": True, "locked_count": len(rows)})


# ── ROUTE: /upload-external  (POST — Excel upload) ───────────────────────────

@external_bp.route("/upload-external", methods=["GET", "POST"])
@admin_or_teacher_required
def upload_external():
    from external_excel_utils import parse_external_upload
    if request.method == "GET":
        semesters = models.Semester.query.all()
        subjects  = models.Subject.query.filter_by(subject_type="THEORY", is_audit=False).all()
        return render_template("upload_external.html", semesters=semesters, subjects=subjects)

    file         = request.files.get("file")
    subject_code = request.form.get("subject_code")
    semester_id  = int(request.form.get("semester_id"))
    academic_year = request.form.get("academic_year")

    if not file or not file.filename.endswith(".xlsx"):
        flash("Please upload a valid .xlsx file.", "error")
        return redirect(url_for("external.upload_external"))

    subj = models.Subject.query.filter_by(subject_code=subject_code).first()
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
                                semester_id=semester_id, subject_code=subject_code))

    errors  = []
    saved   = 0
    skipped = 0

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
            academic_year=academic_year,
        ).first()

        if ext_row and ext_row.locked:
            errors.append(f"PRN ({prn}): record is locked — cannot overwrite")
            continue

        existing = models.TheoryMarks.query.filter_by(
            prn=student.prn,
            subject_code=subject_code,
            academic_year=academic_year
        ).first()

        if existing is None:
            existing = models.TheoryMarks(
                prn=student.prn,
                subject_code=subject_code,
                semester_id=semester_id,
                academic_year=academic_year
            )
            db.session.add(existing)

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

        # Call SGPA/CGPA recalculation for that student
        try:
            update_sgpa_cgpa_for_student(student.prn, semester_id, academic_year, db, models)
        except Exception as e:
            pass

        saved += 1

    db.session.commit()

    flash(f"Upload complete: {saved} saved, {skipped} skipped (blank), {len(errors)} error(s).", 
          "success" if not errors else "warning")
    
    if errors:
        session["upload_errors"] = errors[:50]  # store up to 50 errors in session

    return redirect(url_for("external.external_marks_page",
                            semester_id=semester_id, subject_code=subject_code))


# ── ROUTE: /download-external-template ───────────────────────────────────────

@external_bp.route("/download-external-template")
@admin_or_teacher_required
def download_external_template():
    from external_excel_utils import generate_external_template

    subject_code  = request.args.get("subject_code")
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")

    subj = models.Subject.query.filter_by(subject_code=subject_code).first()
    if academic_year:
        sem = models.Semester.query.filter_by(semester_id=semester_id, academic_year=academic_year).first()
    else:
        sem = models.Semester.query.filter_by(semester_id=semester_id).first()

    if not subj or not sem:
        flash("Invalid subject or semester.", "error")
        return redirect(url_for("external.external_marks_page"))

    students_data = _get_subject_students(subject_code, semester_id, academic_year)

    meta = {
        "subject_code": subject_code,
        "subject_name": subj.subject_name,
        "semester_id": semester_id,
        "academic_year": academic_year,
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

    subj = models.Subject.query.filter_by(subject_code=subject_code).first()
    if not subj:
        flash("Subject not found.", "error")
        return redirect(url_for("external.external_marks_page"))

    data, meta = build_external_data(subject_code, semester_id, academic_year)
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
    subject_code  = request.args.get("subject_code")
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")

    subj = models.Subject.query.filter_by(subject_code=subject_code).first()
    if not subj:
        flash("Subject not found.", "error")
        return redirect(url_for("external.external_marks_page"))

    data, meta = build_external_data(subject_code, semester_id, academic_year)
    if not data:
        flash("No data found for the report.", "error")
        return redirect(url_for("external.external_marks_page"))

    output   = io.BytesIO()
    doc      = SimpleDocTemplate(output, pagesize=landscape(A4),
                                 leftMargin=1.5*cm, rightMargin=1.5*cm,
                                 topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles   = getSampleStyleSheet()
    elements = []

    DARK_BLUE = colors.HexColor("#1E3A5F")
    LIGHT_BLUE = colors.HexColor("#D6EAF8")
    GREEN  = colors.HexColor("#D5F5E3")
    RED    = colors.HexColor("#FADBD8")
    GREY   = colors.HexColor("#F2F3F4")

    # ── Header ───────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("title", fontSize=14, fontName="Helvetica-Bold",
                                 textColor=DARK_BLUE, alignment=1, spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   fontSize=10, fontName="Helvetica",
                                 alignment=1, spaceAfter=2)
    info_style  = ParagraphStyle("info",  fontSize=9,  fontName="Helvetica",
                                 alignment=1, spaceAfter=10)

    elements.append(Paragraph("CSMSS Chh. Shahu College of Engineering", title_style))
    elements.append(Paragraph("Department of Electronics &amp; Computer Engineering", sub_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=DARK_BLUE))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        f"<b>External Marks Report</b> &nbsp;|&nbsp; {subj.subject_code} — {subj.subject_name} "
        f"&nbsp;|&nbsp; Semester {semester_id} &nbsp;|&nbsp; A.Y. {academic_year} "
        f"&nbsp;|&nbsp; Date: {datetime.now().strftime('%d %b %Y')}",
        info_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    elements.append(Spacer(1, 8))

    # ── Table ────────────────────────────────────────────────────────────────
    table_data = [["SR", "PRN", "Student Name", "Internal (/40)", "External (/60)", "Total (/100)", "Grade", "GP", "Result"]]

    marks_list = []
    pass_c = fail_c = 0

    for i, s in enumerate(data, 1):
        ext = s["external"]
        internal = s["internal"]
        total = s["total"]
        status = s["status"]

        if ext is not None:
            marks_list.append(ext)
            if status == "PASS": pass_c += 1
            else:         fail_c += 1

        table_data.append([
            str(i),
            s["prn"],
            s["name"],
            str(internal) if internal is not None else "—",
            str(ext) if ext is not None else "—",
            str(total) if total is not None else "—",
            s["grade"] or "—",
            str(s["grade_point"]) if s["grade_point"] is not None else "—",
            status
        ])

    tbl = Table(table_data, colWidths=[1.0*cm, 3.5*cm, 6.5*cm, 2.2*cm, 2.2*cm, 2.2*cm, 1.8*cm, 2.2*cm, 2.0*cm], repeatRows=1)
    tbl_style = TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0), 9),
        ("ALIGN",        (0,0), (-1,-1), "CENTER"),
        ("ALIGN",        (2,1), (2,-1), "LEFT"),
        ("FONTSIZE",     (0,1), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, GREY]),
        ("GRID",         (0,0), (-1,-1), 0.4, colors.grey),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ])

    # Colour pass/fail rows in column 8 (Result)
    for i, s in enumerate(data, 1):
        status = s["status"]
        if status == "PASS":
            tbl_style.add("BACKGROUND", (8, i), (8, i), GREEN)
        elif status == "FAIL":
            tbl_style.add("BACKGROUND", (8, i), (8, i), RED)
            tbl_style.add("TEXTCOLOR",  (8, i), (8, i), colors.red)

    tbl.setStyle(tbl_style)
    elements.append(tbl)
    elements.append(Spacer(1, 14))

    # ── Summary box ──────────────────────────────────────────────────────────
    avg_marks = round(sum(marks_list)/len(marks_list), 2) if marks_list else 0
    pass_pct  = round(pass_c/len(marks_list)*100, 1) if marks_list else 0

    summary_data = [
        ["Total Students", "Entered", "Pass", "Fail", "Pass%", "Highest", "Lowest", "Average"],
        [str(len(data)), str(len(marks_list)),
         str(pass_c), str(fail_c), f"{pass_pct}%",
         str(max(marks_list)) if marks_list else "—",
         str(min(marks_list)) if marks_list else "—",
         str(avg_marks)],
    ]
    sum_tbl = Table(summary_data)
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), LIGHT_BLUE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.grey),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    elements.append(sum_tbl)
    elements.append(Spacer(1, 30))

    # ── Signature block ───────────────────────────────────────────────────────
    sig_data = [["Subject Teacher", "HOD — ECE", "Principal"]]
    sig_tbl  = Table(sig_data, colWidths=[8*cm, 8*cm, 8*cm])
    sig_tbl.setStyle(TableStyle([
        ("ALIGN",   (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE",(0,0), (-1,-1), 9),
        ("TOPPADDING",   (0,0), (-1,-1), 30),
        ("LINEABOVE",    (0,0), (-1,0), 0.5, colors.black),
    ]))
    elements.append(sig_tbl)

    doc.build(elements)
    output.seek(0)

    filename = f"External_Report_{subject_code}_Sem{semester_id}.pdf"
    return send_file(output, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


# ── ROUTE: /external/stats  (JSON — dashboard cards) ─────────────────────────

@external_bp.route("/external/stats")
def external_stats():
    """JSON endpoint for dashboard cards."""
    semester_id   = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "")

    if not semester_id:
        active = models.Semester.query.filter_by(is_active=True).first()
        semester_id   = active.semester_id   if active else 1
        academic_year = active.academic_year if active else ""

    theory_subjects = models.Subject.query.filter_by(
        semester_id=semester_id, subject_type="THEORY", is_audit=False).all()

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
def download_sgpa_cgpa_excel():
    semester_id = request.args.get("semester_id", type=int)
    academic_year = request.args.get("academic_year", "").strip()

    if not semester_id:
        flash("Please select semester first.", "error")
        return redirect(url_for("external.external_marks_page"))

    if not academic_year:
        academic_year = "2024-25"

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
