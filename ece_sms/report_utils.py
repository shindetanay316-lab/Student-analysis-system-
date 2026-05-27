from models import db, Student, Subject, TheoryMarks, Enrollment


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _calculate_internal_components(ct1, ct2, assignment, mse):
    """
    DBATU internal formula:
      CA1 = best score among CT1, CT2, Assignment
      CA2 = second-best score among CT1, CT2, Assignment
      Internal = CA1 + CA2 + MSE
    """
    scores = sorted(
        [_safe_float(ct1), _safe_float(ct2), _safe_float(assignment)],
        reverse=True
    )
    ca1 = scores[0]
    ca2 = scores[1]
    ca_total = ca1 + ca2
    internal = ca_total + _safe_float(mse)

    return ca1, ca2, ca_total, internal


def build_internal_data(subject_code, semester_id, academic_year):
    """
    Builds internal marks report data for one subject.

    Uses the corrected formula:
      CA1 = highest of CT1, CT2, Assignment
      CA2 = second highest of CT1, CT2, Assignment
      Internal Total = CA1 + CA2 + MSE
    """
    subj = Subject.query.get(subject_code)
    if not subj:
        return [], {
            "subject_code": subject_code,
            "subject_name": "Subject not found",
            "semester_id": semester_id,
            "academic_year": academic_year,
        }

    students = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year,
        )
        .order_by(Student.prn)
        .all()
    )

    marks = TheoryMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year,
    ).all()

    lookup = {m.prn: m for m in marks}
    data = []

    for sr, stu in enumerate(students, 1):
        m = lookup.get(stu.prn)

        ct1 = _safe_float(m.ct1) if m else 0.0
        ct2 = _safe_float(m.ct2) if m else 0.0
        assignment = _safe_float(m.assignment) if m else 0.0
        mse = _safe_float(m.midsem) if m else 0.0

        ca1, ca2, ca_total, internal = _calculate_internal_components(
            ct1, ct2, assignment, mse
        )

        data.append({
            "sr": sr,
            "prn": stu.prn,
            "name": stu.name,
            "ct1": ct1,
            "ct2": ct2,
            "assignment": assignment,

            # Corrected report fields
            "ca1": ca1,
            "ca2": ca2,
            "ca_total": ca_total,
            "mse": mse,
            "internal": internal,

            # Backward-compatible aliases for old Excel/PDF code.
            # We will update the visible headers in excel_utils.py and pdf_utils.py next.
            "best_ct": ca1,
            "ca": ca_total,
            "midsem": mse,
        })

    meta = {
        "subject_code": subj.subject_code,
        "subject_name": subj.subject_name,
        "semester_id": semester_id,
        "academic_year": academic_year,
    }

    return data, meta
