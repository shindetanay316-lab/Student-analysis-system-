from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, Student
from batch_utils import DIVISION_OPTIONS, BATCH_OPTIONS, clean_filter


batches_bp = Blueprint("batches", __name__)


def _is_admin():
    role = getattr(current_user, "role", "")
    return str(role).upper() == "ADMIN"


@batches_bp.route("/batches", methods=["GET"])
@login_required
def batch_assignment_page():
    """Simple batch/division assignment page.

    The old page had separate filter steps and assignment steps, which was easy
    to confuse. This page always shows all students and uses a simple client-side
    search/filter so the actual save flow is only:
      1. choose target division/batch
      2. tick students
      3. save
    """
    if not _is_admin():
        flash("Only admin users can access Batch / Division Assignment.", "error")
        return redirect(url_for("index"))

    students = Student.query.order_by(Student.prn).all()

    total_students = Student.query.count()
    unassigned_count = Student.query.filter(
        ((Student.division == None) | (Student.division == "")) |
        ((Student.batch == None) | (Student.batch == ""))
    ).count()

    counts = {}
    for division in DIVISION_OPTIONS:
        counts[division] = Student.query.filter(Student.division == division).count()

    batch_counts = {}
    for batch in BATCH_OPTIONS:
        batch_counts[batch] = Student.query.filter(Student.batch == batch).count()

    return render_template(
        "batch_assignment.html",
        students=students,
        division_options=DIVISION_OPTIONS,
        batch_options=BATCH_OPTIONS,
        total_students=total_students,
        unassigned_count=unassigned_count,
        counts=counts,
        batch_counts=batch_counts,
    )


@batches_bp.route("/batches/save", methods=["POST"])
@login_required
def save_batch_assignment():
    if not _is_admin():
        flash("Only admin users can save Batch / Division Assignment.", "error")
        return redirect(url_for("index"))

    division = clean_filter(request.form.get("division", ""))
    batch = clean_filter(request.form.get("batch", ""))
    selected_prns = request.form.getlist("student_prns")

    if not division:
        flash("Please select the division you want to assign.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    if not batch:
        flash("Please select the batch you want to assign.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    if division not in DIVISION_OPTIONS:
        flash("Invalid division selected.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    if batch not in BATCH_OPTIONS:
        flash("Invalid batch selected.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    if not batch.startswith(division):
        flash(
            f"Batch {batch} belongs to Division {batch[0]}. Please select matching Division {batch[0]}.",
            "error",
        )
        return redirect(url_for("batches.batch_assignment_page"))

    if not selected_prns:
        flash("Tick at least one student before saving.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    students = Student.query.filter(Student.prn.in_(selected_prns)).all()

    for student in students:
        student.division = division
        student.batch = batch

    db.session.commit()
    flash(f"Saved: {len(students)} student(s) assigned to Division {division}, Batch {batch}.", "success")
    return redirect(url_for("batches.batch_assignment_page"))


@batches_bp.route("/batches/clear", methods=["POST"])
@login_required
def clear_batch_assignment():
    if not _is_admin():
        flash("Only admin users can clear Batch / Division Assignment.", "error")
        return redirect(url_for("index"))

    selected_prns = request.form.getlist("student_prns")
    if not selected_prns:
        flash("Tick at least one student to clear.", "error")
        return redirect(url_for("batches.batch_assignment_page"))

    students = Student.query.filter(Student.prn.in_(selected_prns)).all()
    for student in students:
        student.division = None
        student.batch = None

    db.session.commit()
    flash(f"Cleared division and batch for {len(students)} student(s).", "success")
    return redirect(url_for("batches.batch_assignment_page"))
