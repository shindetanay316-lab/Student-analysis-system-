"""Keep legacy entry paths and new assessment paths mutually exclusive."""
from sqlalchemy import event
from sqlalchemy.orm import Session
from flask import request, redirect, url_for, abort
from flask_login import current_user
from models import db, Enrollment, Student, Semester
from completion_models import StudentTerm


@event.listens_for(Session, 'before_flush')
def snapshot_new_enrollment_placement(session, flush_context, instances):
    pending = {(r.prn,r.semester_id,r.academic_year) for r in session.new if isinstance(r,StudentTerm)}
    new_students = {r.prn:r for r in session.new if isinstance(r,Student)}
    new_terms = {(r.semester_id,r.academic_year) for r in session.new if isinstance(r,Semester)}
    for enrollment in list(session.new):
        if not isinstance(enrollment,Enrollment):
            continue
        key = (enrollment.prn,enrollment.semester_id,enrollment.academic_year)
        if key in pending or session.query(StudentTerm).filter_by(prn=key[0],semester_id=key[1],academic_year=key[2]).first():
            continue
        student = new_students.get(key[0]) or session.get(Student,key[0])
        if not student or ((key[1],key[2]) not in new_terms and not session.get(Semester,(key[1],key[2]))):
            continue
        session.add(StudentTerm(prn=key[0],semester_id=key[1],academic_year=key[2],
            division=student.division,batch=student.batch,origin='ROSTER_DEFAULT'))
        pending.add(key)


def register(app):
    @app.before_request
    def configured_entry_boundary():
        if not current_user.is_authenticated:
            return
        from teaching_access import SUBJECT_ENDPOINTS, require_assignment, context_year
        endpoints = (SUBJECT_ENDPOINTS - {e for e in SUBJECT_ENDPOINTS if e.startswith('attendance.')}) | {'workflow.subject_analysis','workflow.marks_preview'}
        if request.endpoint not in endpoints:
            return
        values = request.get_json(silent=True) if request.is_json else request.form if request.method=='POST' else request.args
        code = (values or {}).get('subject_code')
        if not code:
            return
        subject = session_subject(code)
        if not subject:
            return
        try:
            sem = int((values or {}).get('semester_id') or subject.semester_id)
        except (TypeError,ValueError):
            return
        from assessment_services import policy_for
        policy = policy_for(code,sem,context_year(sem))
        if policy:
            require_assignment(code,sem,policy.academic_year)
            if request.method=='POST':
                abort(400,'This subject uses an approved configurable assessment. Open Assessment rules and marks to submit or correct its scores.')
            return redirect(url_for('completion.assessment_detail',token=policy.token))


def session_subject(code):
    from models import Subject
    return db.session.get(Subject,code)
