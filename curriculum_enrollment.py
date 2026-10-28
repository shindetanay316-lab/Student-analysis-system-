"""Reviewed curriculum enrollment, including explicit DSE-to-regular-cohort linkage."""
from datetime import timezone
from hashlib import sha256
import json
from sqlalchemy import update
from flask_login import current_user
from models import db, Student, Subject, Enrollment
from curriculum_models import CurriculumBinding, CurriculumVersion, StudentCurriculumTerm
from workflow_models import WorkflowReview, now
from routes_teaching import audit
from workflow_services import validate_roster_rows


def courses(binding):
    return [r for r in binding.version.courses if r.get('include') and r['semester_id'] == binding.semester_id and r['group'] == binding.group_name]


def fingerprint(binding, prns, codes):
    payload = dict(version=binding.version_token, branch=binding.branch, cohort=binding.regular_cohort,
        semester=binding.semester_id, year=binding.academic_year, group=binding.group_name,
        students=[s.to_dict() for s in Student.query.filter(Student.prn.in_(prns)).order_by(Student.prn)],
        subjects=[s.to_dict() for s in Subject.query.filter(Subject.subject_code.in_(codes)).order_by(Subject.subject_code)],
        enrollments=[(e.prn, e.subject_code) for e in Enrollment.query.filter(Enrollment.prn.in_(prns), Enrollment.semester_id == binding.semester_id,
            Enrollment.academic_year == binding.academic_year).order_by(Enrollment.prn, Enrollment.subject_code)],
        assigned=[(a.prn, a.binding_id) for a in StudentCurriculumTerm.query.filter(StudentCurriculumTerm.prn.in_(prns),
            StudentCurriculumTerm.semester_id == binding.semester_id, StudentCurriculumTerm.academic_year == binding.academic_year).order_by(StudentCurriculumTerm.prn)])
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def validate(binding, prns, codes):
    if binding.version.status != 'APPROVED':
        raise ValueError('Select an approved curriculum binding.')
    available = courses(binding)
    required = {r['code'] for r in available if not r.get('choice_group') and not r.get('is_bucket')}
    choices = {}
    for row in available:
        if row.get('choice_group') and not row.get('is_bucket'):
            choices.setdefault(row['choice_group'], set()).add(row['code'])
    actual = {r['code'] for r in available if not r.get('is_bucket')}
    if not codes or not set(codes).issubset(actual) or not required.issubset(codes):
        raise ValueError('Select all compulsory courses and only verified options from this binding.')
    for group, options in choices.items():
        if len(set(codes) & options) != 1:
            raise ValueError(f'Select exactly one option in {group} for these students. Use separate previews for different options.')
    students = Student.query.filter(Student.prn.in_(prns)).order_by(Student.prn).all()
    if not students or len(students) != len(set(prns)) or len(students) > 1000:
        raise ValueError('Select 1–1,000 existing students with valid PRNs.')
    for student in students:
        # DSE retains its real admission year, while explicitly using the
        # matching regular cohort curriculum from semester 3.
        valid_admissions = {binding.regular_cohort}
        if binding.semester_id >= 3:
            valid_admissions.add(binding.regular_cohort + 1)
        if student.year_of_admission not in valid_admissions:
            raise ValueError(f'{student.prn}: admission year does not match the regular cohort or next-year DSE intake.')
        assigned = StudentCurriculumTerm.query.filter_by(prn=student.prn, semester_id=binding.semester_id, academic_year=binding.academic_year).first()
        if assigned and assigned.binding_id != binding.id:
            raise ValueError(f'{student.prn}: already linked to a different curriculum for this teaching term.')
    from curriculum_services import conflicts
    selected_rows = [{**r, 'include': r['code'] in codes} for r in available]
    errors, _ = conflicts(selected_rows)
    if errors:
        raise ValueError('Subjects changed after syllabus approval. ' + '\n'.join(errors[:5]))
    roster_rows = [dict(prn=s.prn, name=s.name, admission_year=s.year_of_admission, division=s.division or '', batch=s.batch or '') for s in students]
    for code in codes:
        if not db.session.get(Subject, code) or not db.session.get(Subject, code).is_active:
            raise ValueError(f'{code}: the approved subject is missing or disabled.')
        validate_roster_rows(dict(subject_code=code, semester_id=binding.semester_id, academic_year=binding.academic_year), roster_rows)
    return students


def preview(binding, prns, options):
    available = courses(binding)
    codes = sorted({r['code'] for r in available if not r.get('choice_group') and not r.get('is_bucket')} | set(options))
    students = validate(binding, prns, codes)
    review = WorkflowReview(owner_id=current_user.user_id, kind='CURRICULUM_ROSTER',
        context=dict(binding_id=binding.id, codes=codes, semester_id=binding.semester_id, academic_year=binding.academic_year),
        rows=[dict(prn=s.prn, name=s.name, admission_year=s.year_of_admission) for s in students],
        snapshot=fingerprint(binding, prns, codes))
    db.session.add(review)
    db.session.commit()
    return review


def confirm(review):
    if review.confirmed_at:
        return False
    binding = db.session.get(CurriculumBinding, review.context['binding_id'])
    if not binding:
        raise ValueError('The selected curriculum binding no longer exists.')
    expires = review.expires_at.replace(tzinfo=timezone.utc) if review.expires_at.tzinfo is None else review.expires_at
    if expires <= now():
        raise ValueError('Preview expired. Create a fresh enrollment preview.')
    codes, prns = review.context['codes'], [r['prn'] for r in review.rows]
    db.session.execute(db.select(Subject).where(Subject.subject_code.in_(codes)).order_by(Subject.subject_code).with_for_update())
    if fingerprint(binding, prns, codes) != review.snapshot:
        raise ValueError('Student placements, enrollments or subjects changed. Create a fresh preview.')
    students = validate(binding, prns, codes)
    if db.session.execute(update(WorkflowReview).where(WorkflowReview.token == review.token, WorkflowReview.claimed.is_(False),
        WorkflowReview.confirmed_at.is_(None)).values(claimed=True)).rowcount != 1:
        raise ValueError('This enrollment preview has already been processed.')
    for student in students:
        term = StudentCurriculumTerm.query.filter_by(prn=student.prn, semester_id=binding.semester_id, academic_year=binding.academic_year).first()
        if not term:
            db.session.add(StudentCurriculumTerm(prn=student.prn, binding_id=binding.id, semester_id=binding.semester_id,
                academic_year=binding.academic_year, actor_id=current_user.user_id))
        for code in codes:
            fields = dict(prn=student.prn, subject_code=code, semester_id=binding.semester_id, academic_year=binding.academic_year)
            if not Enrollment.query.filter_by(**fields).first():
                db.session.add(Enrollment(**fields))
    review.confirmed_at = now()
    audit(current_user, 'curriculum_roster_confirmed', {'review': review.token, 'binding_id': binding.id, 'students': prns, 'subjects': codes})
    db.session.commit()
    return True
