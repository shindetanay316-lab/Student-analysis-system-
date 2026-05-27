from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user

from models import db, Semester, Subject, TimetableSlot
from academic_utils import get_academic_year_for_semester, attendance_subjects_query
from batch_utils import clean_filter, DIVISION_OPTIONS, BATCH_OPTIONS, batch_label
from attendance_utils import (
    generate_timetable_template, parse_timetable_upload,
    timetable_slots_for_subject, generate_dates_from_slots,
    students_for_attendance, generate_attendance_template,
    parse_attendance_upload, parse_date, attendance_summary,
    generate_defaulter_excel, generate_defaulter_pdf,
)

attendance_bp = Blueprint('attendance', __name__)


def _is_admin():
    return str(getattr(current_user, 'role', '')).upper() == 'ADMIN'


@attendance_bp.route('/attendance')
@login_required
def attendance_page():
    selected_semester = request.args.get('semester_id', type=int)
    active = Semester.query.filter_by(is_active=True).first()
    if not selected_semester and active:
        selected_semester = active.semester_id

    academic_year = get_academic_year_for_semester(selected_semester)
    selected_subject = request.args.get('subject_code', '').strip().upper()
    selected_division = clean_filter(request.args.get('division', ''))
    selected_batch = clean_filter(request.args.get('batch', ''))

    all_semesters = Semester.query.order_by(Semester.semester_id, Semester.academic_year).all()
    subjects = attendance_subjects_query(selected_semester).all() if selected_semester else []

    slots = []
    summary_rows = []
    if selected_semester and selected_subject:
        slots = timetable_slots_for_subject(
            selected_semester,
            academic_year,
            selected_subject,
            selected_division or 'ALL',
            selected_batch or 'ALL',
        )
        summary_rows = attendance_summary(selected_subject, selected_semester, academic_year)

    stats = {
        'slots': TimetableSlot.query.filter_by(semester_id=selected_semester, academic_year=academic_year, is_active=True).count() if selected_semester else 0,
        'subjects': len(subjects),
        'records': len(summary_rows),
        'defaulters': sum(1 for att, _stu in summary_rows if float(att.percentage or 0) < 75),
    }

    return render_template(
        'attendance.html',
        all_semesters=all_semesters,
        selected_semester=selected_semester,
        academic_year=academic_year,
        subjects=subjects,
        selected_subject=selected_subject,
        selected_division=selected_division,
        selected_batch=selected_batch,
        division_options=DIVISION_OPTIONS,
        batch_options=BATCH_OPTIONS,
        batch_label=batch_label(selected_division, selected_batch),
        slots=slots,
        summary_rows=summary_rows,
        stats=stats,
    )


@attendance_bp.route('/attendance/api/subjects')
@login_required
def api_attendance_subjects():
    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        return jsonify({'subjects': []})
    subjects = attendance_subjects_query(semester_id).all()
    return jsonify({'subjects': [s.to_dict() for s in subjects]})


@attendance_bp.route('/attendance/download-timetable-template')
@login_required
def download_timetable_template():
    buf, filename = generate_timetable_template()
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@attendance_bp.route('/attendance/upload-timetable', methods=['POST'])
@login_required
def upload_timetable():
    if not _is_admin():
        flash('Only admin can upload weekly timetable.', 'error')
        return redirect(url_for('attendance.attendance_page'))

    file = request.files.get('timetable_file')
    if not file or file.filename == '':
        flash('Please select a timetable Excel file.', 'error')
        return redirect(url_for('attendance.attendance_page'))
    if not file.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx timetable files are accepted.', 'error')
        return redirect(url_for('attendance.attendance_page'))

    success, errors, count = parse_timetable_upload(file, get_academic_year_for_semester())
    if not success:
        flash('Timetable upload failed:<br>' + '<br>'.join(errors[:15]), 'error')
        return redirect(url_for('attendance.attendance_page'))

    flash(f'Timetable uploaded successfully. {count} weekly slot(s) saved/updated.', 'success')
    return redirect(url_for('attendance.attendance_page'))


@attendance_bp.route('/attendance/download-template')
@login_required
def download_attendance_template():
    semester_id = request.args.get('semester_id', type=int)
    subject_code = request.args.get('subject_code', '').strip().upper()
    division = clean_filter(request.args.get('division', '')) or 'ALL'
    batch = clean_filter(request.args.get('batch', '')) or 'ALL'
    start_date = parse_date(request.args.get('start_date'))
    end_date = parse_date(request.args.get('end_date'))

    if not semester_id or not subject_code or not start_date or not end_date:
        flash('Semester, subject, start date and end date are required for attendance template.', 'error')
        return redirect(url_for('attendance.attendance_page', semester_id=semester_id, subject_code=subject_code))

    academic_year = get_academic_year_for_semester(semester_id)
    subject = Subject.query.get(subject_code)
    if not subject:
        flash('Subject/activity not found.', 'error')
        return redirect(url_for('attendance.attendance_page', semester_id=semester_id))

    slots = timetable_slots_for_subject(semester_id, academic_year, subject_code, division, batch)
    generated_sessions = generate_dates_from_slots(slots, start_date, end_date)
    if not generated_sessions:
        flash('No timetable lectures found for this subject in the selected date range.', 'error')
        return redirect(url_for('attendance.attendance_page', semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    students = students_for_attendance(subject_code, semester_id, academic_year, division, batch)
    if not students:
        flash('No students found for selected subject/division/batch.', 'error')
        return redirect(url_for('attendance.attendance_page', semester_id=semester_id, subject_code=subject_code, division=division, batch=batch))

    meta = {
        'semester_id': semester_id,
        'academic_year': academic_year,
        'subject_code': subject_code,
        'subject_name': subject.subject_name,
        'division': division,
        'batch': batch,
    }
    buf, filename = generate_attendance_template(meta, students, generated_sessions)
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@attendance_bp.route('/attendance/upload', methods=['POST'])
@login_required
def upload_attendance():
    file = request.files.get('attendance_file')
    if not file or file.filename == '':
        flash('Please select filled attendance Excel file.', 'error')
        return redirect(url_for('attendance.attendance_page'))
    if not file.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx attendance files are accepted.', 'error')
        return redirect(url_for('attendance.attendance_page'))

    success, errors, count = parse_attendance_upload(file)
    if not success:
        flash('Attendance upload failed:<br>' + '<br>'.join(errors[:20]), 'error')
        return redirect(url_for('attendance.attendance_page'))

    flash(f'Attendance uploaded successfully. {count} date-wise entries saved and summary updated.', 'success')
    return redirect(url_for('attendance.attendance_page'))


@attendance_bp.route('/attendance/defaulters/<fmt>')
@login_required
def download_defaulters(fmt):
    semester_id = request.args.get('semester_id', type=int)
    subject_code = request.args.get('subject_code', '').strip().upper()
    threshold = request.args.get('threshold', default=75.0, type=float)
    if not semester_id or not subject_code:
        flash('Semester and subject are required.', 'error')
        return redirect(url_for('attendance.attendance_page'))

    academic_year = get_academic_year_for_semester(semester_id)
    rows = attendance_summary(subject_code, semester_id, academic_year)
    subject = Subject.query.get(subject_code)
    meta = {
        'semester_id': semester_id,
        'academic_year': academic_year,
        'subject_code': subject_code,
        'subject_name': subject.subject_name if subject else subject_code,
    }

    if fmt == 'excel':
        buf, filename = generate_defaulter_excel(meta, rows, threshold)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        buf, filename = generate_defaulter_pdf(meta, rows, threshold)
        mimetype = 'application/pdf'
    else:
        flash('Invalid defaulter report format.', 'error')
        return redirect(url_for('attendance.attendance_page', semester_id=semester_id, subject_code=subject_code))

    return send_file(buf, as_attachment=True, download_name=filename, mimetype=mimetype)
