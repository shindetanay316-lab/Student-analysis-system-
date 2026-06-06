"""Shared academic-year and subject-query helpers for ECE SMS.

Purpose:
- Stop repeating hardcoded semester -> academic year maps.
- Keep subject visibility rules consistent everywhere.

Rules:
- Academic year is read from the semesters table.
- Audit subjects are hidden from marks/reports.
- Generic elective parent rows are hidden.
- Actual elective options are shown.
"""

from flask import current_app
from sqlalchemy import or_

from models import Semester, Subject


def _config_fallback(default="2024-25"):
    """Read fallback academic year from Flask config when an app context exists."""
    try:
        return current_app.config.get("CURRENT_ACADEMIC_YEAR", default)
    except RuntimeError:
        return default


def get_academic_year_for_semester(semester_id=None, fallback=None):
    """Return academic year for a selected semester using the semesters table.

    If multiple rows exist for the same semester_id, prefer the active row;
    otherwise use the latest academic_year value.
    """
    fallback = fallback or _config_fallback()

    if not semester_id:
        active = Semester.query.filter_by(is_active=True).first()
        return active.academic_year if active else fallback

    active = (
        Semester.query
        .filter_by(semester_id=semester_id, is_active=True)
        .first()
    )
    if active:
        return active.academic_year

    sem = (
        Semester.query
        .filter_by(semester_id=semester_id)
        .order_by(Semester.academic_year.desc())
        .first()
    )
    return sem.academic_year if sem else fallback


def get_semester_row(semester_id=None, academic_year=None):
    """Return the best matching Semester row."""
    if semester_id and academic_year:
        row = Semester.query.filter_by(
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()
        if row:
            return row

    if semester_id:
        active = Semester.query.filter_by(
            semester_id=semester_id,
            is_active=True,
        ).first()
        if active:
            return active

        return (
            Semester.query
            .filter_by(semester_id=semester_id)
            .order_by(Semester.academic_year.desc())
            .first()
        )

    return Semester.query.filter_by(is_active=True).first()


def visible_subjects_query(semester_id=None, subject_types=None):
    """Common visible-subject query used by marks, lab, external, and reports.

    Subject Management can soft-disable a subject by setting is_active=False.
    Disabled subjects remain in the database for old records, but are hidden
    from new marks entry and dropdowns.
    """
    query = Subject.query.filter(
        Subject.is_audit == False,
        Subject.is_active == True,
        Subject.is_attendance_only == False,
    )

    if semester_id is not None:
        query = query.filter(Subject.semester_id == semester_id)

    if subject_types:
        if isinstance(subject_types, str):
            query = query.filter(Subject.subject_type == subject_types)
        else:
            query = query.filter(Subject.subject_type.in_(list(subject_types)))

    query = query.filter(
        or_(
            Subject.is_elective == False,
            Subject.parent_subject_code.isnot(None),
        )
    )

    return query.order_by(Subject.semester_id, Subject.subject_code)


def visible_theory_subjects_query(semester_id=None):
    """Visible THEORY subjects only."""
    return visible_subjects_query(semester_id, "THEORY")


def visible_lab_subjects_query(semester_id=None):
    """Visible LAB / PROJECT subjects only."""
    return visible_subjects_query(semester_id, ["LAB", "PROJECT"])



def attendance_subjects_query(semester_id=None):
    """Subjects visible in the attendance module.

    Includes normal theory/lab/project subjects plus audit/attendance-only timetable activities.
    This keeps non-credit timetable sessions available for attendance without affecting SGPA/CGPA.
    """
    query = Subject.query.filter(Subject.is_active == True)
    if semester_id is not None:
        query = query.filter(Subject.semester_id == semester_id)
    return query.order_by(Subject.semester_id, Subject.subject_code)
