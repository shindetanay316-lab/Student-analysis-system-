"""Reviewed course-attempt choices, backlog counts and semester progression."""
from decimal import Decimal
from flask_login import current_user
from models import db, Student, Subject, Enrollment, Semester
from completion_models import ProgressionPolicy, ProgressionDecision, CourseOutcomeSelection, StudentTerm
from academic_link_models import UniversityLinkedResult
from workflow_models import WorkflowReview, now
from routes_teaching import audit, normalize_academic_year
from academic_link_services import digest
from assessment_services import number
import term_services as terms


def create_policy(values):
    title, source = str(values.get('title','')).strip(), str(values.get('source_reference','')).strip()
    try:
        semester = int(values.get('from_semester'))
        subjects = int(values.get('maximum_backlog_subjects'))
        credits = int(values.get('maximum_backlog_credits'))
    except (ValueError, TypeError):
        raise ValueError('Semester and backlog limits must be whole numbers.')
    if semester not in range(1,9) or not 0<=subjects<=200 or not 0<=credits<=1000 or not 1<=len(title)<=180 or not 10<=len(source)<=1000:
        raise ValueError('Enter semester 1–8, nonnegative backlog limits, a title and source reference of 10–1,000 characters.')
    percent = number(values.get('minimum_earned_percent'), 'Minimum earned credit percentage',0,100)
    try:
        reviewed=sorted({int(v.strip()) for v in str(values.get('reviewed_semesters','')).split(',')})
    except ValueError:
        raise ValueError('List the semesters required by this policy, separated by commas.')
    if semester not in reviewed or any(v<1 or v>semester for v in reviewed):
        raise ValueError('Reviewed semesters must include the source semester and contain only semesters up to it.')
    if semester==8 and (subjects or credits or percent!=100):
        raise ValueError('Graduation requires no backlogs and 100% earned credits. Configure zero backlog limits and 100%.')
    policy = ProgressionPolicy(title=title,from_semester=semester,reviewed_semesters=reviewed,maximum_backlog_subjects=subjects,
        maximum_backlog_credits=credits,minimum_earned_percent=percent,source_reference=source,actor_id=current_user.user_id)
    db.session.add(policy)
    audit(current_user,'progression_policy_approved',dict(title=title,semester=semester,source=source))
    db.session.commit()
    return policy


def local_result(prn, semester_id, academic_year):
    """Legacy report helpers refresh derived ORM fields; never save them during review."""
    from final_result_utils import build_student_semester_result
    savepoint = db.session.begin_nested()
    try:
        result = build_student_semester_result(prn,semester_id,academic_year)
        return {k:v for k,v in result.items() if k!='student'}
    finally:
        savepoint.rollback()


def candidates(prn, upto_semester, upto_year, reviewed_semesters=None):
    enrollments = Enrollment.query.join(Subject).filter(Enrollment.prn==prn,Enrollment.semester_id<=upto_semester,
        Enrollment.academic_year<=upto_year,Subject.credits>0,Subject.is_audit.is_(False),Subject.is_attendance_only.is_(False),
        db.or_(Subject.is_elective.is_(False),Subject.parent_subject_code.isnot(None))).order_by(Enrollment.semester_id,Enrollment.subject_code,Enrollment.academic_year).all()
    courses, cache = {}, {}
    for enrollment in enrollments:
        if reviewed_semesters is not None and enrollment.semester_id not in reviewed_semesters:
            continue
        subject = enrollment.subject
        key = (enrollment.semester_id,subject.subject_code)
        course = courses.setdefault(key,dict(semester_id=key[0],subject_code=key[1],subject_name=subject.subject_name,
            credits=int(subject.credits or 0),options=[]))
        term = (enrollment.semester_id,enrollment.academic_year)
        if term not in cache:
            cache[term] = local_result(prn,*term)
        result = next((r for r in cache[term]['subjects'] if r['subject_code']==subject.subject_code),None)
        if result and result['result'] in {'PASS','FAIL'} and result['grade_point'] is not None:
            course['options'].append(dict(key=f'LOCAL|{subject.subject_code}|{term[0]}|{term[1]}',
                label='Local '+term[1],source='LOCAL',teaching_year=term[1],result=result['result'],grade=result['grade'],
                grade_point=float(result['grade_point']),total=float(result['total']) if result['total'] is not None else None))
    # Only the newest linked revision of each printed source result is eligible.
    latest = set()
    for link in UniversityLinkedResult.query.filter_by(prn=prn).order_by(UniversityLinkedResult.id.desc()):
        if link.attempt_key in latest:
            continue
        latest.add(link.attempt_key)
        course = courses.get((link.semester_id,link.subject_code))
        source = link.source
        if not course or link.academic_year>upto_year or source.get('student_status') in {'CANCEL','CANCELLED','WITHHELD','RR','RLE'}:
            continue
        grade = str(source.get('grade_display') or '').strip().upper()
        point = source.get('grade_point')
        if grade not in {'EX','AA','AB','BB','BC','CC','CD','DD','DE','EE','FF','F'} or point is None:
            continue
        try:
            point = number(point,'Printed grade point',0,10)
        except ValueError:
            continue
        passed = grade not in {'FF','F'} and point>0
        if (grade in {'FF','F'} and point!=0) or (grade not in {'FF','F'} and point==0):
            continue
        course['options'].append(dict(key='UNIVERSITY|'+str(link.id),label='University '+str(link.publication.examination_session or '')+' / '+str(link.id),
            source='UNIVERSITY',teaching_year=link.academic_year,result='PASS' if passed else 'FAIL',grade=grade,
            grade_point=float(point),total=source.get('total'),source_hash=link.publication.source_hash))
    return [courses[k] for k in sorted(courses)]


def analyze(student, policy, year, choices=None):
    rows = candidates(student.prn,policy.from_semester,year,policy.reviewed_semesters)
    choices = choices or {}
    registered = earned = backlog_credits = backlog_subjects = pending = 0
    for row in rows:
        field = f"choice_{row['semester_id']}_{row['subject_code']}"
        suggested = max(row['options'],key=lambda r:(r['result']=='PASS',r['grade_point']),default=None)
        proposed = choices.get(field)
        selected = next((r for r in row['options'] if r['key']==proposed),None) if proposed else suggested
        if proposed and not selected:
            raise ValueError('A selected attempt is unavailable or was superseded. Refresh the source choices.')
        row['selected'] = selected
        registered += row['credits']
        if not selected:
            pending += 1
        elif selected['result']=='PASS':
            earned += row['credits']
        else:
            backlog_credits += row['credits']
            backlog_subjects += 1
    percent = (Decimal(earned)/registered*100) if registered else Decimal(0)
    reasons = []
    missing_semesters=set(policy.reviewed_semesters)-{r['semester_id'] for r in rows}
    if missing_semesters:
        reasons.append('Missing required enrollment/evidence for semester(s): '+', '.join(map(str,sorted(missing_semesters))))
    if not rows or registered<=0:
        reasons.append('No graded enrollment/credits in the reviewed scope.')
    if pending:
        reasons.append(f'{pending} courses have no eligible complete attempt; missing evidence is not a failure or zero.')
    if backlog_subjects>policy.maximum_backlog_subjects:
        reasons.append('Backlog subject limit exceeded.')
    if backlog_credits>policy.maximum_backlog_credits:
        reasons.append('Backlog credit limit exceeded.')
    if percent<policy.minimum_earned_percent:
        reasons.append('Earned credit percentage is below the approved minimum.')
    summary = dict(registered_credits=registered,earned_credits=earned,backlog_credits=backlog_credits,
        backlog_subjects=backlog_subjects,pending_courses=pending,earned_percent=float(percent.quantize(Decimal('.01'))),
        eligible=not reasons,reasons=reasons)
    return rows,summary


def fingerprint(student, policy, year, target_year, choices):
    rows,summary = analyze(student,policy,year,choices)
    return digest(dict(student=student.to_dict(),policy=(policy.token,policy.from_semester,policy.maximum_backlog_subjects,
        policy.maximum_backlog_credits,str(policy.minimum_earned_percent),policy.reviewed_semesters),rows=rows,summary=summary,
        enrollments=[(e.subject_code,e.semester_id,e.academic_year) for e in Enrollment.query.filter_by(prn=student.prn).order_by(Enrollment.id)],
        placements=[(p.semester_id,p.academic_year,p.revision,p.status) for p in StudentTerm.query.filter_by(prn=student.prn).order_by(StudentTerm.id)],
        decisions=[(d.token,d.decision,d.revision) for d in ProgressionDecision.query.filter_by(prn=student.prn).order_by(ProgressionDecision.created_at)],target_year=target_year))


def preview(student, policy, values):
    year = normalize_academic_year(values.get('academic_year'))
    c = dict(semester_id=policy.from_semester,academic_year=year)
    terms.term(c)
    if not Enrollment.query.filter_by(prn=student.prn,**c).first():
        raise ValueError('Student has no enrollment in this source semester and academic year.')
    if ProgressionDecision.query.filter_by(prn=student.prn,**c).filter(ProgressionDecision.decision.in_(['PROMOTED','GRADUATED'])).first():
        raise ValueError('This teaching term already has a final progression approval. Earlier approval is retained.')
    target_year = None
    if policy.from_semester<8:
        target_year = normalize_academic_year(values.get('target_year'))
        if target_year<year or int(target_year[:4])>int(year[:4])+2:
            raise ValueError('Choose a next teaching year from the source year through the following two years.')
        terms.term(dict(semester_id=policy.from_semester+1,academic_year=target_year))
    reason = str(values.get('reason','')).strip()
    if policy.from_semester==8 and values.get('clearances_verified')!='on':
        raise ValueError('Verify required audit/non-credit courses and institutional clearances before graduation review.')
    if not 10<=len(reason)<=1000:
        raise ValueError('Enter a review reason of 10–1,000 characters, including any non-best attempt choice.')
    rows,summary = analyze(student,policy,year,values)
    choices = {f"choice_{r['semester_id']}_{r['subject_code']}":r['selected']['key'] for r in rows if r['selected']}
    context = dict(prn=student.prn,policy_token=policy.token,academic_year=year,semester_id=policy.from_semester,
        target_year=target_year,choices=choices,summary=summary,reason=reason,student_name=student.name,
        clearances_verified=values.get('clearances_verified')=='on',
        decision=('GRADUATED' if policy.from_semester==8 else 'PROMOTED') if summary['eligible'] else 'HOLD')
    review = WorkflowReview(owner_id=current_user.user_id,kind='PROGRESSION',context=context,rows=rows,
        snapshot=fingerprint(student,policy,year,target_year,choices))
    db.session.add(review)
    db.session.commit()
    return review


def confirm(review):
    from completion_services import claim
    if review.confirmed_at:
        return False
    c = review.context
    student = db.session.execute(db.select(Student).where(Student.prn==c['prn']).with_for_update()).scalar_one()
    codes=db.session.query(Enrollment.subject_code).filter(Enrollment.prn==student.prn,
        Enrollment.semester_id<=c['semester_id'],Enrollment.academic_year<=c['academic_year']).distinct().all()
    db.session.execute(db.select(Subject).where(Subject.subject_code.in_([v[0] for v in codes])).order_by(Subject.subject_code).with_for_update()).all()
    policy = db.session.get(ProgressionPolicy,c['policy_token'])
    claim(review)
    if fingerprint(student,policy,c['academic_year'],c['target_year'],c['choices'])!=review.snapshot:
        raise ValueError('Attempts, enrollment or placements changed. Create a fresh progression preview.')
    rows,summary = analyze(student,policy,c['academic_year'],c['choices'])
    source = dict(prn=student.prn,semester_id=c['semester_id'],academic_year=c['academic_year'])
    old = ProgressionDecision.query.filter_by(**source).order_by(ProgressionDecision.revision.desc()).first()
    if old and old.decision in {'PROMOTED','GRADUATED'}:
        raise ValueError('A final progression decision already exists.')
    revision = old.revision+1 if old else 1
    if c['decision']=='PROMOTED':
        target = terms.placement(student.prn,c['semester_id']+1,c['target_year'])
        if not target:
            # Never copy an old roll/division/batch into the new term by guessing.
            target = terms.ensure_placement(student.prn,c['semester_id']+1,c['target_year'],division=None,batch=None,origin='PROGRESSION')
            target.actor_id = current_user.user_id
    for row in rows:
        chosen = row['selected']
        if not chosen:
            continue
        keys = dict(prn=student.prn,subject_code=row['subject_code'],semester_id=row['semester_id'])
        selection = CourseOutcomeSelection.query.filter_by(**keys).first()
        evidence = dict(chosen,credits=row['credits'],subject_name=row['subject_name'])
        if selection:
            selection.source_key,selection.evidence,selection.review_token = chosen['key'],evidence,review.token
            selection.revision,selection.approved_at = selection.revision+1,now()
        else:
            db.session.add(CourseOutcomeSelection(**keys,source_key=chosen['key'],evidence=evidence,review_token=review.token))
    db.session.add(ProgressionDecision(**source,revision=revision,target_year=c['target_year'],decision=c['decision'],
        policy_token=policy.token,outcomes=rows,summary=summary,reason=c['reason'],actor_id=current_user.user_id,review_token=review.token))
    review.confirmed_at = now()
    audit(current_user,'progression_approved',dict(**source,decision=c['decision'],revision=revision,review=review.token))
    db.session.commit()
    return True


def consolidated(prn):
    rows = CourseOutcomeSelection.query.filter_by(prn=prn).order_by(CourseOutcomeSelection.semester_id,CourseOutcomeSelection.subject_code).all()
    credits = sum(r.evidence['credits'] for r in rows)
    points = sum(Decimal(str(r.evidence['grade_point']))*r.evidence['credits'] for r in rows)
    # Only approved selections are included; this is not a whole-degree completeness claim.
    average = float((points/credits).quantize(Decimal('.01'))) if credits else None
    return dict(rows=rows,credits=credits,grade_average=average,
        earned=sum(r.evidence['credits'] for r in rows if r.evidence['result']=='PASS'),
        backlogs=sum(1 for r in rows if r.evidence['result']=='FAIL'))
