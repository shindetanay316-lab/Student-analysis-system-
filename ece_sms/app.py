import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, Student, Subject, Semester, TheoryMarks, Enrollment, User
from batch_utils import (
    clean_filter, apply_student_batch_filters, batch_label,
    DIVISION_OPTIONS, BATCH_OPTIONS
)
from academic_utils import (
    get_academic_year_for_semester,
    visible_theory_subjects_query,
    visible_lab_subjects_query,
    attendance_subjects_query,
)
from stability_utils import clean_exam_type


login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please login first.'
    login_manager.login_message_category = 'error'

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None

    from routes_external import external_bp
    app.register_blueprint(external_bp)

    from routes_lab import lab_bp
    app.register_blueprint(lab_bp)

    from routes_electives import electives_bp
    app.register_blueprint(electives_bp)

    from routes_batches import batches_bp
    app.register_blueprint(batches_bp)

    from routes_subjects import subjects_bp
    app.register_blueprint(subjects_bp)

    from routes_attendance import attendance_bp
    app.register_blueprint(attendance_bp)

    from routes_analytics import analytics_bp
    app.register_blueprint(analytics_bp)

    return app

# ══════════════════════════════════════════════
#  CT1 / INTERNAL MARKS MODULE
# ══════════════════════════════════════════════

EXAM_TYPES = [
    {'value': 'CT1',        'label': 'Class Test 1'},
    {'value': 'CT2',        'label': 'Class Test 2'},
    {'value': 'MIDSEM',     'label': 'Mid Semester Examination'},
    {'value': 'ASSIGNMENT', 'label': 'Assignment'},
]

EXAM_MAX_MARKS = {
    'CT1': 10, 'CT2': 10, 'ASSIGNMENT': 10, 'MIDSEM': 20
}

VALID_EXAM_TYPES = {e['value'] for e in EXAM_TYPES}


class _ET:
    def __init__(self, d):
        self.value = d['value']
        self.label = d['label']


app = create_app()


def _visible_marks_subject_filter(semester_id):
    """Subjects shown in marks pages using the shared database-driven rule."""
    return visible_theory_subjects_query(semester_id)


def _academic_year_for_semester(semester_id=None, fallback='2024-25'):
    return get_academic_year_for_semester(semester_id, fallback)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))

        if not user.is_active:
            flash('This account is inactive.', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash('Login successful.', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════
#  DASHBOARD — INDEX ROUTE
# ══════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    # Active semester
    active_sem = Semester.query.filter_by(is_active=True).first()
    academic_year = _academic_year_for_semester(
        active_sem.semester_id if active_sem else None,
        app.config.get('CURRENT_ACADEMIC_YEAR', '2024-25')
    )

    # Counts for stat cards
    student_count = Student.query.count()
    subject_count = Subject.query.filter(
        Subject.is_audit == False,
        Subject.is_active == True,
        Subject.subject_type.in_(['THEORY', 'LAB'])
    ).count()

    # Theory subjects for active semester
    theory_subjects = []
    ct1_lock = {}
    locked_count = 0

    if active_sem:
        theory_subjects = _visible_marks_subject_filter(active_sem.semester_id).all()

        sem_academic_year = _academic_year_for_semester(
            active_sem.semester_id, academic_year
        )

        for subj in theory_subjects:
            locked = TheoryMarks.query.filter(
                TheoryMarks.subject_code  == subj.subject_code,
                TheoryMarks.academic_year == sem_academic_year,
                TheoryMarks.ct1.isnot(None)
            ).first() is not None
            ct1_lock[subj.subject_code] = locked
            if locked:
                locked_count += 1

    lab_subjects = []
    attendance_count = 0
    if active_sem:
        lab_subjects = visible_lab_subjects_query(active_sem.semester_id).all()
        attendance_count = attendance_subjects_query(active_sem.semester_id).count()

    all_semesters = Semester.query.order_by(Semester.semester_id).all()

    return render_template(
        'index.html',
        academic_year   = academic_year,
        active_sem      = active_sem,
        all_semesters   = all_semesters,
        student_count   = student_count,
        subject_count   = subject_count,
        theory_subjects = theory_subjects,
        lab_subjects    = lab_subjects,
        lab_count       = len(lab_subjects),
        attendance_count = attendance_count,
        ct1_lock        = ct1_lock,
        locked_count    = locked_count,
    )


@app.route('/api/theory-subjects')
@login_required
def api_theory_subjects():
    """Return visible theory subjects for dashboard dropdowns.

    Used by the dashboard report forms so changing the semester refreshes
    the subject list instead of leaving old active-semester subjects selected.
    """
    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        return jsonify({'subjects': []})

    subjects = visible_theory_subjects_query(semester_id).all()
    return jsonify({
        'subjects': [
            {
                'subject_code': subj.subject_code,
                'subject_name': subj.subject_name,
                'credits': int(subj.credits or 0),
                'category': subj.category or '',
            }
            for subj in subjects
        ]
    })


@app.route('/api/lab-subjects')
@login_required
def api_lab_subjects():
    """Return visible lab/project subjects for future dashboard dropdowns."""
    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        return jsonify({'subjects': []})

    subjects = visible_lab_subjects_query(semester_id).all()
    return jsonify({
        'subjects': [
            {
                'subject_code': subj.subject_code,
                'subject_name': subj.subject_name,
                'credits': int(subj.credits or 0),
                'category': subj.category or '',
            }
            for subj in subjects
        ]
    })


@app.route('/set-active-semester', methods=['POST'])
@login_required
def set_active_semester():
    """Admin helper to set exactly one active semester from dashboard."""
    if getattr(current_user, 'role', None) != 'ADMIN':
        flash('Only admin can change the active semester.', 'error')
        return redirect(url_for('index'))

    semester_id = request.form.get('semester_id', type=int)
    academic_year = request.form.get('academic_year', '').strip()

    if not semester_id or not academic_year:
        flash('Please select a valid semester.', 'error')
        return redirect(url_for('index'))

    sem = Semester.query.filter_by(
        semester_id=semester_id,
        academic_year=academic_year
    ).first()
    if not sem:
        flash('Selected semester row was not found.', 'error')
        return redirect(url_for('index'))

    Semester.query.update({Semester.is_active: False})
    sem.is_active = True
    db.session.commit()

    flash(f'Active semester changed to Semester {semester_id} ({academic_year}).', 'success')
    return redirect(url_for('index'))


@app.route('/ct1')
@login_required
def ct1_page():

    selected_semester = request.args.get(
        'semester_id',
        type=int
    )
    academic_year = _academic_year_for_semester(selected_semester)

    all_semesters = Semester.query.order_by(
        Semester.semester_id
    ).all()

    exam_types = [_ET(e) for e in EXAM_TYPES]

    raw_exam = request.args.get(
        'exam_type',
        ''
    ).strip().upper()
    selected_exam = clean_exam_type(raw_exam, VALID_EXAM_TYPES, default='') if raw_exam else ''

    selected_code = request.args.get(
        'subject_code',
        ''
    ).strip()

    selected_division = clean_filter(request.args.get('division', ''))
    selected_batch = clean_filter(request.args.get('batch', ''))

    subjects = []
    lock_status = {}
    selected_exam_label = ''

    if selected_semester and selected_exam:
        subjects = _visible_marks_subject_filter(selected_semester).all()

        for et in EXAM_TYPES:
            if et['value'] == selected_exam:
                selected_exam_label = et['label']
                break

        for subj in subjects:
            key = subj.subject_code + '_' + selected_exam
            lock_status[key] = _is_marks_locked(
                subj.subject_code, academic_year, selected_exam, selected_semester
            )

    return render_template(
        'ct1.html',
        subjects             = subjects,
        lock_status          = lock_status,
        academic_year        = academic_year,
        all_semesters        = all_semesters,
        exam_types           = exam_types,
        selected_semester    = selected_semester,
        selected_exam        = selected_exam,
        selected_exam_label  = selected_exam_label,
        selected_code        = selected_code,
        selected_division    = selected_division,
        selected_batch       = selected_batch,
        division_options     = DIVISION_OPTIONS,
        batch_options        = BATCH_OPTIONS,
    )


@app.route('/download-ct1-template')
@login_required
def download_ct1_template():
    from excel_utils import generate_ct1_template

    subject_code    = request.args.get('subject_code', '').strip()
    subject_teacher = request.args.get('subject_teacher', '').strip()
    exam_date       = request.args.get('exam_date', '').strip()
    exam_type       = clean_exam_type(request.args.get('exam_type', 'CT1'), VALID_EXAM_TYPES)
    semester_id     = request.args.get('semester_id', type=int)
    division        = clean_filter(request.args.get('division', ''))
    batch           = clean_filter(request.args.get('batch', ''))
    academic_year = _academic_year_for_semester(semester_id)
    if not subject_code:
        flash('Please select a subject first.', 'error')
        return redirect(url_for('ct1_page'))

    subj = Subject.query.get(subject_code)
    if not subj:
        flash('Subject not found.', 'error')
        return redirect(url_for('ct1_page'))

    enrolled_query = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year
        )
    )
    enrolled_query = apply_student_batch_filters(enrolled_query, Student, division, batch)
    enrolled = enrolled_query.order_by(Student.prn).all()

    if not enrolled:
        flash('No students found for this subject and selected division/batch filter.', 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id=semester_id,
            exam_type=exam_type,
            subject_code=subject_code,
            division=division,
            batch=batch,
        ))

    exam_label = next(
        (e['label'] for e in EXAM_TYPES if e['value'] == exam_type),
        exam_type
    )
    max_marks = EXAM_MAX_MARKS.get(exam_type, 10)

    meta = {
        'subject_code':    subject_code,
        'subject_name':    subj.subject_name,
        'subject_teacher': subject_teacher or 'N/A',
        'exam_date':       exam_date or 'N/A',
        'exam_type':       exam_type,
        'exam_label':      exam_label,
        'max_marks':       max_marks,
        'academic_year':   academic_year,
        'semester_id':     semester_id,
        'division':        division,
        'batch':           batch,
        'batch_label':     batch_label(division, batch),
    }

    buf, filename = generate_ct1_template(meta, enrolled)
    return send_file(
        buf,
        as_attachment = True,
        download_name = filename,
        mimetype      = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/upload-ct1', methods=['POST'])
@login_required
def upload_ct1():
    from excel_utils import parse_ct1_upload

    subject_code  = request.form.get('subject_code', '').strip()
    exam_type     = clean_exam_type(request.form.get('exam_type', 'CT1'), VALID_EXAM_TYPES)
    semester_id   = request.form.get('semester_id', type=int)
    academic_year = _academic_year_for_semester(semester_id)
    max_marks     = EXAM_MAX_MARKS.get(exam_type, 10)

    if not subject_code:
        flash('Subject code missing.', 'error')
        return redirect(url_for('ct1_page'))

    if _is_marks_locked(subject_code, academic_year, exam_type, semester_id):
        flash(
            'Marks have been successfully submitted and locked. '
            'Further modifications are restricted to preserve academic record integrity.',
            'locked'
        )
        return redirect(url_for(
            'ct1_page',
            semester_id   = semester_id,
            exam_type     = exam_type,
            subject_code  = subject_code
        ))

    file = request.files.get('ct1_file')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id  = semester_id,
            exam_type    = exam_type,
            subject_code = subject_code
        ))

    if not file.filename.endswith('.xlsx'):
        flash('Only .xlsx files are accepted.', 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id  = semester_id,
            exam_type    = exam_type,
            subject_code = subject_code
        ))

    success, errors, count = parse_ct1_upload(
        file_obj      = file,
        subject_code  = subject_code,
        semester_id   = semester_id,
        academic_year = academic_year,
        exam_type     = exam_type,
        max_marks     = max_marks
    )

    if not success:
        error_msgs = [f"Row {e['row']}: {e['col']} — {e['msg']}" for e in errors]
        flash('Upload failed. Errors:<br>' + '<br>'.join(error_msgs), 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id  = semester_id,
            exam_type    = exam_type,
            subject_code = subject_code
        ))

    flash(
        f'Marks submitted successfully for {count} students. '
        f'This record is now permanently locked.',
        'success'
    )
    return redirect(url_for(
        'ct1_page',
        semester_id  = semester_id,
        exam_type    = exam_type,
        subject_code = subject_code
    ))

@app.route('/download-ct1-report/<fmt>')
@login_required
def download_ct1_report(fmt):
    subject_code    = request.args.get('subject_code', '').strip()
    subject_teacher = request.args.get('subject_teacher', '').strip()
    exam_date       = request.args.get('exam_date', '').strip()
    exam_type       = clean_exam_type(request.args.get('exam_type', 'CT1'), VALID_EXAM_TYPES)
    semester_id     = request.args.get('semester_id', type=int)
    division        = clean_filter(request.args.get('division', ''))
    batch           = clean_filter(request.args.get('batch', ''))
    academic_year = _academic_year_for_semester(semester_id)

    if not subject_code:
        flash('Please select a subject.', 'error')
        return redirect(url_for('ct1_page'))

    subj = Subject.query.get(subject_code)
    if not subj:
        flash('Subject not found.', 'error')
        return redirect(url_for('ct1_page'))

    exam_label = next(
        (e['label'] for e in EXAM_TYPES if e['value'] == exam_type),
        exam_type
    )

    # Fetch enrolled students, optionally filtered by division/batch
    enrolled_query = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year
        )
    )
    enrolled_query = apply_student_batch_filters(enrolled_query, Student, division, batch)
    enrolled_students = enrolled_query.order_by(Student.prn).all()

    if not enrolled_students:
        flash('No students found for this subject and selected division/batch filter.', 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id=semester_id,
            exam_type=exam_type,
            subject_code=subject_code,
            division=division,
            batch=batch,
        ))

    # Get uploaded marks
    marks_rows = TheoryMarks.query.filter_by(
        subject_code=subject_code,
        semester_id=semester_id,
        academic_year=academic_year
    ).all()

    marks_lookup = {
        m.prn: getattr(m, exam_type.lower(), None)
        for m in marks_rows
    }

    meta = {
        'subject_code': subject_code,
        'subject_name': subj.subject_name,
        'subject_teacher': subject_teacher or 'N/A',
        'exam_date': exam_date or 'N/A',
        'exam_type': exam_type,
        'exam_label': exam_label,
        'max_marks': EXAM_MAX_MARKS.get(exam_type, 10),
        'academic_year': academic_year,
        'semester_id': semester_id,
        'division': division,
        'batch': batch,
        'batch_label': batch_label(division, batch),
    }

    data = []

    for sr, stu in enumerate(enrolled_students, 1):
        mark_val = marks_lookup.get(stu.prn)

        data.append({
            'sr': sr,
            'prn': stu.prn,
            'name': stu.name,
            'ct1': float(mark_val) if mark_val is not None else None
        })

    if fmt == 'pdf':
        from pdf_utils import generate_ct1_pdf_report
        buf, filename = generate_ct1_pdf_report(meta, data)
        mimetype = 'application/pdf'

    elif fmt == 'excel':
        from excel_utils import generate_ct1_excel_report
        buf, filename = generate_ct1_excel_report(meta, data)
        mimetype = (
            'application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet'
        )

    else:
        flash('Invalid format.', 'error')
        return redirect(url_for('ct1_page'))

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

def _is_marks_locked(subject_code, academic_year, exam_type, semester_id=None):
    col_map = {
        'CT1':        TheoryMarks.ct1,
        'CT2':        TheoryMarks.ct2,
        'ASSIGNMENT': TheoryMarks.assignment,
        'MIDSEM':     TheoryMarks.midsem,
    }
    col = col_map.get(exam_type.upper(), TheoryMarks.ct1)
    query = TheoryMarks.query.filter(
        TheoryMarks.subject_code  == subject_code,
        TheoryMarks.academic_year == academic_year,
        col.isnot(None)
    )
    if semester_id is not None:
        query = query.filter(TheoryMarks.semester_id == semester_id)

    return query.first() is not None
# ══════════════════════════════════════════════════════════════
#  DEPARTMENT SUMMARY ROUTES
#  Append before:  if __name__ == '__main__':
# ══════════════════════════════════════════════════════════════

@app.route('/download-ct1-summary-excel')
@login_required
def download_ct1_summary_excel():
    from summary_utils import build_summary_data
    from excel_utils   import generate_ct1_summary_excel

    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        flash('Please select a semester.', 'error')
        return redirect(url_for('index'))

    academic_year = _academic_year_for_semester(semester_id)

    exam_type   = clean_exam_type(request.args.get('exam_type', 'CT1'), VALID_EXAM_TYPES)
    date_from   = request.args.get('date_from',       '').strip()
    date_to     = request.args.get('date_to',         '').strip()
    coordinator = request.args.get('coordinator',     '').strip()
    dean        = request.args.get('dean',            '').strip()
    principal   = request.args.get('principal',       '').strip()

    try:
        summary_data = build_summary_data(
            semester_id   = semester_id,
            exam_type     = exam_type,
            academic_year = academic_year,
            date_from     = date_from or None,
            date_to       = date_to   or None,
            coordinator   = coordinator,
            dean          = dean,
            principal     = principal,
        )
    except Exception as e:
        flash(f'Summary generation failed: {str(e)}', 'error')
        return redirect(request.referrer or '/')

    if not summary_data['subjects']:
        flash(
            'No visible theory subjects found for the selected semester.',
            'error'
        )
        return redirect(request.referrer or '/')

    buf, filename = generate_ct1_summary_excel(summary_data)
    return send_file(
        buf,
        as_attachment = True,
        download_name = filename,
        mimetype      = (
            'application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet'
        )
    )


@app.route('/download-ct1-summary-pdf')
@login_required
def download_ct1_summary_pdf():
    from summary_utils import build_summary_data
    from pdf_utils     import generate_ct1_summary_pdf

    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        flash('Please select a semester.', 'error')
        return redirect(request.referrer or '/')

    academic_year = _academic_year_for_semester(semester_id)

    exam_type   = clean_exam_type(request.args.get('exam_type', 'CT1'), VALID_EXAM_TYPES)
    date_from   = request.args.get('date_from',   '').strip()
    date_to     = request.args.get('date_to',     '').strip()
    coordinator = request.args.get('coordinator', '').strip()
    dean        = request.args.get('dean',        '').strip()
    principal   = request.args.get('principal',   '').strip()

    try:
        summary_data = build_summary_data(
            semester_id   = semester_id,
            exam_type     = exam_type,
            academic_year = academic_year,
            date_from     = date_from or None,
            date_to       = date_to   or None,
            coordinator   = coordinator,
            dean          = dean,
            principal     = principal,
        )
    except Exception as e:
        flash(f'Summary generation failed: {str(e)}', 'error')
        return redirect(request.referrer or '/')

    if not summary_data['subjects']:
        flash(
            'No visible theory subjects found for the selected semester.',
            'error'
        )
        return redirect(request.referrer or '/')

    buf, filename = generate_ct1_summary_pdf(summary_data)
    return send_file(
        buf,
        as_attachment = True,
        download_name = filename,
        mimetype      = 'application/pdf'
    )

@app.route('/download-internal-report/<fmt>')
@login_required
def download_internal_report(fmt):

    from report_utils import build_internal_data

    subject_code = request.args.get('subject_code', '').strip()
    semester_id = request.args.get('semester_id', type=int)

    if not subject_code:
        flash('Please select subject.', 'error')
        return redirect(url_for('ct1_page'))
    academic_year = _academic_year_for_semester(semester_id)

    data, meta = build_internal_data(
        subject_code,
        semester_id,
        academic_year
    )

    if fmt == 'excel':
        from excel_utils import generate_internal_excel
        buf, filename = generate_internal_excel(meta, data)

        mimetype = (
            'application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet'
        )

    elif fmt == 'pdf':
        from pdf_utils import generate_internal_pdf
        buf, filename = generate_internal_pdf(meta, data)

        mimetype = 'application/pdf'

    else:
        flash('Invalid format.', 'error')
        return redirect(url_for('ct1_page'))

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )




if __name__ == '__main__':
    app.run(debug=True)