"""Semester placements; global Student division/batch are legacy defaults only."""
import csv
from io import StringIO
import json
from hashlib import sha256
from flask_login import current_user
from models import db, Student, Semester, Enrollment
from completion_models import StudentTerm, PendingAdmission
from workflow_models import WorkflowReview, now
from routes_teaching import normalize_academic_year, audit


def term(values):
    try:
        semester = int(values.get('semester_id'))
    except (TypeError, ValueError):
        raise ValueError('Choose semester 1 to 8.')
    year = normalize_academic_year(values.get('academic_year'))
    if semester not in range(1, 9) or not db.session.get(Semester, (semester, year)):
        raise ValueError('Create/select an existing teaching semester and academic year.')
    return dict(semester_id=semester, academic_year=year)


def placement(prn, semester_id, academic_year):
    return StudentTerm.query.filter_by(prn=prn, semester_id=semester_id, academic_year=academic_year).first()


class TermStudent:
    def __init__(self, student, record):
        self._student = student
        self.division = record.division if record else student.division
        self.batch = record.batch if record else student.batch
        self.roll_number = record.roll_number if record else None
        self.placement_origin = record.origin if record else 'LEGACY_DEFAULT'

    def __getattr__(self, key):
        return getattr(self._student, key)


def students_in_term(students, semester_id, academic_year):
    placements = {r.prn:r for r in StudentTerm.query.filter_by(semester_id=semester_id, academic_year=academic_year)}
    return [TermStudent(s, placements.get(s.prn)) for s in students]


def ensure_placement(prn, semester_id, academic_year, **values):
    record = placement(prn, semester_id, academic_year)
    if not record:
        student = db.session.get(Student, prn)
        record = StudentTerm(prn=prn, semester_id=semester_id, academic_year=academic_year,
            division=values.get('division', student.division if student else None),
            batch=values.get('batch', student.batch if student else None), origin=values.get('origin', 'ROSTER_DEFAULT'))
        db.session.add(record)
    return record


def clean_placement(values):
    result = {k:str(values.get(k) or '').strip().upper() or None for k in ('division', 'batch', 'roll_number')}
    if any(v and len(v) > (20 if k == 'roll_number' else 10) for k,v in result.items()):
        raise ValueError('Roll number: at most 20 characters. Division/batch: at most 10.')
    if result['roll_number'] and not result['division']:
        raise ValueError('Assign a division with a roll number so roll numbers stay unique within that division.')
    if result['batch'] and not result['division']:
        raise ValueError('Assign a division with the practical batch.')
    return result


def fingerprint(c, rows):
    prns = [r['prn'] for r in rows]
    placements = StudentTerm.query.filter_by(**c).order_by(StudentTerm.prn).all()
    payload = dict(students=[s.to_dict() for s in Student.query.filter(Student.prn.in_(prns)).order_by(Student.prn)],
        placements=[(p.prn, p.division, p.batch, p.roll_number, p.revision, p.status) for p in placements])
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_rows(c, rows):
    if not rows or len(rows) > 5000:
        raise ValueError('Select between 1 and 5,000 students.')
    seen, rolls = set(), set()
    selected = {r['prn'] for r in rows}
    for record in StudentTerm.query.filter_by(**c):
        if record.prn not in selected and record.roll_number:
            rolls.add((record.division, record.roll_number))
    for row in rows:
        student = db.session.get(Student, row['prn'])
        if not student or row['prn'] in seen:
            raise ValueError('Unknown or duplicate PRN in term placement.')
        if ' '.join(student.name.split()).casefold() != ' '.join(row['name'].split()).casefold():
            raise ValueError(f"{row['prn']}: student name differs from the profile.")
        seen.add(row['prn'])
        row.update(clean_placement(row))
        if row['roll_number']:
            key = (row['division'], row['roll_number'])
            if key in rolls:
                raise ValueError(f'Duplicate roll number {key[1]} in division {key[0]} for this term.')
            rolls.add(key)


def preview(c, rows):
    validate_rows(c, rows)
    review = WorkflowReview(owner_id=current_user.user_id, kind='TERM_PLACEMENT', context=c, rows=rows, snapshot=fingerprint(c, rows))
    db.session.add(review)
    db.session.commit()
    return review


def confirm(review):
    from completion_services import claim
    if review.confirmed_at:
        return False
    c = term(review.context)
    db.session.execute(db.select(Semester).filter_by(**c).with_for_update()).scalar_one()
    claim(review)
    if fingerprint(c, review.rows) != review.snapshot:
        raise ValueError('Placement or student records changed. Create a fresh preview.')
    validate_rows(c, review.rows)
    # Clear conflicting rolls inside the selected set first, allowing reviewed swaps.
    for record in StudentTerm.query.filter_by(**c).filter(StudentTerm.prn.in_([r['prn'] for r in review.rows])):
        record.roll_number = None
    db.session.flush()
    for row in review.rows:
        record = ensure_placement(row['prn'], **c)
        for key in ('division', 'batch', 'roll_number'):
            setattr(record, key, row[key])
        record.revision = (record.revision or 0) + 1
        record.origin, record.actor_id, record.updated_at = 'REVIEWED', current_user.user_id, now()
    review.confirmed_at = now()
    audit(current_user, 'term_placement_approved', dict(**c, rows=len(review.rows), review=review.token))
    db.session.commit()
    return True


def admission(values):
    c = term(values)
    number, name = str(values.get('admission_number','')).strip(), str(values.get('name','')).strip()
    try:
        year = int(values.get('admission_year'))
    except (ValueError, TypeError):
        raise ValueError('Enter the actual admission year.')
    if not number or len(number) > 40 or not name or len(name) > 100 or not 1900 <= year <= int(c['academic_year'][:4]) + 1:
        raise ValueError('Enter a valid admission number, student name and actual admission year.')
    if PendingAdmission.query.filter_by(admission_number=number).first():
        raise ValueError('This admission number is already recorded.')
    item = PendingAdmission(admission_number=number, name=name, admission_year=year,
        placement=dict(c, **clean_placement(values)), actor_id=current_user.user_id)
    db.session.add(item)
    audit(current_user, 'pending_admission_created', dict(admission_number=number))
    db.session.commit()
    return item


def activation_preview(item, prn):
    import re
    prn = str(prn or '').strip()
    if item.activated_prn or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,19}', prn) or db.session.get(Student, prn):
        raise ValueError('Enter an unused real PRN. Existing identities are never merged automatically.')
    row = dict(prn=prn, name=item.name, admission_year=item.admission_year, **item.placement)
    review = WorkflowReview(owner_id=current_user.user_id, kind='PRN_ACTIVATION',
        context=dict(admission_token=item.token,revision=item.revision), rows=[row], snapshot=sha256(json.dumps(row, sort_keys=True).encode()).hexdigest())
    db.session.add(review)
    db.session.commit()
    return review


def activate(review):
    from completion_services import claim
    if review.confirmed_at:
        return False
    item = db.session.execute(db.select(PendingAdmission).where(PendingAdmission.token == review.context['admission_token']).with_for_update()).scalar_one()
    claim(review)
    row = review.rows[0]
    if item.activated_prn or item.revision!=review.context['revision'] or db.session.get(Student, row['prn']):
        raise ValueError('This admission or PRN was already activated. Reload the list.')
    current = dict(prn=row['prn'], name=item.name, admission_year=item.admission_year, **item.placement)
    if sha256(json.dumps(current, sort_keys=True).encode()).hexdigest() != review.snapshot:
        raise ValueError('The admission changed. Create a fresh activation preview.')
    c = term(row)
    validate = dict(prn=row['prn'], name=row['name'], division=row['division'], batch=row['batch'], roll_number=row['roll_number'])
    if row['roll_number'] and StudentTerm.query.filter_by(**c, division=row['division'], roll_number=row['roll_number']).first():
        raise ValueError('The chosen roll number is already occupied. Correct the pending placement first.')
    db.session.add(Student(prn=row['prn'], name=row['name'], year_of_admission=row['admission_year'], division=row['division'], batch=row['batch']))
    db.session.flush()
    record = ensure_placement(row['prn'], **c, division=row['division'], batch=row['batch'], origin='PRN_ACTIVATION')
    record.roll_number, record.actor_id = row['roll_number'], current_user.user_id
    item.activated_prn, review.confirmed_at = row['prn'], now()
    audit(current_user, 'admission_prn_activated', dict(admission_number=item.admission_number, prn=row['prn'], review=review.token))
    db.session.commit()
    return True


def edit_admission(item, values):
    if item.activated_prn:
        raise ValueError('Activated admissions are retained. Edit the teaching-term placement in Semester student records.')
    c = term(values)
    name = str(values.get('name','')).strip()
    try:
        year = int(values.get('admission_year'))
        revision = int(values.get('revision'))
    except (ValueError,TypeError):
        raise ValueError('Reload the admission form and enter its actual admission year.')
    if not 1<=len(name)<=100 or not 1900<=year<=int(c['academic_year'][:4])+1:
        raise ValueError('Enter a valid student name and actual admission year.')
    before = dict(name=item.name,admission_year=item.admission_year,placement=item.placement)
    count = db.session.execute(db.update(PendingAdmission).where(PendingAdmission.token==item.token,PendingAdmission.revision==revision,
        PendingAdmission.activated_prn.is_(None)).values(name=name,admission_year=year,placement=dict(c,**clean_placement(values)),revision=revision+1)).rowcount
    if count!=1:
        raise ValueError('This admission changed. Reload before editing.')
    audit(current_user,'pending_admission_corrected',dict(admission_number=item.admission_number,before=before))
    db.session.commit()
