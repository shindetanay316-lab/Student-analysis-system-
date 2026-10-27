"""One assignment policy for coursework pages, writes and file downloads."""
from flask import abort, has_request_context, request, session, redirect, url_for
from flask_login import current_user, logout_user
from sqlalchemy import exists, and_
from models import db, Subject
from teaching_models import TeachingAssignment, StaffAccessState

# These routes operate on one subject. Department reports and independent
# university PDF analysis have their own read scope and need no assignment.
SUBJECT_ENDPOINTS={
    'ct1_page','download_ct1_template','upload_ct1','download_ct1_report','download_internal_report',
    'external.external_marks_page','external.save_external_marks','external.lock_external_subject',
    'external.upload_external','external.download_external_template','external.download_external_report_excel',
    'external.download_external_report_pdf','external.external_stats',
    'lab.lab_marks_page','lab.download_lab_template','lab.upload_lab',
    'lab.download_lab_report_excel','lab.download_lab_report_pdf',
    'attendance.attendance_page','attendance.download_attendance_template','attendance.upload_attendance',
    'attendance.download_defaulters',
}
WRITE_ENDPOINTS={'upload_ct1','external.save_external_marks','external.lock_external_subject',
    'external.upload_external','lab.upload_lab','attendance.upload_attendance'}
DEPARTMENT_REPORT_ENDPOINTS={'download_ct1_summary_excel','download_ct1_summary_pdf','external.download_sgpa_cgpa_excel'}


def payload():
    return request.get_json(silent=True) if request.is_json else request.form if request.method=='POST' else request.args


def context_year(semester_id):
    raw=(payload() or {}).get('academic_year','') if has_request_context() else ''
    if raw:return str(raw).strip()
    from academic_utils import get_academic_year_for_semester
    return get_academic_year_for_semester(semester_id)


def permitted(user,code,semester_id,academic_year):
    if user.role=='ADMIN':return True
    if user.role!='TEACHER' or not user.is_active:return False
    return db.session.scalar(db.select(TeachingAssignment.id).join(Subject).where(
        TeachingAssignment.teacher_id==user.user_id,TeachingAssignment.subject_code==code,
        TeachingAssignment.semester_id==semester_id,TeachingAssignment.academic_year==academic_year,
        TeachingAssignment.is_active.is_(True),Subject.is_active.is_(True)).limit(1)) is not None


def require_assignment(code,semester_id,academic_year):
    if not current_user.is_authenticated:abort(401)
    if not permitted(current_user,code,semester_id,academic_year):
        abort(403,'This subject is not assigned to you for the selected academic year and semester.')


def scope_subjects(query,semester_id=None):
    if not has_request_context() or not current_user.is_authenticated or current_user.role=='ADMIN':return query
    if request.endpoint in DEPARTMENT_REPORT_ENDPOINTS:return query
    year=context_year(semester_id)
    return query.filter(exists().where(and_(
        TeachingAssignment.teacher_id==current_user.user_id,TeachingAssignment.subject_code==Subject.subject_code,
        TeachingAssignment.semester_id==Subject.semester_id,TeachingAssignment.academic_year==year,
        TeachingAssignment.is_active.is_(True))))


def record_login(user):
    state=db.session.get(StaffAccessState,user.user_id)
    session['staff_credential_version']=state.credential_version if state else 0


def register_access(app):
    @app.before_request
    def enforce_staff_access():
        if not current_user.is_authenticated:return
        state=db.session.get(StaffAccessState,current_user.user_id)
        if not current_user.is_active or session.get('staff_credential_version',0)!=(state.credential_version if state else 0):
            logout_user();session.clear()
            return redirect(url_for('login'))
        endpoint=request.endpoint or ''
        if state and state.must_change_password and endpoint not in {'teaching.password','logout','static'}:
            return redirect(url_for('teaching.password'))
        if request.blueprint=='teaching' and request.method=='POST':
            from result_data import csrf
            csrf.protect()
        if current_user.role!='TEACHER':return
        if endpoint in SUBJECT_ENDPOINTS:
            data=payload() or {};code=str(data.get('subject_code','')).strip()
            raw=data.get('semester_id')
            try:semester_id=int(raw) if raw else None
            except (ValueError,TypeError):abort(400,'Invalid semester.')
            # Attendance imports use their workbook metadata, checked again at
            # the parser boundary before sessions or attendance entries exist.
            if endpoint=='attendance.upload_attendance':
                from result_data import csrf
                csrf.protect()
                return
            if code:
                subject=db.session.get(Subject,code)
                if not subject:abort(404)
                semester_id=semester_id or subject.semester_id
                if subject.semester_id!=semester_id:abort(403)
                require_assignment(code,semester_id,context_year(semester_id))
            elif endpoint in WRITE_ENDPOINTS:abort(400,'Select an assigned subject.')
            if request.method=='POST':
                from result_data import csrf
                csrf.protect()
