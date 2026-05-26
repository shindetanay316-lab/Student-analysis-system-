import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from config import Config
from models import db, Student, Subject, Semester, TheoryMarks, Enrollment

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

    db.init_app(app)

    from routes_external import external_bp
    app.register_blueprint(external_bp)

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


class _ET:
    def __init__(self, d):
        self.value = d['value']
        self.label = d['label']


app = create_app()

# ══════════════════════════════════════════════════════════════
#  DASHBOARD — INDEX ROUTE
#  Paste immediately after:  app = create_app()
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    from models import Student, Subject, Semester, TheoryMarks, Enrollment

    academic_map = {
        3: '2024-25', 4: '2024-25',
        5: '2025-26', 6: '2025-26',
        7: '2026-27', 8: '2026-27',
    }

    # Active semester
    active_sem = Semester.query.filter_by(is_active=True).first()
    academic_year = app.config.get('CURRENT_ACADEMIC_YEAR', '2024-25')

    # Counts for stat cards
    student_count = Student.query.count()
    subject_count = Subject.query.filter(
        Subject.is_audit == False,
        Subject.subject_type.in_(['THEORY', 'LAB'])
    ).count()

    # Theory subjects for active semester
    theory_subjects = []
    ct1_lock = {}
    locked_count = 0

    if active_sem:
        theory_subjects = Subject.query.filter_by(
            semester_id  = active_sem.semester_id,
            subject_type = 'THEORY',
            is_audit     = False
        ).order_by(Subject.subject_code).all()

        sem_academic_year = academic_map.get(
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

    all_semesters = Semester.query.order_by(Semester.semester_id).all()

    return render_template(
        'index.html',
        academic_year   = academic_year,
        active_sem      = active_sem,
        all_semesters   = all_semesters,
        student_count   = student_count,
        subject_count   = subject_count,
        theory_subjects = theory_subjects,
        ct1_lock        = ct1_lock,
        locked_count    = locked_count,
    )

@app.route('/ct1')
def ct1_page():

    selected_semester = request.args.get(
        'semester_id',
        type=int
    )

    academic_map = {
        3: '2024-25',
        4: '2024-25',
        5: '2025-26',
        6: '2025-26',
        7: '2026-27',
        8: '2026-27'
    }

    academic_year = academic_map.get(
        selected_semester,
        '2024-25'
    )

    all_semesters = Semester.query.order_by(
        Semester.semester_id
    ).all()

    exam_types = [_ET(e) for e in EXAM_TYPES]

    selected_exam = request.args.get(
        'exam_type',
        ''
    ).strip().upper()

    selected_code = request.args.get(
        'subject_code',
        ''
    ).strip()

    subjects = []
    lock_status = {}
    selected_exam_label = ''

    if selected_semester and selected_exam:
        subjects = Subject.query.filter_by(
            semester_id  = selected_semester,
            subject_type = 'THEORY',
            is_audit     = False
        ).order_by(Subject.subject_code).all()

        for et in EXAM_TYPES:
            if et['value'] == selected_exam:
                selected_exam_label = et['label']
                break

        for subj in subjects:
            key = subj.subject_code + '_' + selected_exam
            lock_status[key] = _is_marks_locked(
                subj.subject_code, academic_year, selected_exam
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
    )


@app.route('/download-ct1-template')
def download_ct1_template():
    from excel_utils import generate_ct1_template

    subject_code    = request.args.get('subject_code', '').strip()
    subject_teacher = request.args.get('subject_teacher', '').strip()
    exam_date       = request.args.get('exam_date', '').strip()
    exam_type       = request.args.get('exam_type', 'CT1').strip().upper()
    semester_id     = request.args.get('semester_id', type=int)
    academic_map = {
        3: '2024-25',
        4: '2024-25',
        5: '2025-26',
        6: '2025-26',
        7: '2026-27',
        8: '2026-27'
    }

    academic_year = academic_map.get(
        semester_id,
        '2024-25'
    )
    if not subject_code:
        flash('Please select a subject first.', 'error')
        return redirect(url_for('ct1_page'))

    subj = Subject.query.get(subject_code)
    if not subj:
        flash('Subject not found.', 'error')
        return redirect(url_for('ct1_page'))

    enrolled = (
    db.session.query(Student)
    .join(Enrollment, Enrollment.prn == Student.prn)
    .filter(
        Enrollment.subject_code == subject_code,
        Enrollment.semester_id == semester_id,
        Enrollment.academic_year == academic_year
    )
    .order_by(Student.prn)
    .all()
    )

    if not enrolled:
        flash('No students enrolled in this subject.', 'error')
        return redirect(url_for('ct1_page'))

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
    }

    buf, filename = generate_ct1_template(meta, enrolled)
    return send_file(
        buf,
        as_attachment = True,
        download_name = filename,
        mimetype      = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/upload-ct1', methods=['POST'])
def upload_ct1():
    from excel_utils import parse_ct1_upload

    subject_code  = request.form.get('subject_code', '').strip()
    exam_type     = request.form.get('exam_type', 'CT1').strip().upper()
    semester_id   = request.form.get('semester_id', type=int)
    academic_map = {
        3: '2024-25',
        4: '2024-25',
        5: '2025-26',
        6: '2025-26',
        7: '2026-27',
        8: '2026-27'
    }

    academic_year = academic_map.get(
        semester_id,
        '2024-25'
    )
    max_marks     = EXAM_MAX_MARKS.get(exam_type, 10)

    if not subject_code:
        flash('Subject code missing.', 'error')
        return redirect(url_for('ct1_page'))

    if _is_marks_locked(subject_code, academic_year, exam_type):
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
def download_ct1_report(fmt):
    subject_code    = request.args.get('subject_code', '').strip()
    subject_teacher = request.args.get('subject_teacher', '').strip()
    exam_date       = request.args.get('exam_date', '').strip()
    exam_type       = request.args.get('exam_type', 'CT1').strip().upper()
    semester_id     = request.args.get('semester_id', type=int)

    academic_map = {
        3: '2024-25',
        4: '2024-25',
        5: '2025-26',
        6: '2025-26',
        7: '2026-27',
        8: '2026-27'
    }

    academic_year = academic_map.get(
        semester_id,
        '2024-25'
    )

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

    # Column map
    col_map = {
        'CT1': TheoryMarks.ct1,
        'CT2': TheoryMarks.ct2,
        'ASSIGNMENT': TheoryMarks.assignment,
        'MIDSEM': TheoryMarks.midsem,
    }

    marks_col = col_map.get(exam_type, TheoryMarks.ct1)

    # Fetch ALL enrolled students
    enrolled_students = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year
        )
        .order_by(Student.prn)
        .all()
    )

    if not enrolled_students:
        flash('No students enrolled in this subject.', 'error')
        return redirect(url_for(
            'ct1_page',
            semester_id=semester_id,
            exam_type=exam_type,
            subject_code=subject_code
        ))

    # Get uploaded marks
    marks_rows = TheoryMarks.query.filter_by(
        subject_code=subject_code,
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

def _is_marks_locked(subject_code, academic_year, exam_type):
    col_map = {
        'CT1':        TheoryMarks.ct1,
        'CT2':        TheoryMarks.ct2,
        'ASSIGNMENT': TheoryMarks.assignment,
        'MIDSEM':     TheoryMarks.midsem,
    }
    col = col_map.get(exam_type.upper(), TheoryMarks.ct1)
    exists = TheoryMarks.query.filter(
        TheoryMarks.subject_code  == subject_code,
        TheoryMarks.academic_year == academic_year,
        col.isnot(None)
    ).first()
    return exists is not None
# ══════════════════════════════════════════════════════════════
#  DEPARTMENT SUMMARY ROUTES
#  Append before:  if __name__ == '__main__':
# ══════════════════════════════════════════════════════════════

@app.route('/download-ct1-summary-excel')
def download_ct1_summary_excel():
    from summary_utils import build_summary_data
    from excel_utils   import generate_ct1_summary_excel

    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        flash('Please select a semester.', 'error')
        return redirect(url_for('index'))

    academic_map = {
        3: '2024-25', 4: '2024-25',
        5: '2025-26', 6: '2025-26',
        7: '2026-27', 8: '2026-27',
    }
    academic_year = academic_map.get(semester_id, '2024-25')

    exam_type   = request.args.get('exam_type',       'CT1').strip().upper()
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
            'No subjects found for the selected semester. '
            'Check SEMESTER_SUBJECTS in summary_utils.py.',
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
def download_ct1_summary_pdf():
    from summary_utils import build_summary_data
    from pdf_utils     import generate_ct1_summary_pdf

    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        flash('Please select a semester.', 'error')
        return redirect(request.referrer or '/')

    academic_map = {
        3: '2024-25', 4: '2024-25',
        5: '2025-26', 6: '2025-26',
        7: '2026-27', 8: '2026-27',
    }
    academic_year = academic_map.get(semester_id, '2024-25')

    exam_type   = request.args.get('exam_type',   'CT1').strip().upper()
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
            'No subjects found for the selected semester. '
            'Check SEMESTER_SUBJECTS in summary_utils.py.',
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
def download_internal_report(fmt):

    from report_utils import build_internal_data

    subject_code = request.args.get('subject_code', '').strip()
    semester_id = request.args.get('semester_id', type=int)

    if not subject_code:
        flash('Please select subject.', 'error')
        return redirect(url_for('ct1_page'))

    academic_map = {
        3: '2024-25',
        4: '2024-25',
        5: '2025-26',
        6: '2025-26',
        7: '2026-27',
        8: '2026-27'
    }

    academic_year = academic_map.get(
        semester_id,
        '2024-25'
    )

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