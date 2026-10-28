"""Admin-reviewed university links and scoped student history/export routes."""
from io import BytesIO
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, OperationalError
from models import db, Student, Subject, Semester
from result_data.models import ImportJob
from workflow_models import WorkflowReview
from academic_link_models import UniversityPublication
from routes_teaching import admin_required
import academic_link_services as links
import student_history_services as students

academic_bp = Blueprint('academic', __name__, url_prefix='/academic')


@academic_bp.before_request
def protect():
    if request.method == 'POST':
        from result_data import csrf
        csrf.protect()


@academic_bp.get('/linking')
@admin_required
def linking():
    return render_template('academic/linking.html', jobs=ImportJob.query.filter(ImportJob.confirmed_at.isnot(None),
        ImportJob.status.in_(['READY', 'EXPORTED'])).order_by(ImportJob.id.desc()).all(),
        publications=UniversityPublication.query.order_by(UniversityPublication.approved_at.desc()).limit(100).all())


@academic_bp.get('/linking/<int:job_id>')
@admin_required
def mapping(job_id):
    job = db.get_or_404(ImportJob, job_id)
    try:
        semester = links.confirmed_job(job)
    except ValueError as error:
        flash(str(error), 'error')
        return redirect(url_for('academic.linking'))
    return render_template('academic/mapping.html', job=job, semester=semester,
        terms=Semester.query.filter_by(semester_id=semester).order_by(Semester.academic_year.desc()).all(),
        subjects=Subject.query.filter_by(semester_id=semester, is_active=True).order_by(Subject.subject_name).all())


@academic_bp.post('/linking/<int:job_id>/preview')
@admin_required
def preview(job_id):
    job = db.get_or_404(ImportJob, job_id)
    try:
        review = links.preview(job, request.form)
    except ValueError as error:
        flash(str(error), 'error')
        return redirect(url_for('academic.mapping', job_id=job_id))
    return redirect(url_for('academic.review', token=review.token))


def link_review(token):
    item = db.get_or_404(WorkflowReview, token)
    if item.kind != 'UNIVERSITY_LINK':
        abort(404)
    return item


@academic_bp.get('/linking/reviews/<token>')
@admin_required
def review(token):
    return render_template('academic/review.html', review=link_review(token))


@academic_bp.get('/linking/reviews/<token>/source')
@admin_required
def review_source(token):
    item = link_review(token)
    return send_file(BytesIO(item.source_workbook), download_name=item.source_name or 'university-source.pdf', as_attachment=True, mimetype='application/pdf')


@academic_bp.post('/linking/reviews/<token>/confirm')
@admin_required
def confirm(token):
    item = link_review(token)
    try:
        if not item.confirmed_at and request.form.get('verified') != 'on':
            raise ValueError('Confirm that you verified the selected identities, subjects and teaching year.')
        changed = links.confirm(item, set(request.form.getlist('rows')), set(request.form.getlist('copy_ese')))
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else 'Records changed concurrently. Create a fresh preview; no partial changes were saved.'
        return render_template('academic/conflict.html', message=message, context=item.context), 409
    flash('University results linked after review.' if changed else 'Already confirmed. No duplicate records were created.', 'success')
    return redirect(url_for('academic.review', token=item.token))


@academic_bp.get('/students')
@login_required
def student_list():
    query = students.student_query()
    search = request.args.get('q', '').strip()
    cohort = request.args.get('cohort', type=int)
    if search:
        query = query.filter(db.or_(Student.prn.ilike('%' + search + '%'), Student.name.ilike('%' + search + '%')))
    if cohort:
        query = query.filter_by(year_of_admission=cohort)
    page = query.order_by(Student.prn).paginate(page=request.args.get('page', 1, type=int), per_page=50, error_out=False)
    return render_template('academic/students.html', page=page, search=search, cohort=cohort)


@academic_bp.get('/students/<prn>')
@login_required
def student_detail(prn):
    return render_template('academic/student.html', **students.history(prn))


@academic_bp.post('/students/<prn>/portfolio')
@admin_required
def portfolio_save(prn):
    student = db.get_or_404(Student, prn)
    try:
        students.save_portfolio(student, request.form)
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error, ValueError) else 'The profile changed concurrently. Reload before saving.', 'error')
        return redirect(url_for('academic.student_detail', prn=prn)), 303
    flash('Student portfolio saved. Academic marks and identities are unchanged.', 'success')
    return redirect(url_for('academic.student_detail', prn=prn))


@academic_bp.get('/students/<prn>/export/<fmt>')
@login_required
def student_export(prn, fmt):
    if fmt not in {'excel', 'pdf'}:
        abort(404)
    from student_history_reports import generate_history
    stream, filename, mime = generate_history(students.history(prn), fmt)
    return send_file(stream, download_name=filename, as_attachment=True, mimetype=mime)
