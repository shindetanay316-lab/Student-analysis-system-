from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import (
    db, Student, Subject, Semester, Enrollment,
    TheoryMarks, LabMarks, Attendance, ExternalMarks, TimetableSlot
)
from academic_utils import get_academic_year_for_semester


subjects_bp = Blueprint("subjects", __name__)

SUBJECT_TYPES = ["THEORY", "LAB", "PROJECT", "AUDIT"]


def _is_admin():
    role = getattr(current_user, "role", "")
    return str(role).upper() == "ADMIN"


def _clean_code(value):
    return (value or "").strip().upper().replace(" ", "")


def _clean_text(value):
    return (value or "").strip()


def _int_value(name, default=0):
    raw = request.form.get(name, default)
    try:
        return int(raw or default)
    except (TypeError, ValueError):
        return default


def _flag(name):
    return request.form.get(name) in ("1", "on", "true", "TRUE", "yes")


def _subject_dependency_count(subject_code):
    """Rows that make hard-delete unsafe."""
    from teaching_models import TeachingAssignment
    from completion_models import AssessmentPolicy, CourseOutcomeSelection
    return {
        'assessment_policies': AssessmentPolicy.query.filter_by(subject_code=subject_code).count(),
        'approved_outcomes': CourseOutcomeSelection.query.filter_by(subject_code=subject_code).count(),
        "linked_university_results": _linked_university_count(subject_code),
        "approved_curricula": len(_approved_curricula(subject_code)),
        "teaching_assignments": TeachingAssignment.query.filter_by(subject_code=subject_code).count(),
        "enrollments": Enrollment.query.filter_by(subject_code=subject_code).count(),
        "theory_marks": TheoryMarks.query.filter_by(subject_code=subject_code).count(),
        "lab_marks": LabMarks.query.filter_by(subject_code=subject_code).count(),
        "attendance": Attendance.query.filter_by(subject_code=subject_code).count(),
        "external_marks": ExternalMarks.query.filter_by(subject_code=subject_code).count(),
        "timetable_slots": TimetableSlot.query.filter_by(subject_code=subject_code).count(),
        "child_options": Subject.query.filter_by(parent_subject_code=subject_code).count(),
    }


def _approved_curricula(subject_code):
    from curriculum_models import CurriculumVersion
    return [v.token for v in CurriculumVersion.query.with_entities(CurriculumVersion.token, CurriculumVersion.courses).filter_by(status='APPROVED')
            if any(r.get('include') and r.get('code') == subject_code for r in v.courses)]


def _linked_university_count(subject_code):
    from academic_link_models import UniversityLinkedResult
    return UniversityLinkedResult.query.filter_by(subject_code=subject_code).count()


def _configured_definition_count(subject_code):
    from completion_models import AssessmentPolicy, CourseOutcomeSelection
    return (AssessmentPolicy.query.filter_by(subject_code=subject_code).count()
        + CourseOutcomeSelection.query.filter_by(subject_code=subject_code).count())


def _total_dependencies(dep):
    return sum(int(v or 0) for v in dep.values())


def _subject_or_404(subject_code):
    subject = db.session.get(Subject, _clean_code(subject_code))
    if subject is None:
        abort(404)
    return subject


def _parent_subjects(semester_id=None, current_code=None):
    q = Subject.query.filter(
        Subject.is_elective == True,
        Subject.parent_subject_code.is_(None),
        Subject.is_active == True,
    )
    if semester_id:
        q = q.filter(Subject.semester_id == semester_id)
    if current_code:
        q = q.filter(Subject.subject_code != current_code)
    return q.order_by(Subject.semester_id, Subject.subject_code).all()


def _load_subjects(selected_semester=None, search="", include_inactive=True):
    q = Subject.query
    if selected_semester:
        q = q.filter(Subject.semester_id == selected_semester)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Subject.subject_code.like(like), Subject.subject_name.like(like)))
    if not include_inactive:
        q = q.filter(Subject.is_active == True)
    return q.order_by(Subject.semester_id, Subject.subject_code).all()


@subjects_bp.route("/subjects", methods=["GET"])
@login_required
def subjects_page():
    if not _is_admin():
        flash("Only admin users can access Subject Management.", "error")
        return redirect(url_for("index"))

    selected_semester = request.args.get("semester_id", type=int)
    search = _clean_text(request.args.get("q", ""))
    edit_code = _clean_code(request.args.get("edit", ""))

    all_semesters = Semester.query.order_by(Semester.semester_id, Semester.academic_year).all()
    edit_subject = db.session.get(Subject, edit_code) if edit_code else None

    subjects = _load_subjects(selected_semester, search, include_inactive=True)

    stats = {
        "total": Subject.query.count(),
        "active": Subject.query.filter_by(is_active=True).count(),
        "inactive": Subject.query.filter_by(is_active=False).count(),
        "theory": Subject.query.filter_by(subject_type="THEORY", is_active=True).count(),
        "lab_project": Subject.query.filter(
            Subject.subject_type.in_(["LAB", "PROJECT"]),
            Subject.is_active == True,
        ).count(),
        "audit": Subject.query.filter_by(is_audit=True, is_active=True).count(),
        "elective": Subject.query.filter_by(is_elective=True, is_active=True).count(),
    }

    parent_subjects = _parent_subjects(
        semester_id=edit_subject.semester_id if edit_subject else selected_semester,
        current_code=edit_subject.subject_code if edit_subject else None,
    )

    return render_template(
        "subject_management.html",
        all_semesters=all_semesters,
        subjects=subjects,
        edit_subject=edit_subject,
        subject_types=SUBJECT_TYPES,
        parent_subjects=parent_subjects,
        selected_semester=selected_semester,
        search=search,
        stats=stats,
        dependencies={s.subject_code: _subject_dependency_count(s.subject_code) for s in subjects},
    )


@subjects_bp.route("/subjects/save", methods=["POST"])
@login_required
def save_subject():
    if not _is_admin():
        flash("Only admin users can save subjects.", "error")
        return redirect(url_for("index"))

    original_code = _clean_code(request.form.get("original_subject_code"))
    subject_code = _clean_code(request.form.get("subject_code"))
    subject_name = _clean_text(request.form.get("subject_name"))
    semester_id = _int_value("semester_id", 0)
    subject_type = _clean_text(request.form.get("subject_type", "THEORY")).upper()

    if not subject_code or not subject_name or not semester_id:
        flash("Subject code, subject name and semester are required.", "error")
        return redirect(url_for("subjects.subjects_page"))

    if len(subject_code) > 20 or len(subject_name) > 150 or not 1 <= semester_id <= 8:
        flash("Use a subject code up to 20 characters, a name up to 150 characters, and semester 1 to 8.", "error")
        return redirect(url_for("subjects.subjects_page"))

    if subject_type not in SUBJECT_TYPES:
        flash("Invalid subject type selected.", "error")
        return redirect(url_for("subjects.subjects_page"))

    sem = Semester.query.filter_by(semester_id=semester_id).first()
    if not sem:
        flash("Selected semester row does not exist. Create the semester first.", "error")
        return redirect(url_for("subjects.subjects_page"))

    is_edit = bool(original_code)
    if is_edit:
        subject = db.session.get(Subject, original_code)
        if not subject:
            flash("Subject to edit was not found.", "error")
            return redirect(url_for("subjects.subjects_page"))
        subject_code = original_code  # primary key is not changed during edit
    else:
        if db.session.get(Subject, subject_code):
            flash(f"Subject code {subject_code} already exists. Use Edit instead.", "error")
            return redirect(url_for("subjects.subjects_page", edit=subject_code))
        subject = Subject(subject_code=subject_code)
        db.session.add(subject)

    if is_edit and (_approved_curricula(subject_code) or _linked_university_count(subject_code) or _configured_definition_count(subject_code)):
        flash('This subject is used by approved curriculum or university evidence. Its academic definition was preserved; enable/disable remains available.', 'error')
        return redirect(url_for('subjects.subjects_page', edit=subject_code))

    credits = _int_value("credits", 0)
    l_hours = _int_value("l_hours", 0)
    t_hours = _int_value("t_hours", 0)
    p_hours = _int_value("p_hours", 0)
    if any(value < 0 for value in (credits, l_hours, t_hours, p_hours)):
        db.session.rollback()
        flash("Credits and weekly hours cannot be negative.", "error")
        return redirect(url_for("subjects.subjects_page", edit=original_code or subject_code))
    category = _clean_text(request.form.get("category", ""))
    is_elective = _flag("is_elective")
    is_audit = _flag("is_audit") or subject_type == "AUDIT"
    is_attendance_only = _flag("is_attendance_only")
    is_active = _flag("is_active")
    elective_group = _clean_text(request.form.get("elective_group", "")) or None
    parent_subject_code = _clean_code(request.form.get("parent_subject_code", "")) or None

    if not is_elective:
        elective_group = None
        parent_subject_code = None

    if parent_subject_code == subject_code:
        db.session.rollback()
        flash("A subject cannot be its own parent elective subject.", "error")
        return redirect(url_for("subjects.subjects_page", edit=original_code or subject_code))

    if parent_subject_code:
        parent = db.session.get(Subject, parent_subject_code)
        if (
            not parent
            or not parent.is_elective
            or parent.parent_subject_code is not None
            or parent.semester_id != semester_id
        ):
            db.session.rollback()
            flash("Selected parent must be an elective parent in the same semester.", "error")
            return redirect(url_for("subjects.subjects_page", edit=original_code or subject_code))

        if not elective_group:
            db.session.rollback()
            flash("An elective option with a parent must have an elective group.", "error")
            return redirect(url_for("subjects.subjects_page", edit=original_code or subject_code))

    subject.subject_name = subject_name
    subject.semester_id = semester_id
    subject.subject_type = subject_type
    subject.credits = credits
    subject.l_hours = l_hours
    subject.t_hours = t_hours
    subject.p_hours = p_hours
    subject.category = category
    subject.is_elective = is_elective
    subject.elective_group = elective_group
    subject.parent_subject_code = parent_subject_code
    subject.is_audit = is_audit
    subject.is_attendance_only = is_attendance_only
    if is_attendance_only:
        subject.is_audit = True
        subject.credits = 0
    subject.is_active = is_active

    db.session.commit()
    flash(f"Subject {subject.subject_code} saved successfully.", "success")
    return redirect(url_for("subjects.subjects_page", semester_id=semester_id))


@subjects_bp.route("/subjects/<subject_code>/disable", methods=["POST"])
@login_required
def disable_subject(subject_code):
    if not _is_admin():
        flash("Only admin users can disable subjects.", "error")
        return redirect(url_for("index"))
    subject = _subject_or_404(subject_code)
    subject.is_active = False
    db.session.commit()
    flash(f"Subject {subject.subject_code} disabled. It will be hidden from marks dropdowns.", "success")
    return redirect(request.referrer or url_for("subjects.subjects_page"))


@subjects_bp.route("/subjects/<subject_code>/enable", methods=["POST"])
@login_required
def enable_subject(subject_code):
    if not _is_admin():
        flash("Only admin users can enable subjects.", "error")
        return redirect(url_for("index"))
    subject = _subject_or_404(subject_code)
    subject.is_active = True
    db.session.commit()
    flash(f"Subject {subject.subject_code} enabled.", "success")
    return redirect(request.referrer or url_for("subjects.subjects_page"))


@subjects_bp.route("/subjects/<subject_code>/delete", methods=["POST"])
@login_required
def delete_subject(subject_code):
    if not _is_admin():
        flash("Only admin users can delete subjects.", "error")
        return redirect(url_for("index"))

    subject = _subject_or_404(subject_code)
    dep = _subject_dependency_count(subject.subject_code)

    if _total_dependencies(dep) > 0:
        subject.is_active = False
        db.session.commit()
        flash(
            f"{subject.subject_code} has existing records, so it was safely disabled instead of deleted.",
            "warning",
        )
        return redirect(request.referrer or url_for("subjects.subjects_page"))

    db.session.delete(subject)
    db.session.commit()
    flash(f"Subject {subject.subject_code} deleted permanently because it had no records.", "success")
    return redirect(url_for("subjects.subjects_page"))


@subjects_bp.route("/subjects/<subject_code>/enroll-compulsory", methods=["POST"])
@login_required
def enroll_compulsory_subject(subject_code):
    """Enroll every student into a newly-added compulsory subject."""
    if not _is_admin():
        flash("Only admin users can create enrollments.", "error")
        return redirect(url_for("index"))

    subject = _subject_or_404(subject_code)
    if subject.elective_group and not subject.is_elective:
        flash('This course is a curriculum choice option. Use reviewed curriculum enrollment to select exactly one option per student.', 'error')
        return redirect(url_for('curriculum.index'))
    if subject.is_audit:
        flash("Audit subjects are not enrolled for marks/SGPA.", "error")
        return redirect(request.referrer or url_for("subjects.subjects_page"))
    if subject.is_elective:
        flash("Use Elective Assignment for elective subjects.", "error")
        return redirect(request.referrer or url_for("subjects.subjects_page"))

    academic_year = get_academic_year_for_semester(subject.semester_id)
    students = Student.query.order_by(Student.prn).all()
    created = 0

    for student in students:
        exists = Enrollment.query.filter_by(
            prn=student.prn,
            subject_code=subject.subject_code,
            semester_id=subject.semester_id,
            academic_year=academic_year,
        ).first()
        if exists:
            continue
        db.session.add(Enrollment(
            prn=student.prn,
            subject_code=subject.subject_code,
            semester_id=subject.semester_id,
            academic_year=academic_year,
        ))
        created += 1

    db.session.commit()
    flash(
        f"Enrollment complete for {subject.subject_code}: {created} new student enrollment(s) created.",
        "success",
    )
    return redirect(request.referrer or url_for("subjects.subjects_page", semester_id=subject.semester_id))
