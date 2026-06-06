from models import db, Student, Subject, TheoryMarks, Enrollment, ExternalMarks
from calculations import compute_final_result, is_theory_internal_complete, update_internal_totals
from batch_utils import clean_filter, apply_student_batch_filters, batch_label


def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_external_data(subject_code, semester_id, academic_year, division="", batch=""):
    """
    Builds external marks report data for one selected THEORY subject.

    Fixes:
      - Adds semester_id filter for TheoryMarks and ExternalMarks.
      - Uses calculations.compute_final_result() as source of truth.
      - Shows PENDING when internal/external/result data is incomplete.
      - Uses ESE pass minimum 20/60 through compute_final_result().
    """
    subj = Subject.query.get(subject_code)
    if not subj:
        return [], {}

    students_query = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year,
        )
    )
    students_query = apply_student_batch_filters(students_query, Student, division, batch)
    students = students_query.order_by(Student.prn).all()

    theory_marks = TheoryMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year,
    ).all()

    external_marks = ExternalMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year,
    ).all()

    tm_lookup = {tm.prn: tm for tm in theory_marks}
    ext_lookup = {ext.prn: ext for ext in external_marks}

    data = []
    credits = int(subj.credits or 0)

    for sr, stu in enumerate(students, 1):
        tm = tm_lookup.get(stu.prn)
        ext = ext_lookup.get(stu.prn)

        internal_val = None
        if tm:
            update_internal_totals(tm)
            if is_theory_internal_complete(tm) and tm.internal_total is not None:
                internal_val = _safe_float(tm.internal_total)

        external_val = None
        if tm and tm.external is not None:
            external_val = _safe_float(tm.external)
        elif ext and ext.external_marks is not None:
            external_val = _safe_float(ext.external_marks)

        total_val = None
        grade_val = None
        grade_point_val = None
        status_val = "PENDING"

        if internal_val is not None and external_val is not None:
            result = compute_final_result(
                internal_marks=internal_val,
                external_marks=external_val,
                credits=credits,
            )
            total_val = result["total"]
            grade_val = result["grade"]
            grade_point_val = float(result["grade_point"])
            status_val = "PASS" if result["is_passed"] else "FAIL"
        elif tm and tm.is_passed is True:
            status_val = "PASS"
        elif tm and tm.is_passed is False and tm.external is not None:
            status_val = "FAIL"

        data.append({
            "sr": sr,
            "prn": stu.prn,
            "name": stu.name,
            "internal": internal_val,
            "external": external_val,
            "total": total_val,
            "grade": grade_val or "—",
            "grade_point": grade_point_val,
            "status": status_val,
        })

    meta = {
        "subject_code": subj.subject_code,
        "subject_name": subj.subject_name,
        "semester_id": semester_id,
        "academic_year": academic_year,
        "credits": subj.credits,
        "division": clean_filter(division),
        "batch": clean_filter(batch),
        "batch_label": batch_label(division, batch),
    }

    return data, meta
