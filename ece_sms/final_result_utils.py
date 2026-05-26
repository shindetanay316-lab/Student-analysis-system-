from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from models import db, Student, Subject, Enrollment, TheoryMarks


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
# Grade calculation
# -------------------------------------------------
def calculate_grade(total_marks, external_marks=None):
    """
    total_marks: out of 100
    external_marks: out of 60

    Assumption:
    - Total pass condition: total >= 40
    - External pass condition: external >= 24
    """

    total = _safe_float(total_marks)
    external = _safe_float(external_marks)

    if total < 40 or external < 24:
        return {
            "grade": "EF",
            "grade_point": 0.0,
            "is_passed": False
        }

    if total >= 91:
        grade, gp = "EX", 10.0
    elif total >= 86:
        grade, gp = "AA", 9.0
    elif total >= 81:
        grade, gp = "AB", 8.5
    elif total >= 76:
        grade, gp = "BB", 8.0
    elif total >= 71:
        grade, gp = "BC", 7.5
    elif total >= 66:
        grade, gp = "CC", 7.0
    elif total >= 61:
        grade, gp = "CD", 6.5
    elif total >= 56:
        grade, gp = "DD", 6.0
    elif total >= 51:
        grade, gp = "DE", 5.5
    else:
        grade, gp = "EE", 5.0

    return {
        "grade": grade,
        "grade_point": gp,
        "is_passed": True
    }


# -------------------------------------------------
# Recalculate final result for one TheoryMarks row
# -------------------------------------------------
def recalculate_theory_result(mark_row):
    """
    Updates:
    - total_marks
    - grade
    - grade_point
    - is_passed
    """

    if mark_row is None:
        return None

    internal = _safe_float(mark_row.internal_total)
    external = _safe_float(mark_row.external)

    mark_row.total_marks = internal + external

    grade_data = calculate_grade(
        total_marks=mark_row.total_marks,
        external_marks=external
    )

    mark_row.grade = grade_data["grade"]
    mark_row.grade_point = grade_data["grade_point"]
    mark_row.is_passed = grade_data["is_passed"]

    return mark_row


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
            Subject.subject_type == "THEORY"
        )
        .order_by(Subject.subject_code)
        .all()
    )

    rows = []
    total_credits = 0
    total_credit_points = 0
    is_complete = True
    has_failed = False

    for enrollment, subject in enrolled_subjects:
        marks = TheoryMarks.query.filter_by(
            prn=prn,
            subject_code=subject.subject_code,
            semester_id=semester_id,
            academic_year=academic_year
        ).first()

        credits = int(subject.credits or 0)

        internal = None
        external = None
        total = None
        grade = "-"
        grade_point = None
        result = "PENDING"
        credit_points = None

        if marks:
            internal = marks.internal_total
            external = marks.external

            if marks.internal_total is not None and marks.external is not None:
                recalculate_theory_result(marks)

                total = marks.total_marks
                grade = marks.grade
                grade_point = marks.grade_point
                result = "PASS" if marks.is_passed else "FAIL"

                credit_points = credits * _safe_float(grade_point)
                total_credits += credits
                total_credit_points += credit_points

                if not marks.is_passed:
                    has_failed = True
            else:
                is_complete = False
        else:
            is_complete = False

        rows.append({
            "subject_code": subject.subject_code,
            "subject_name": subject.subject_name,
            "credits": credits,
            "internal": internal,
            "external": external,
            "total": total,
            "grade": grade,
            "grade_point": grade_point,
            "credit_points": credit_points,
            "result": result
        })

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
            "total_credit_points": sem_result["total_credit_points"],
            "sgpa": sem_result["sgpa"],
            "result": sem_result["result"]
        })

    return result_rows


# -------------------------------------------------
# Calculate CGPA for one student up to selected semester
# -------------------------------------------------
def calculate_cgpa_for_student(prn, upto_semester_id=None):
    query = (
        db.session.query(TheoryMarks, Subject)
        .join(Subject, TheoryMarks.subject_code == Subject.subject_code)
        .filter(
            TheoryMarks.prn == prn,
            Subject.subject_type == "THEORY"
        )
    )

    if upto_semester_id is not None:
        query = query.filter(TheoryMarks.semester_id <= upto_semester_id)

    rows = query.all()

    total_credits = 0
    total_credit_points = 0

    for marks, subject in rows:
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
