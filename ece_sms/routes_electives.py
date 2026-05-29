from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db, Student, Subject, Semester, Enrollment
from academic_utils import get_academic_year_for_semester


electives_bp = Blueprint("electives", __name__)



def _is_admin():
    role = getattr(current_user, "role", "")
    return str(role).upper() == "ADMIN"


def _academic_year_for_semester(semester_id):
    """Return the academic year from the semesters table."""
    return get_academic_year_for_semester(semester_id)


def _option_subjects_query(semester_id, elective_group=None):
    q = (
        Subject.query
        .filter(Subject.semester_id == semester_id)
        .filter(Subject.is_active == True)
        .filter(Subject.is_elective == True)
        .filter(Subject.parent_subject_code.isnot(None))
        .filter(Subject.elective_group.isnot(None))
    )
    if elective_group:
        q = q.filter(Subject.elective_group == elective_group)
    return q.order_by(Subject.elective_group, Subject.subject_code)


def _semester_students(semester_id, academic_year):
    """Students already present in this semester through compulsory/lab enrollments."""
    return (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year,
        )
        .distinct()
        .order_by(Student.prn)
        .all()
    )


def _load_page_data(selected_semester, selected_group, selected_subject):
    all_semesters = Semester.query.order_by(Semester.semester_id).all()

    academic_year = None
    groups = []
    options = []
    students = []
    current_choice = {}
    selected_prns = set()
    option_counts = {}

    if selected_semester:
        academic_year = _academic_year_for_semester(selected_semester)

        group_rows = (
            db.session.query(Subject.elective_group)
            .filter(Subject.semester_id == selected_semester)
            .filter(Subject.is_active == True)
            .filter(Subject.is_elective == True)
            .filter(Subject.parent_subject_code.isnot(None))
            .filter(Subject.elective_group.isnot(None))
            .distinct()
            .order_by(Subject.elective_group)
            .all()
        )
        groups = [g[0] for g in group_rows if g[0]]

        if selected_group not in groups:
            selected_group = ""
            selected_subject = ""

        if selected_group:
            options = _option_subjects_query(selected_semester, selected_group).all()
            option_codes = [s.subject_code for s in options]

            if selected_subject and selected_subject not in option_codes:
                selected_subject = ""

            if option_codes:
                count_rows = (
                    db.session.query(Enrollment.subject_code, func.count(Enrollment.id))
                    .filter(
                        Enrollment.semester_id == selected_semester,
                        Enrollment.academic_year == academic_year,
                        Enrollment.subject_code.in_(option_codes),
                    )
                    .group_by(Enrollment.subject_code)
                    .all()
                )
                option_counts = {code: int(count) for code, count in count_rows}

                existing = (
                    Enrollment.query
                    .filter(
                        Enrollment.semester_id == selected_semester,
                        Enrollment.academic_year == academic_year,
                        Enrollment.subject_code.in_(option_codes),
                    )
                    .all()
                )
                current_choice = {enr.prn: enr.subject_code for enr in existing}

                if selected_subject:
                    selected_prns = {
                        enr.prn for enr in existing
                        if enr.subject_code == selected_subject
                    }

            students = _semester_students(selected_semester, academic_year)

    return {
        "all_semesters": all_semesters,
        "academic_year": academic_year,
        "groups": groups,
        "options": options,
        "students": students,
        "current_choice": current_choice,
        "selected_prns": selected_prns,
        "option_counts": option_counts,
        "selected_semester": selected_semester,
        "selected_group": selected_group,
        "selected_subject": selected_subject,
    }


@electives_bp.route("/electives", methods=["GET"])
@login_required
def elective_assignment_page():
    if not _is_admin():
        flash("Only admin users can access Elective Assignment.", "error")
        return redirect(url_for("index"))

    selected_semester = request.args.get("semester_id", type=int)
    selected_group = request.args.get("elective_group", "").strip()
    selected_subject = request.args.get("subject_code", "").strip()

    page_data = _load_page_data(
        selected_semester=selected_semester,
        selected_group=selected_group,
        selected_subject=selected_subject,
    )

    return render_template("elective_assignment.html", **page_data)


@electives_bp.route("/electives/save", methods=["POST"])
@login_required
def save_elective_assignment():
    if not _is_admin():
        flash("Only admin users can save elective assignments.", "error")
        return redirect(url_for("index"))

    semester_id = request.form.get("semester_id", type=int)
    elective_group = request.form.get("elective_group", "").strip()
    subject_code = request.form.get("subject_code", "").strip()
    selected_prns = request.form.getlist("student_prns")

    if not semester_id or not elective_group or not subject_code:
        flash("Please select semester, elective group and subject option.", "error")
        return redirect(url_for("electives.elective_assignment_page"))

    if not selected_prns:
        flash("Please select at least one student before saving.", "error")
        return redirect(url_for(
            "electives.elective_assignment_page",
            semester_id=semester_id,
            elective_group=elective_group,
            subject_code=subject_code,
        ))

    academic_year = _academic_year_for_semester(semester_id)

    selected_subject = Subject.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        elective_group=elective_group,
        is_active=True,
    ).first()

    if (
        selected_subject is None
        or not selected_subject.is_elective
        or selected_subject.parent_subject_code is None
    ):
        flash("Invalid elective option selected.", "error")
        return redirect(url_for(
            "electives.elective_assignment_page",
            semester_id=semester_id,
            elective_group=elective_group,
        ))

    option_subjects = _option_subjects_query(semester_id, elective_group).all()
    option_codes = [s.subject_code for s in option_subjects]

    # Include parent placeholder row in cleanup. Older/manual data may have
    # enrollments like BTECHM505 instead of BTECHM505B. Those parent rows must
    # be removed when a real option is assigned, otherwise SGPA/CGPA becomes
    # PENDING for that student.
    parent_code = selected_subject.parent_subject_code
    cleanup_codes = list(option_codes)
    if parent_code and parent_code not in cleanup_codes:
        cleanup_codes.append(parent_code)

    if subject_code not in option_codes:
        flash("Selected subject does not belong to the selected elective group.", "error")
        return redirect(url_for(
            "electives.elective_assignment_page",
            semester_id=semester_id,
            elective_group=elective_group,
        ))

    valid_students = {
        stu.prn for stu in _semester_students(semester_id, academic_year)
    }
    selected_prns = [prn for prn in selected_prns if prn in valid_students]

    if not selected_prns:
        flash("Selected students are not enrolled in this semester.", "error")
        return redirect(url_for(
            "electives.elective_assignment_page",
            semester_id=semester_id,
            elective_group=elective_group,
            subject_code=subject_code,
        ))

    try:
        # Remove only the previous option from the SAME elective group for selected students.
        # Compulsory/lab/other group enrollments are untouched.
        (
            Enrollment.query
            .filter(
                Enrollment.prn.in_(selected_prns),
                Enrollment.semester_id == semester_id,
                Enrollment.academic_year == academic_year,
                Enrollment.subject_code.in_(cleanup_codes),
            )
            .delete(synchronize_session=False)
        )

        for prn in selected_prns:
            db.session.add(Enrollment(
                prn=prn,
                subject_code=subject_code,
                semester_id=semester_id,
                academic_year=academic_year,
            ))

        db.session.commit()

        flash(
            f"Assigned {len(selected_prns)} student(s) to {subject_code} successfully.",
            "success",
        )

    except Exception as exc:
        db.session.rollback()
        flash(f"Elective assignment failed: {exc}", "error")

    return redirect(url_for(
        "electives.elective_assignment_page",
        semester_id=semester_id,
        elective_group=elective_group,
        subject_code=subject_code,
    ))
