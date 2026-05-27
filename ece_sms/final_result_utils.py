from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from models import db, Student, Subject, Enrollment, TheoryMarks, LabMarks
from calculations import compute_final_result, compute_lab_result, get_grade, update_internal_totals, is_theory_internal_complete


TNR = "Times New Roman"


# -------------------------------------------------
# Basic Excel styles
# -------------------------------------------------
def _center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)


def _left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)


def _thin_border():
    side = Side(style="thin", color="000000")
    return Border(left=side, right=side, top=side, bottom=side)


def _header_fill():
    return PatternFill("solid", fgColor="D9EAF7")


def _title_fill():
    return PatternFill("solid", fgColor="1F4E78")


def _title_font():
    return Font(name=TNR, size=14, bold=True, color="FFFFFF")


def _header_font():
    return Font(name=TNR, size=11, bold=True, color="000000")


def _body_font(bold=False):
    return Font(name=TNR, size=10, bold=bold, color="000000")


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


# -------------------------------------------------
# Backward-compatible grade helper
# -------------------------------------------------
def calculate_grade(total_marks, external_marks=None):
    """
    Backward-compatible wrapper.

    THEORY result decisions are delegated to calculations.compute_final_result(),
    so the ESE minimum remains one single source of truth: external >= 20.
    """
    total = _safe_float(total_marks)

    if external_marks is not None:
        external = _safe_float(external_marks)
        internal = total - external
        result = compute_final_result(
            internal_marks=internal,
            external_marks=external,
            credits=0
        )
        return {
            "grade": result["grade"] or "EF",
            "grade_point": float(result["grade_point"] or 0),
            "is_passed": bool(result["is_passed"])
        }

    # Used only for LAB/PROJECT totals where no separate ESE minimum is applied.
    if total < 40:
        return {
            "grade": "EF",
            "grade_point": 0.0,
            "is_passed": False
        }

    grade, gp = get_grade(total)
    return {
        "grade": grade,
        "grade_point": float(gp),
        "is_passed": True
    }


# -------------------------------------------------
# Recalculate final result for one TheoryMarks row
# -------------------------------------------------
def recalculate_theory_result(mark_row):
    """
    Updates one TheoryMarks row using calculations.py as the single source of truth.

    Theory pass conditions:
    - Internal: /40
    - External: /60
    - Total: /100
    - Pass only when external >= 20 AND total >= 40

    Also refreshes internal_total using the confirmed formula:
    Internal = best 2 of (CT1, CT2, Assignment) + MSE.
    """

    if mark_row is None:
        return None

    # Keep internal fields consistent with the confirmed CA1 + CA2 + MSE formula.
    update_internal_totals(mark_row)

    # Final result should remain PENDING until every internal component and
    # the external marks are present. This prevents incomplete records from
    # appearing as FAIL just because missing marks were treated as 0.
    if not is_theory_internal_complete(mark_row) or mark_row.external is None:
        mark_row.total_marks = None
        mark_row.grade = None
        mark_row.grade_point = None
        mark_row.is_passed = None
        return mark_row

    subject = Subject.query.filter_by(subject_code=mark_row.subject_code).first()
    credits = int(subject.credits or 0) if subject else 0

    result = compute_final_result(
        internal_marks=mark_row.internal_total,
        external_marks=mark_row.external,
        credits=credits
    )

    mark_row.total_marks = result["total"]
    mark_row.grade = result["grade"]
    mark_row.grade_point = result["grade_point"]
    mark_row.is_passed = result["is_passed"]

    return mark_row


# -------------------------------------------------
# Recalculate result for one LabMarks / Project row
# -------------------------------------------------
def recalculate_lab_result(lab_row):
    """
    Lab/Project result:
    - CA1: /30
    - CA2: /30
    - Internal: CA1 + CA2 = /60
    - External: /40
    - Total: /100
    - Pass when total >= 40

    Compatibility: if old rows have internal/external but no ca1/ca2,
    the existing internal value is still used.
    """

    if lab_row is None:
        return None

    if lab_row.external is None:
        lab_row.total_marks = None
        lab_row.grade = None
        lab_row.grade_point = None
        lab_row.is_passed = None
        return lab_row

    ca1 = getattr(lab_row, "ca1", None)
    ca2 = getattr(lab_row, "ca2", None)

    if ca1 is not None and ca2 is not None:
        subject = Subject.query.filter_by(subject_code=lab_row.subject_code).first()
        credits = int(subject.credits or 0) if subject else 0
        result = compute_lab_result(
            ca1_marks=ca1,
            ca2_marks=ca2,
            external_marks=lab_row.external,
            credits=credits
        )
        lab_row.internal = result["internal"]
        lab_row.total_marks = result["total"]
        lab_row.grade = result["grade"]
        lab_row.grade_point = result["grade_point"]
        lab_row.is_passed = result["is_passed"]
        return lab_row

    if lab_row.internal is None:
        lab_row.total_marks = None
        lab_row.grade = None
        lab_row.grade_point = None
        lab_row.is_passed = None
        return lab_row

    total = _safe_float(lab_row.internal) + _safe_float(lab_row.external)
    lab_row.total_marks = round(total, 2)

    if total < 40:
        lab_row.grade = "EF"
        lab_row.grade_point = 0.0
        lab_row.is_passed = False
    else:
        grade, gp = get_grade(total)
        lab_row.grade = grade
        lab_row.grade_point = gp
        lab_row.is_passed = True

    return lab_row


# -------------------------------------------------
# Internal helpers for report calculation
# -------------------------------------------------
def _add_subject_result(rows, subject, internal, external, total, grade, grade_point, result):
    credits = int(subject.credits or 0)
    credit_points = None

    if grade_point is not None:
        credit_points = round(credits * _safe_float(grade_point), 2)

    rows.append({
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "subject_type": subject.subject_type,
        "credits": credits,
        "internal": internal,
        "external": external,
        "total": total,
        "grade": grade,
        "grade_point": grade_point,
        "credit_points": credit_points,
        "result": result
    })

    return credit_points


# -------------------------------------------------
# Build one student's semester result
# -------------------------------------------------
def build_student_semester_result(prn, semester_id, academic_year):
    student = Student.query.filter_by(prn=prn).first()

    enrolled_subjects = (
        db.session.query(Enrollment, Subject)
        .join(Subject, Enrollment.subject_code == Subject.subject_code)
        .filter(
            Enrollment.prn == prn,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year,
            Subject.is_audit == False
        )
        .order_by(Subject.subject_code)
        .all()
    )

    rows = []
    total_credits = 0
    total_credit_points = 0
    credits_earned = 0
    is_complete = True
    has_failed = False

    for enrollment, subject in enrolled_subjects:
        credits = int(subject.credits or 0)
        total_credits += credits

        internal = None
        external = None
        total = None
        grade = "-"
        grade_point = None
        result = "PENDING"

        if subject.subject_type == "THEORY":
            marks = TheoryMarks.query.filter_by(
                prn=prn,
                subject_code=subject.subject_code,
                semester_id=semester_id,
                academic_year=academic_year
            ).first()

            if marks and marks.external is not None:
                recalculate_theory_result(marks)

                if marks.is_passed is None or marks.total_marks is None:
                    is_complete = False
                else:
                    internal = marks.internal_total
                    external = marks.external
                    total = marks.total_marks
                    grade = marks.grade or "-"
                    grade_point = marks.grade_point
                    result = "PASS" if marks.is_passed is True else "FAIL"

                    if marks.is_passed is True:
                        credits_earned += credits
                    else:
                        has_failed = True
            else:
                is_complete = False

        else:
            lab = LabMarks.query.filter_by(
                prn=prn,
                subject_code=subject.subject_code,
                semester_id=semester_id,
                academic_year=academic_year
            ).first()

            if lab and lab.external is not None and (lab.internal is not None or (getattr(lab, "ca1", None) is not None and getattr(lab, "ca2", None) is not None)):
                recalculate_lab_result(lab)

                internal = lab.internal
                external = lab.external
                total = lab.total_marks
                grade = lab.grade or "-"
                grade_point = lab.grade_point
                if lab.is_passed is None or lab.total_marks is None:
                    is_complete = False
                else:
                    result = "PASS" if lab.is_passed is True else "FAIL"

                    if lab.is_passed is True:
                        credits_earned += credits
                    else:
                        has_failed = True
            else:
                is_complete = False

        credit_points = _add_subject_result(
            rows=rows,
            subject=subject,
            internal=internal,
            external=external,
            total=total,
            grade=grade,
            grade_point=grade_point,
            result=result
        )

        if credit_points is not None:
            total_credit_points += credit_points

    if not enrolled_subjects:
        is_complete = False

    sgpa = None
    if is_complete and total_credits > 0:
        sgpa = round(total_credit_points / total_credits, 2)

    return {
        "student": student,
        "prn": prn,
        "semester_id": semester_id,
        "academic_year": academic_year,
        "subjects": rows,
        "total_credits": total_credits,
        "credits_earned": credits_earned,
        "total_credit_points": round(total_credit_points, 2),
        "sgpa": sgpa,
        "is_complete": is_complete,
        "has_failed": has_failed,
        "result": "PASS" if is_complete and not has_failed else ("FAIL" if is_complete else "PENDING")
    }


# -------------------------------------------------
# Build semester result for all students
# -------------------------------------------------
def build_semester_result(semester_id, academic_year):
    students = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year
        )
        .distinct()
        .order_by(Student.prn)
        .all()
    )

    result_rows = []

    for student in students:
        sem_result = build_student_semester_result(
            prn=student.prn,
            semester_id=semester_id,
            academic_year=academic_year
        )

        result_rows.append({
            "prn": student.prn,
            "name": student.name,
            "total_credits": sem_result["total_credits"],
            "credits_earned": sem_result["credits_earned"],
            "total_credit_points": sem_result["total_credit_points"],
            "sgpa": sem_result["sgpa"],
            "result": sem_result["result"]
        })

    return result_rows


# -------------------------------------------------
# Calculate CGPA for one student up to selected semester
# -------------------------------------------------
def calculate_cgpa_for_student(prn, upto_semester_id=None):
    """
    CGPA includes both theory and lab/project marks.
    Audit subjects are excluded.
    """

    total_credits = 0
    total_credit_points = 0

    theory_query = (
        db.session.query(TheoryMarks, Subject)
        .join(Subject, TheoryMarks.subject_code == Subject.subject_code)
        .filter(
            TheoryMarks.prn == prn,
            Subject.subject_type == "THEORY",
            Subject.is_audit == False
        )
    )

    lab_query = (
        db.session.query(LabMarks, Subject)
        .join(Subject, LabMarks.subject_code == Subject.subject_code)
        .filter(
            LabMarks.prn == prn,
            Subject.subject_type != "THEORY",
            Subject.is_audit == False
        )
    )

    if upto_semester_id is not None:
        theory_query = theory_query.filter(TheoryMarks.semester_id <= upto_semester_id)
        lab_query = lab_query.filter(LabMarks.semester_id <= upto_semester_id)

    for marks, subject in theory_query.all():
        if marks.grade_point is None:
            continue

        credits = int(subject.credits or 0)
        total_credits += credits
        total_credit_points += credits * _safe_float(marks.grade_point)

    for marks, subject in lab_query.all():
        if marks.grade_point is None:
            continue

        credits = int(subject.credits or 0)
        total_credits += credits
        total_credit_points += credits * _safe_float(marks.grade_point)

    if total_credits == 0:
        return None

    return round(total_credit_points / total_credits, 2)


# -------------------------------------------------
# Build SGPA + CGPA report
# -------------------------------------------------
def build_sgpa_cgpa_report(semester_id, academic_year):
    semester_rows = build_semester_result(semester_id, academic_year)

    final_rows = []

    for row in semester_rows:
        cgpa = calculate_cgpa_for_student(
            prn=row["prn"],
            upto_semester_id=semester_id
        )

        final_rows.append({
            "prn": row["prn"],
            "name": row["name"],
            "semester_id": semester_id,
            "academic_year": academic_year,
            "sgpa": row["sgpa"],
            "cgpa": cgpa,
            "total_credits": row["total_credits"],
            "credits_earned": row.get("credits_earned"),
            "total_credit_points": row["total_credit_points"],
            "result": row["result"]
        })

    return final_rows


# -------------------------------------------------
# Generate SGPA/CGPA Excel report
# -------------------------------------------------
def generate_sgpa_cgpa_excel_report(semester_id, academic_year):
    rows = build_sgpa_cgpa_report(semester_id, academic_year)

    wb = Workbook()
    ws = wb.active
    ws.title = "SGPA CGPA Report"

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 14
    ws.column_dimensions["G"].width = 16
    ws.column_dimensions["H"].width = 16
    ws.column_dimensions["I"].width = 14

    ws.merge_cells("A1:I1")
    title = ws["A1"]
    title.value = "SGPA / CGPA REPORT"
    title.font = _title_font()
    title.alignment = _center()
    title.fill = _title_fill()
    title.border = _thin_border()

    ws.merge_cells("A2:I2")
    sub = ws["A2"]
    sub.value = f"Semester: {semester_id}     Academic Year: {academic_year}"
    sub.font = _body_font(bold=True)
    sub.alignment = _center()
    sub.border = _thin_border()

    headers = [
        "SR",
        "PRN",
        "Student Name",
        "Semester",
        "SGPA",
        "CGPA",
        "Total Credits",
        "Credit Points",
        "Result"
    ]

    start_row = 4

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col)
        cell.value = header
        cell.font = _header_font()
        cell.alignment = _center()
        cell.fill = _header_fill()
        cell.border = _thin_border()

    for idx, row in enumerate(rows, start=1):
        r = start_row + idx

        values = [
            idx,
            row["prn"],
            row["name"],
            row["semester_id"],
            row["sgpa"] if row["sgpa"] is not None else "PENDING",
            row["cgpa"] if row["cgpa"] is not None else "PENDING",
            row["total_credits"],
            row["total_credit_points"],
            row["result"]
        ]

        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col)
            cell.value = value
            cell.font = _body_font()
            cell.alignment = _center() if col != 3 else _left()
            cell.border = _thin_border()

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"SGPA_CGPA_Report_Sem_{semester_id}_{academic_year}.xlsx"
    filename = filename.replace("/", "-")

    return output, filename
