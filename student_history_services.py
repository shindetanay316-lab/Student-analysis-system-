"""Unified read model with clearly separated local calculations and official evidence."""
from flask import abort
from flask_login import current_user
from sqlalchemy import exists, and_, update
from models import db, Student, Enrollment, Subject, AttendanceSession, AttendanceEntry
from teaching_models import TeachingAssignment
from academic_link_models import UniversityLinkedResult, StudentPortfolio
from curriculum_models import StudentCurriculumTerm
from coursework_models import MarkRevision
from routes_teaching import audit
from workflow_models import now

PORTFOLIO_FIELDS = {
    'interests': ('Interests', 1500), 'skills': ('Skills', 2000),
    'projects': ('Projects', 3000), 'certifications': ('Certifications', 2000),
    'achievements': ('Achievements and activities', 2000), 'goals': ('Learning and career goals', 1500),
}


def allowed_contexts():
    if current_user.role == 'ADMIN':
        return None
    if current_user.role != 'TEACHER':
        abort(403)
    return {(r.subject_code, r.semester_id, r.academic_year) for r in TeachingAssignment.query.join(Subject).filter(
        TeachingAssignment.teacher_id == current_user.user_id, TeachingAssignment.is_active.is_(True), Subject.is_active.is_(True))}


def student_query():
    allowed = allowed_contexts()
    if allowed is None:
        return Student.query
    if not allowed:
        return Student.query.filter(db.false())
    return Student.query.filter(exists().where(and_(Enrollment.prn == Student.prn,
        db.or_(*[and_(Enrollment.subject_code == code, Enrollment.semester_id == sem, Enrollment.academic_year == year)
            for code, sem, year in sorted(allowed)]))))


def history(prn):
    student = student_query().filter(Student.prn == prn).first()
    if not student:
        abort(404, 'Student not found in your permitted teaching scope.')
    allowed = allowed_contexts()
    enrollments = Enrollment.query.filter_by(prn=prn).order_by(Enrollment.academic_year, Enrollment.semester_id, Enrollment.subject_code).all()
    enrollments = [r for r in enrollments if allowed is None or (r.subject_code, r.semester_id, r.academic_year) in allowed]
    terms = sorted({(r.semester_id, r.academic_year) for r in enrollments}, key=lambda t: (t[1], t[0]))
    from final_result_utils import build_student_semester_result, calculate_cgpa_for_student
    from coursework_services import effective_states
    from attendance_services import report_rows
    local, summaries, attendance = [], [], []
    for semester, year in terms:
        semester_result = build_student_semester_result(prn, semester, year)
        if allowed is None:
            summaries.append(dict(semester_id=semester, academic_year=year,
                sgpa=semester_result.get('sgpa'), credits=semester_result.get('total_credits'),
                earned=semester_result.get('credits_earned'), result=semester_result.get('result'), complete=semester_result.get('is_complete')))
        scoped_codes = {r.subject_code for r in enrollments if (r.semester_id, r.academic_year) == (semester, year)}
        for row in semester_result.get('subjects', []):
            if row['subject_code'] not in scoped_codes:
                continue
            c = dict(subject_code=row['subject_code'], semester_id=semester, academic_year=year, division='ALL', batch='ALL')
            states = {component: state for (p, category, component), state in effective_states(c).items() if p == prn}
            local.append(dict(row, semester_id=semester, academic_year=year, states=states))
        # Includes audit/attendance-only subjects even when they are not gradable.
        for code in sorted(scoped_codes):
            c = dict(subject_code=code, semester_id=semester, academic_year=year, division='ALL', batch='ALL')
            data = next((r for r in report_rows(c) if r['student'].prn == prn), None)
            if data:
                attendance.append(dict(semester_id=semester, academic_year=year, subject_code=code,
                    subject_name=db.session.get(Subject, code).subject_name,
                    **{k: data[k] for k in ('total', 'present', 'leave', 'official', 'percentage', 'conflicts')}))
    official = UniversityLinkedResult.query.filter_by(prn=prn).order_by(UniversityLinkedResult.id.desc()).all()
    official = [r for r in official if allowed is None or (r.subject_code, r.semester_id, r.academic_year) in allowed]
    latest = set()
    official_rows = []
    for row in official:
        revised = row.attempt_key in latest
        latest.add(row.attempt_key)
        official_rows.append(dict(record=row, superseded=revised))
    curriculum = StudentCurriculumTerm.query.filter_by(prn=prn).order_by(StudentCurriculumTerm.academic_year, StudentCurriculumTerm.semester_id).all() if allowed is None else []
    corrections = MarkRevision.query.filter_by(prn=prn).order_by(MarkRevision.created_at.desc()).all()
    corrections = [r for r in corrections if allowed is None or (r.context['subject_code'], r.context['semester_id'], r.context['academic_year']) in allowed]
    portfolio = db.session.get(StudentPortfolio, prn)
    from completion_models import StudentTerm, CourseOutcomeSelection, ProgressionDecision, AssessmentPolicy, AssessmentScore, AssessmentScoreChange
    placements=StudentTerm.query.filter_by(prn=prn).order_by(StudentTerm.academic_year,StudentTerm.semester_id).all()
    if allowed is not None:
        visible_terms={(sem,year) for code,sem,year in allowed}
        placements=[p for p in placements if (p.semester_id,p.academic_year) in visible_terms]
    selected=CourseOutcomeSelection.query.filter_by(prn=prn).order_by(CourseOutcomeSelection.semester_id,CourseOutcomeSelection.subject_code).all()
    selected=[r for r in selected if allowed is None or (r.subject_code,r.semester_id,r.evidence['teaching_year']) in allowed]
    progression=ProgressionDecision.query.filter_by(prn=prn).order_by(ProgressionDecision.created_at).all() if allowed is None else []
    components=[]
    configured_changes=[]
    for score,policy in db.session.query(AssessmentScore,AssessmentPolicy).join(AssessmentPolicy).filter(AssessmentScore.prn==prn):
        if allowed is not None and (policy.subject_code,policy.semester_id,policy.academic_year) not in allowed:
            continue
        for component in policy.rules['components']:
            value=score.values.get(component['code'],{})
            components.append(dict(subject_code=policy.subject_code,subject_name=db.session.get(Subject,policy.subject_code).subject_name,
                semester_id=policy.semester_id,academic_year=policy.academic_year,label=component['label'],code=component['code'],maximum=component['maximum'],
                value=value.get('value'),state=value.get('state','PENDING'),revision=score.revision))
        configured_changes.extend(AssessmentScoreChange.query.filter_by(policy_token=policy.token,prn=prn).order_by(AssessmentScoreChange.id).all())
    return dict(student=student, local=local, summaries=summaries, official=official_rows, attendance=attendance,
        curriculum=curriculum, corrections=corrections, portfolio=portfolio, portfolio_fields=PORTFOLIO_FIELDS,
        placements=placements,selected_outcomes=selected,progression=progression,configured_components=components,configured_changes=configured_changes,
        cgpa=calculate_cgpa_for_student(prn) if allowed is None else None, scoped=allowed is not None)


def save_portfolio(student, values):
    details = {}
    for key, (label, maximum) in PORTFOLIO_FIELDS.items():
        text = str(values.get(key, '')).strip()
        if len(text) > maximum:
            raise ValueError(f'{label}: at most {maximum} characters.')
        details[key] = text
    try:
        revision = int(values.get('revision', 0))
    except (TypeError, ValueError):
        raise ValueError('Reload the student profile before saving.')
    previous = db.session.get(StudentPortfolio, student.prn)
    before = previous.details if previous else {}
    if previous:
        if db.session.execute(update(StudentPortfolio).where(StudentPortfolio.prn == student.prn,
            StudentPortfolio.revision == revision).values(details=details, revision=revision + 1,
                actor_id=current_user.user_id, updated_at=now())).rowcount != 1:
            raise ValueError('This portfolio changed in another window. Reload before editing.')
    else:
        if revision != 0:
            raise ValueError('Reload before creating this student portfolio.')
        db.session.add(StudentPortfolio(prn=student.prn, details=details, actor_id=current_user.user_id))
    audit(current_user, 'student_portfolio_updated', dict(prn=student.prn, before=before, after=details))
    db.session.commit()
