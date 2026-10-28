"""Explicit syllabus review, immutable approval and safe subject provisioning."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import re
from flask_login import current_user
from sqlalchemy import update
from models import db, Subject, Semester
from curriculum_models import CurriculumVersion, CurriculumBinding
from workflow_models import now
from routes_teaching import normalize_academic_year, audit
from syllabus_parser import extract_syllabus


def create_version(file, values):
    title = str(values.get('title', '')).strip()
    branch = str(values.get('branch', '')).strip()
    scheme = str(values.get('scheme', 'NEP/MIS')).strip().upper()
    if scheme in {'NEP', 'MIS', 'NEP / MIS'}:
        scheme = 'NEP/MIS'
    if not title or len(title) > 180 or not branch or len(branch) > 100 or not scheme or len(scheme) > 30:
        raise ValueError('Enter a title, branch and scheme within the displayed limits.')
    year = normalize_academic_year(values.get('effective_year'))
    if not file or not file.filename.lower().endswith('.pdf'):
        raise ValueError('Select a syllabus PDF.')
    content = file.read(20 * 1024 * 1024 + 1)
    rows, warnings = extract_syllabus(content)
    version = CurriculumVersion(title=title, branch=branch, scheme=scheme, effective_year=year,
        owner_id=current_user.user_id, source_name=file.filename.replace('\\', '/').rsplit('/', 1)[-1][:255],
        source_hash=hashlib.sha256(content).hexdigest(), source_pdf=content,
        extracted=deepcopy(rows), courses=rows, warnings=warnings)
    db.session.add(version)
    db.session.commit()
    return version


def numeric(value, field, limit):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > limit or result != result.to_integral_value():
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field} must be a whole number between 0 and {limit}. The existing marks system uses integer credits.')
    return int(result)


def validate_courses(rows, approval=False):
    if len(rows) > 500:
        raise ValueError('At most 500 courses per syllabus version.')
    selected = [r for r in rows if r.get('include')]
    if approval and not selected:
        raise ValueError('Select at least one verified course to approve.')
    keys = set()
    for row in rows:
        if not row.get('include'):
            continue
        row['code'] = str(row.get('code', '')).strip().upper()
        row['name'] = str(row.get('name', '')).strip()
        row['category'] = str(row.get('category', '')).strip()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]{0,19}', row['code']):
            raise ValueError(f"Row {row['row_id']}: enter a verified subject code (up to 20 characters), or exclude the row.")
        if not row['name'] or len(row['name']) > 150 or len(row['category']) > 20:
            raise ValueError(f"Row {row['row_id']}: subject name is required (up to 150 characters); category up to 20.")
        if row.get('subject_type') not in {'THEORY', 'LAB', 'PROJECT', 'AUDIT'}:
            raise ValueError('Select a valid subject type.')
        row['semester_id'] = numeric(row.get('semester_id'), 'Semester', 8)
        if not row['semester_id'] or row.get('group') not in {'A', 'B', 'COMMON'}:
            raise ValueError('Semester must be 1–8; group must be A, B or COMMON.')
        for field, limit in [('credits', 30), ('l', 40), ('t', 40), ('p', 40)]:
            row[field] = numeric(row.get(field), field, limit)
        if row.get('is_audit') or row['subject_type'] == 'AUDIT':
            row['is_audit'] = True
            if row['credits'] != 0:
                raise ValueError('An audit course must have zero credits.')
        key = (row['semester_id'], row['group'], row['code'])
        if key in keys:
            raise ValueError(f"Duplicate selected course {row['code']} in the same semester/group.")
        keys.add(key)
        original = row.get('original', {})
        if approval and row['code'] != original.get('code', row['code']) and len(str(row.get('evidence', '')).strip()) < 5:
            raise ValueError(f"{row['code']}: add a source reference for the changed/missing printed code.")
        if row.get('manual') and approval and len(str(row.get('evidence', '')).strip()) < 5:
            raise ValueError('Manually added courses need a source/page reference.')
        if len(str(row.get('choice_group', ''))) > 50 or len(str(row.get('evidence', ''))) > 1000:
            raise ValueError('Choice group: at most 50 characters. Evidence: at most 1000.')
    return rows


def proposed_courses(version, form):
    rows = deepcopy(version.courses)
    for row in rows:
        prefix = f"r{row['row_id']}_"
        original = next((r for r in version.extracted if r['row_id'] == row['row_id']), None)
        row['original'] = {k: original[k] for k in ('code', 'name', 'credits')} if original else {}
        for field in ('code', 'name', 'category', 'subject_type', 'credits', 'l', 't', 'p', 'semester_id', 'group', 'choice_group', 'evidence'):
            row[field] = form.get(prefix + field, row.get(field, ''))
        for field in ('include', 'is_audit', 'is_bucket'):
            row[field] = form.get(prefix + field) == 'on'
    return rows


def subject_values(row):
    # Choice options share an elective_group; bucket parents stay non-enrollable.
    return dict(subject_name=row['name'], semester_id=row['semester_id'], subject_type=row['subject_type'],
        credits=row['credits'], l_hours=row['l'], t_hours=row['t'], p_hours=row['p'], category=row['category'],
        is_elective=bool(row.get('choice_group') or row.get('is_bucket')),
        elective_group=row.get('choice_group') or None,
        parent_subject_code=None, is_audit=bool(row.get('is_audit')), is_attendance_only=False)


def conflicts(rows):
    errors, by_code = [], {}
    for row in [r for r in rows if r.get('include')]:
        expected = subject_values(row)
        # Options are represented by a real parent only when one was supplied;
        # do not manufacture codes for parent courses.
        if row.get('choice_group') and not row.get('is_bucket'):
            expected['is_elective'] = False
            expected['elective_group'] = row['choice_group']
        if row['code'] in by_code and by_code[row['code']] != expected:
            errors.append(f"{row['code']}: selected rows disagree. Keep separate versions or resolve the code/semester before approval.")
        by_code[row['code']] = expected
        subject = db.session.get(Subject, row['code'])
        if subject:
            different = [key for key, value in expected.items() if getattr(subject, key) != value and not (getattr(subject, key) in (None, '') and value in (None, ''))]
            if different:
                errors.append(f"{row['code']}: existing subject differs in {', '.join(different)}. It was preserved; resolve the code or exclude this row.")
            elif not subject.is_active:
                errors.append(f"{row['code']}: existing subject is disabled. Enable it in Subjects before approval.")
    return errors, by_code


def save_draft(version, rows, revision):
    if version.status != 'DRAFT':
        raise ValueError('Approved versions are immutable. Create a revision instead.')
    # Drafts may keep unresolved data; approval performs full validation.
    changed = db.session.execute(update(CurriculumVersion).where(
        CurriculumVersion.token == version.token, CurriculumVersion.status == 'DRAFT',
        CurriculumVersion.revision == revision).values(courses=rows, revision=revision + 1)).rowcount
    if changed != 1:
        db.session.rollback()
        raise ValueError('This draft changed in another window. Reload before editing.')
    db.session.commit()


def approve(version, revision):
    if version.status == 'APPROVED':
        return False
    rows = validate_courses(deepcopy(version.courses), approval=True)
    errors, subjects = conflicts(rows)
    if errors:
        raise ValueError('\n'.join(errors[:15]))
    changed = db.session.execute(update(CurriculumVersion).where(
        CurriculumVersion.token == version.token, CurriculumVersion.status == 'DRAFT',
        CurriculumVersion.revision == revision).values(status='APPROVED', courses=rows,
            approved_at=now(), approved_by=current_user.user_id, revision=revision + 1)).rowcount
    if changed != 1:
        raise ValueError('This version changed. Reload and review again.')
    for code, values in subjects.items():
        if db.session.get(Subject, code) is None:
            db.session.add(Subject(subject_code=code, is_active=True, **values))
    audit(current_user, 'curriculum_approved', {'version': version.token, 'source_sha256': version.source_hash, 'courses': len(subjects)})
    db.session.commit()
    return True


def bind_version(version, values):
    if version.status != 'APPROVED':
        raise ValueError('Approve the syllabus before assigning it to a cohort/term.')
    year = normalize_academic_year(values.get('academic_year'))
    cohort = numeric(values.get('regular_cohort'), 'Regular cohort admission year', 2199)
    semester = numeric(values.get('semester_id'), 'Semester', 8)
    group = str(values.get('group', 'COMMON')).upper()
    if cohort < 1900 or cohort > int(year[:4]) or semester < 1:
        raise ValueError('Choose a valid cohort year and semester.')
    if not any(r.get('include') and r['semester_id'] == semester and r['group'] == group for r in version.courses):
        raise ValueError('The approved version has no selected courses for this semester/group.')
    existing = CurriculumBinding.query.filter_by(branch=version.branch, regular_cohort=cohort,
        semester_id=semester, academic_year=year, group_name=group).first()
    if existing:
        if existing.version_token == version.token:
            return False
        raise ValueError('This cohort/term already has an approved curriculum. Its historical binding was preserved.')
    if not db.session.get(Semester, (semester, year)):
        db.session.add(Semester(semester_id=semester, academic_year=year, is_active=False))
    db.session.add(CurriculumBinding(version_token=version.token, branch=version.branch,
        regular_cohort=cohort, semester_id=semester, academic_year=year, group_name=group, actor_id=current_user.user_id))
    audit(current_user, 'curriculum_bound', {'version': version.token, 'regular_cohort': cohort,
        'semester_id': semester, 'academic_year': year, 'group': group})
    db.session.commit()
    return True
