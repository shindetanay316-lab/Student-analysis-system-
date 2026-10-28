"""Attendance workspace: calendars, sessions, reviewed uploads and reports."""
from io import BytesIO
from types import SimpleNamespace
from datetime import timedelta
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, OperationalError
from models import db, Semester, Subject, AttendanceSession
from attendance_models import AttendanceCalendar, AttendanceHoliday, AttendanceChange
from workflow_models import WorkflowReview
from academic_utils import get_academic_year_for_semester, attendance_subjects_query
from routes_teaching import admin_required, normalize_academic_year, audit
from attendance_utils import generate_timetable_template, parse_timetable_upload, generate_attendance_template, parse_date, generate_defaulter_excel, generate_defaulter_pdf
import attendance_services as services

attendance_bp = Blueprint('attendance', __name__)


@attendance_bp.before_request
def protect():
    if request.method == 'POST':
        from result_data import csrf
        csrf.protect()


def get_context(values):
    values = dict(values)
    if not values.get('academic_year'):
        values['academic_year'] = get_academic_year_for_semester(values.get('semester_id'))
    try:
        return services.context(values)
    except ValueError as error:
        abort(400, str(error))


def return_to(c=None):
    c = c or {}
    return redirect(url_for('attendance.attendance_page', **{k: c[k] for k in ('semester_id', 'academic_year', 'subject_code', 'division', 'batch') if k in c}))


@attendance_bp.get('/attendance')
@login_required
def attendance_page():
    active = Semester.query.filter_by(is_active=True).first()
    sem = request.args.get('semester_id', type=int) or (active.semester_id if active else 1)
    try:
        year = normalize_academic_year(request.args.get('academic_year') or get_academic_year_for_semester(sem))
    except ValueError as error:
        abort(400, str(error))
    if sem not in range(1, 9):
        abort(400)
    code = request.args.get('subject_code', '').strip().upper()
    c = get_context(dict(request.args, semester_id=sem, academic_year=year)) if code else None
    calendar = AttendanceCalendar.query.filter_by(semester_id=sem, academic_year=year).first()
    start = parse_date(request.args.get('start_date')) or (calendar.start_date if calendar else services.local_now().date().replace(day=1))
    end = parse_date(request.args.get('end_date')) or (calendar.end_date if calendar else start + timedelta(days=30))
    rows, planned, changes, cancelled = [], [], [], []
    if c:
        try:
            planned = services.planned(c, start, end)
        except ValueError as error:
            flash(str(error), 'error')
        rows = services.report_rows(c, start, end)
        ids = [s.id for s in AttendanceSession.query.filter_by(**services.course_values(c))]
        changes = AttendanceChange.query.filter(AttendanceChange.session_id.in_(ids)).order_by(AttendanceChange.id.desc()).limit(100).all()
        cancelled = AttendanceSession.query.filter_by(**services.course_values(c), status='CANCELLED').filter(AttendanceSession.lecture_date.between(start, end)).all()
        for spec in planned:
            session = services.find_session(c, spec)
            spec['entries'] = session.entries.count() if session else 0
    return render_template('attendance.html', context=c, selected_semester=sem, academic_year=year,
        all_semesters=Semester.query.order_by(Semester.academic_year.desc(), Semester.semester_id).all(),
        subjects=attendance_subjects_query(sem).all(), calendar=calendar,
        holidays=AttendanceHoliday.query.filter_by(semester_id=sem, academic_year=year, is_active=True).order_by(AttendanceHoliday.holiday_date).all(),
        start_date=start, end_date=end, rows=rows, planned=planned, changes=changes, cancelled=cancelled,
        subject=db.session.get(Subject, code) if code else None,
        stats=dict(students=len(rows), recorded=sum(r['total'] > 0 for r in rows), defaulters=sum(r['total'] > 0 and not r['conflicts'] and r['percentage'] < 75 for r in rows)))


@attendance_bp.get('/attendance/api/subjects')
@login_required
def api_attendance_subjects():
    sem = request.args.get('semester_id', type=int)
    return jsonify(subjects=[s.to_dict() for s in attendance_subjects_query(sem).all()] if sem else [])


@attendance_bp.get('/attendance/download-timetable-template')
@login_required
def download_timetable_template():
    meta = None
    if request.args.get('semester_id'):
        try:
            semester = int(request.args['semester_id'])
            year = normalize_academic_year(request.args.get('academic_year'))
            if not db.session.get(Semester, (semester, year)):
                raise ValueError('Select an existing teaching term.')
            meta = dict(semester_id=semester, academic_year=year, division=request.args.get('division') or 'ALL')
        except (ValueError, TypeError) as error:
            abort(400, str(error))
    buffer, filename = generate_timetable_template(meta)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@attendance_bp.post('/attendance/upload-timetable')
@admin_required
def upload_timetable():
    file = request.files.get('timetable_file')
    if not file or not file.filename.lower().endswith('.xlsx'):
        flash('Select a filled XLSX timetable.', 'error')
        return return_to()
    success, errors, count = parse_timetable_upload(file, get_academic_year_for_semester())
    flash(f'Timetable saved: {count} weekly slots.' if success else 'Timetable not saved:\n' + '\n'.join(errors[:15]), 'success' if success else 'error')
    return return_to()


@attendance_bp.get('/attendance/download-template')
@login_required
def download_attendance_template():
    c = get_context(request.args)
    try:
        items = services.generated_items(c, parse_date(request.args.get('start_date')), parse_date(request.args.get('end_date')))
        students = services.roster(c)
        if not items:
            raise ValueError('No scheduled classes in the chosen range after holidays/cancellations. Add a timetable or makeup class.')
        if len(items) > 500:
            raise ValueError('Choose a shorter range (at most 500 session columns).')
        if not students:
            raise ValueError('No students enrolled for this subject/division/batch. Ask admin to set up the roster.')
        c['subject_name'] = db.session.get(Subject, c['subject_code']).subject_name
        buffer, filename = generate_attendance_template(c, students, items)
    except ValueError as error:
        flash(str(error), 'error')
        return return_to(c)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@attendance_bp.post('/attendance/upload')
@login_required
def upload_attendance():
    try:
        review = services.new_review(request.files.get('attendance_file'))
    except ValueError as error:
        flash('Attendance not saved: ' + str(error), 'error')
        return return_to()
    return redirect(url_for('attendance.review_page', token=review.token))


def authorized_review(token):
    review = db.get_or_404(WorkflowReview, token)
    if review.kind != 'ATTENDANCE':
        abort(404)
    if review.owner_id != current_user.user_id and current_user.role != 'ADMIN':
        abort(403)
    services.context(review.context)
    return review


@attendance_bp.get('/attendance/reviews/<token>')
@login_required
def review_page(token):
    review = authorized_review(token)
    return render_template('attendance/review.html', review=review, subject=db.session.get(Subject, review.context['subject_code']))


@attendance_bp.get('/attendance/reviews/<token>/source')
@login_required
def review_source(token):
    review = authorized_review(token)
    return send_file(BytesIO(review.source_workbook), as_attachment=True, download_name=review.source_name, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@attendance_bp.post('/attendance/reviews/<token>/confirm')
@login_required
def confirm_review(token):
    review = authorized_review(token)
    try:
        changed = services.confirm(review)
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else 'Attendance changed concurrently. Upload a fresh preview. No partial changes were saved.'
        return render_template('workflow/conflict.html', message=message, context={k: review.context[k] for k in ('subject_code','semester_id','academic_year','division','batch')}, kind='ATTENDANCE'), 409
    flash('Attendance confirmed; summary updated.' if changed else 'Already confirmed; no duplicate entries created.', 'success')
    return return_to(review.context)


def admin_action(action):
    try:
        action(request.form)
        flash('Attendance calendar updated.', 'success')
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error, ValueError) else 'The calendar changed. Reload and try again.', 'error')
    return return_to(request.form)


@attendance_bp.post('/attendance/calendar')
@admin_required
def calendar_save():
    return admin_action(services.save_calendar)


@attendance_bp.post('/attendance/holidays')
@admin_required
def holiday_add():
    return admin_action(services.add_holiday)


@attendance_bp.post('/attendance/holidays/<int:holiday_id>/remove')
@admin_required
def holiday_remove(holiday_id):
    holiday = db.get_or_404(AttendanceHoliday, holiday_id)
    services.lock_term(dict(semester_id=holiday.semester_id, academic_year=holiday.academic_year))
    holiday.is_active = False
    audit(current_user, 'attendance_holiday_removed', {'holiday_id': holiday.id, 'date': str(holiday.holiday_date), 'reason': holiday.reason})
    db.session.commit()
    return return_to(dict(semester_id=holiday.semester_id, academic_year=holiday.academic_year))


@attendance_bp.post('/attendance/sessions/<action>')
@login_required
def session_action(action):
    c = get_context(request.form)
    try:
        services.lock_term(c)
        db.session.execute(db.select(Subject).where(Subject.subject_code == c['subject_code']).with_for_update())
        if action == 'cancel':
            services.cancel_session(c, request.form)
        elif action == 'makeup':
            services.add_makeup(c, request.form)
        else:
            abort(404)
        flash('Class cancelled and totals refreshed.' if action == 'cancel' else 'Makeup class scheduled. Record attendance after the class is conducted.', 'success')
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error, ValueError) else 'The timetable changed. Reload and try again.', 'error')
    return return_to(c)


def filtered_report():
    c = get_context(request.args)
    start, end = parse_date(request.args.get('start_date')), parse_date(request.args.get('end_date'))
    if (request.args.get('start_date') and not start) or (request.args.get('end_date') and not end):
        abort(400, 'Enter valid report dates.')
    if bool(start) != bool(end):
        abort(400, 'Provide both report dates or leave both empty.')
    if start:
        try:
            services.validate_range(c, start, end)
        except ValueError as error:
            abort(400, str(error))
    return c, services.report_rows(c, start, end)


@attendance_bp.get('/attendance/defaulters/<fmt>')
@login_required
def download_defaulters(fmt):
    c, data = filtered_report()
    threshold = request.args.get('threshold', default=75., type=float)
    if threshold is None or threshold != threshold:
        threshold = 75.
    threshold = min(100., max(0., threshold))
    rows = [(SimpleNamespace(percentage=r['percentage'], total_lectures=r['total'], attended_lectures=r['present']), r['student']) for r in data if r['total'] > 0 and not r['conflicts']]
    c['subject_name'] = db.session.get(Subject, c['subject_code']).subject_name
    if fmt == 'excel':
        buffer, filename = generate_defaulter_excel(c, rows, threshold)
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        buffer, filename = generate_defaulter_pdf(c, rows, threshold)
        mime = 'application/pdf'
    else:
        abort(404)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype=mime)


@attendance_bp.get('/attendance/report/<fmt>')
@login_required
def report(fmt):
    c, rows = filtered_report()
    from attendance_reports import generate_report
    if fmt not in {'excel', 'pdf'}:
        abort(404)
    c['subject_name'] = db.session.get(Subject, c['subject_code']).subject_name
    c['start_date'], c['end_date'] = request.args.get('start_date', ''), request.args.get('end_date', '')
    buffer, filename, mime = generate_report(c, rows, fmt)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype=mime)
