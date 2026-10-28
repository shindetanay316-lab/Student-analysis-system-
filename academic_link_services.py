"""Review university data before linking it; fill only compatible empty ESE cells."""
from datetime import timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import json
import re
from flask import current_app
from flask_login import current_user
from sqlalchemy import update
from models import db, Student, Subject, Semester, Enrollment, TheoryMarks, ExternalMarks
from result_data.models import ImportJob
from workflow_models import WorkflowReview, now
from coursework_models import AcceptedCourseworkMark
from academic_link_models import UniversityPublication, UniversityLinkedResult
from routes_teaching import normalize_academic_year, audit
import coursework_services as coursework


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def text_number(value):
    return str(value) if value is not None else None


def confirmed_job(job):
    if not job or not job.report or not job.confirmed_at or job.status not in {'READY', 'EXPORTED'}:
        raise ValueError('Confirm the university extraction before linking academic records.')
    if job.report.validation_error_count or job.report.validation_status not in {'VALID', 'WARNING'}:
        raise ValueError('Resolve extraction validation errors and confirm the import first.')
    try:
        semester = int(job.report.semester)
    except (TypeError, ValueError):
        raise ValueError('The source report needs a verified semester from 1 to 8.')
    if semester not in range(1, 9):
        raise ValueError('The source semester must be from 1 to 8.')
    return semester


def source_bytes(job):
    folder = Path(current_app.config['RESULT_DATA_UPLOAD_FOLDER']).resolve()
    path = (folder / job.stored_filename).resolve()
    if path.parent != folder or not path.is_file():
        raise ValueError('Original university PDF is missing or outside the upload folder. Restore its original source file.')
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError('The university PDF exceeds 25 MB.')
    content = path.read_bytes()
    if sha256(content).hexdigest() != job.file_hash:
        raise ValueError('The stored PDF differs from its recorded hash. Restore the original source before linking.')
    return content


def source_rows(job):
    from result_data.services.grade_service import display_grade, manually_changed_grade
    report = job.report
    rows = []
    for student in sorted(report.students, key=lambda s: s.seat_number):
        summary = student.summary
        for result in sorted(student.subject_results, key=lambda r: r.subject.subject_code):
            subject = result.subject
            payload = dict(prn=student.seat_number, name=student.name, student_status=student.result_status,
                validation=student.validation_status, subject_validation=result.validation_status,
                registration_scope=student.registration_scope, subject_code=subject.subject_code, subject_name=subject.subject_name,
                credits=text_number(subject.credits), audit=subject.is_audit, maximum=text_number(subject.total_maximum),
                total=text_number(result.total_value), total_raw=result.total_raw, total_special=result.total_special_code,
                total_carried=result.total_is_carried_forward, grade=result.grade, grade_raw=result.grade_raw,
                grade_display=display_grade(result) or ('REVIEW' if manually_changed_grade(result) else 'NOT PRINTED'),
                audit_grade=result.audit_grade, grade_point=text_number(result.grade_point), credit_points=text_number(result.credit_points),
                attempt_session=result.attempt_session, source_page=result.source_page,
                sgpa=text_number(summary.reported_sgpa) if summary else None,
                reported_status=summary.reported_status if summary else None,
                components=[dict(type=c.component_type, raw=c.raw_text, value=text_number(c.numeric_value),
                    carried=c.is_carried_forward, special=c.special_code, maximum=text_number(c.assessment.maximum_marks),
                    minimum=text_number(c.assessment.minimum_marks)) for c in sorted(result.components, key=lambda c: c.component_type)])
            rows.append(payload)
    return rows


def source_metadata(job):
    report = job.report
    return dict(filename=job.original_filename, university=report.university, programme=report.programme,
        branch=report.branch, semester=report.semester, session=report.examination_session,
        type=report.examination_type, title=report.examination_title, confirmed_at=str(job.confirmed_at),
        parser=report.parser_version, validation=report.validation_status)


def dataset_hash(job):
    return digest(dict(metadata=source_metadata(job), rows=source_rows(job)))


def name_key(value):
    return ' '.join(str(value or '').split()).casefold()


def exam_key(value):
    return ''.join(re.findall(r'[A-Z0-9]+', str(value or '').upper()))


def row_identity(job, source):
    # IDs are deliberately absent: re-extraction may recreate database rows.
    attempt_key = digest([job.file_hash, source['prn'], source['subject_code']])
    return attempt_key, digest([attempt_key, source, job.report.semester, job.report.examination_session, job.report.examination_type])


def ese_candidate(c, source, subject, job):
    from assessment_services import policy_for
    if subject and policy_for(subject.subject_code,c['semester_id'],c['academic_year']):
        return None, 'This course uses configured assessments; retain university evidence and enter scores through its approved policy.'
    if (job.report.examination_type or '').upper() != 'REGULAR':
        return None, 'Repeat/backlog/other examination: retain history only.'
    if (source.get('registration_scope') or '').upper() not in {'WHOLE', 'REGULAR', ''}:
        return None, 'Partial/repeat registration: retain history only.'
    if (source.get('attempt_session') and exam_key(source['attempt_session']) != exam_key(job.report.examination_session)):
        return None, 'Printed attempt label differs from this examination; retain history only until verified.'
    if source['student_status'] == 'CANCEL' or source.get('total_special') or source.get('total_carried'):
        return None, 'Cancelled, special or carried-forward result: retain history only.'
    if subject.subject_type != 'THEORY' or subject.is_audit or subject.is_attendance_only or source['audit']:
        return None, 'Only standard theory ESE can populate the current external marks.'
    components = [v for v in source['components'] if v['type'].upper().startswith('ESE')]
    if len(components) != 1 or components[0]['type'].upper() != 'ESE':
        return None, 'A single printed ESE component is required.'
    value = components[0]
    try:
        numeric = Decimal(value['value'])
        compatible = Decimal(value['maximum']) == 60 and Decimal(source['maximum']) == 100
        compatible = compatible and value['minimum'] is not None and Decimal(value['minimum']) == 20
        compatible = compatible and numeric.is_finite() and 0 <= numeric <= 60 and numeric == numeric.quantize(Decimal('.1'))
    except (InvalidOperation, TypeError, ValueError):
        compatible = False
    if not compatible or value['carried'] or value['special']:
        return None, 'ESE is missing, special, carried forward, or its scale/precision differs from the current /60 rules.'
    selection = dict(prn=source['prn'], subject_code=subject.subject_code, semester_id=c['semester_id'], academic_year=c['academic_year'])
    external = ExternalMarks.query.filter_by(**selection).first()
    theory = TheoryMarks.query.filter_by(**selection).first()
    accepted = AcceptedCourseworkMark.query.filter_by(**selection, category='EXTERNAL').first()
    if accepted or (external and (external.locked or external.external_marks is not None)) or (theory and theory.external is not None):
        return None, 'An external value/absence is already recorded or locked. History can be linked; use Mark corrections to change current marks.'
    return format(numeric, 'f'), 'Compatible empty theory ESE: may be filled after explicit selection.'


def build_rows(job, c, mappings):
    rows = []
    for source in source_rows(job):
        proposed = mappings.get(source['subject_code'], {})
        code, note = proposed.get('code', ''), proposed.get('note', '')
        student = db.session.get(Student, source['prn'])
        subject = db.session.get(Subject, code) if code else None
        issues = []
        if not student:
            issues.append('PRN has no local student profile. Configure the real roster first.')
        elif name_key(student.name) != name_key(source['name']):
            issues.append('PRN matches but the student names differ. Resolve the identity before linking.')
        if not subject or not subject.is_active or subject.semester_id != c['semester_id']:
            issues.append('Choose an active local subject from this semester.')
        else:
            if subject.is_elective and not subject.parent_subject_code:
                issues.append('A bucket parent cannot receive student results. Map the real option.')
            if code != source['subject_code'] and len(note.strip()) < 10:
                issues.append('A different code requires a verified mapping reason (10–1000 characters).')
            elif code == source['subject_code'] and name_key(subject.subject_name) != name_key(source['subject_name']) and len(note.strip()) < 10:
                issues.append('Subject names differ; enter a verified mapping reason before linking.')
            if source['credits'] is None or Decimal(source['credits']) != Decimal(subject.credits or 0) or bool(subject.is_audit) != bool(source['audit']):
                issues.append('Credits/audit status differ from the local curriculum. Resolve the subject mapping.')
            if student and not Enrollment.query.filter_by(prn=student.prn, subject_code=code, semester_id=c['semester_id'], academic_year=c['academic_year']).first():
                issues.append('Student is not enrolled in this subject and teaching year.')
        if source['subject_validation'] in {'ERROR', 'NOT_VALIDATED'} or source['validation'] in {'ERROR', 'NOT_VALIDATED'}:
            issues.append('The source student/result needs extraction review.')
        if not any(source.get(k) for k in ('grade', 'grade_raw', 'audit_grade', 'total', 'total_special')) and not any(v.get('value') is not None or v.get('special') for v in source['components']):
            issues.append('No printed result evidence (possibly an unselected elective).')
        attempt_key, evidence_key = row_identity(job, source)
        prior = UniversityLinkedResult.query.filter_by(attempt_key=attempt_key).first()
        if prior and (prior.prn != source['prn'] or prior.subject_code != code or prior.semester_id != c['semester_id'] or prior.academic_year != c['academic_year']):
            issues.append('This source result was already linked to another context. Its historical mapping was preserved.')
        duplicate = UniversityLinkedResult.query.filter_by(evidence_key=evidence_key).first() is not None
        ese, explanation = ese_candidate(c, source, subject, job) if not issues and subject else (None, 'Resolve matching issues first.')
        rows.append(dict(index=len(rows), prn=source['prn'], name=source['name'], local_code=code,
            local_name=subject.subject_name if subject else '', mapping_note=note, source=source,
            issues=issues, duplicate=duplicate, ready=not issues and not duplicate, ese=ese, ese_note=explanation,
            attempt_key=attempt_key, evidence_key=evidence_key))
    groups = {}
    for row in rows:
        if row['ready']:
            groups.setdefault((row['prn'], row['local_code']), []).append(row)
    for group in groups.values():
        if len(group) > 1:
            for row in group:
                row['issues'].append('Multiple printed subjects map to one local subject for this student. Resolve the mapping.')
                row['ready'] = False
                row['ese'] = None
    return rows


def snapshot(job, c, mappings):
    codes = sorted({v['code'] for v in mappings.values() if v.get('code')})
    local = []
    for code in codes:
        subject = db.session.get(Subject, code)
        local.append((subject.to_dict() if subject else None, coursework.fingerprint(dict(c, subject_code=code, division='', batch=''))))
    return digest(dict(source=dataset_hash(job), mappings=mappings, local=local,
        students=[s.to_dict() for s in Student.query.filter(Student.prn.in_([s.seat_number for s in job.report.students])).order_by(Student.prn)],
        links=[(r.evidence_key, r.subject_code, r.academic_year) for r in UniversityLinkedResult.query.filter(
            UniversityLinkedResult.attempt_key.in_([row_identity(job, s)[0] for s in source_rows(job)])).order_by(UniversityLinkedResult.id)]))


def preview(job, values):
    semester = confirmed_job(job)
    year = normalize_academic_year(values.get('academic_year'))
    if not db.session.get(Semester, (semester, year)):
        raise ValueError('Create/select the actual teaching semester/year before linking. It is not inferred from the examination date.')
    mappings = {}
    for subject in job.report.subjects:
        code = str(values.get(f'map_{subject.id}', subject.subject_code)).strip().upper()
        note = str(values.get(f'note_{subject.id}', '')).strip()
        if len(code) > 20 or len(note) > 1000:
            raise ValueError('Local subject code: at most 20 characters; mapping reason: at most 1000.')
        mappings[subject.subject_code] = dict(code=code, note=note)
    content = source_bytes(job)
    c = dict(job_id=job.id, semester_id=semester, academic_year=year, mappings=mappings,
        metadata=source_metadata(job), dataset_hash=dataset_hash(job))
    rows = build_rows(job, c, mappings)
    if not rows:
        raise ValueError('No extracted subject results are available to link.')
    review = WorkflowReview(owner_id=current_user.user_id, kind='UNIVERSITY_LINK', context=c, rows=rows,
        snapshot=snapshot(job, c, mappings), source_name=job.original_filename,
        source_hash=job.file_hash, source_workbook=content)
    db.session.add(review)
    db.session.commit()
    return review


def confirm(review, selected, copy_ese):
    if review.confirmed_at:
        return False
    expires = review.expires_at.replace(tzinfo=timezone.utc) if review.expires_at.tzinfo is None else review.expires_at
    if expires <= now():
        raise ValueError('Preview expired. Create a fresh linking preview.')
    c = review.context
    job = db.session.execute(db.select(ImportJob).where(ImportJob.id == c['job_id']).with_for_update()).scalar_one_or_none()
    confirmed_job(job)
    db.session.execute(db.select(Subject).where(Subject.subject_code.in_([r['local_code'] for r in review.rows if r['ready']])).order_by(Subject.subject_code).with_for_update()).all()
    if sha256(source_bytes(job)).hexdigest() != review.source_hash or snapshot(job, c, c['mappings']) != review.snapshot:
        raise ValueError('Source data, students, enrollments or marks changed. Create a fresh preview; no records were changed.')
    if not selected or not copy_ese.issubset(selected):
        raise ValueError('Select result rows to link. ESE copying must refer only to selected rows.')
    by_index = {str(r['index']): r for r in review.rows}
    if not selected.issubset(by_index) or any(not by_index[i]['ready'] for i in selected):
        raise ValueError('One or more selected rows are unmatched, already linked, or invalid.')
    if any(by_index[i]['ese'] is None for i in copy_ese):
        raise ValueError('ESE copying was requested for an incompatible or locked result.')
    if db.session.execute(update(WorkflowReview).where(WorkflowReview.token == review.token,
        WorkflowReview.claimed.is_(False), WorkflowReview.confirmed_at.is_(None)).values(claimed=True)).rowcount != 1:
        raise ValueError('This preview was already processed. Reload before continuing.')
    publication = UniversityPublication(review_token=review.token, source_job_id=job.id, source_hash=job.file_hash,
        dataset_hash=c['dataset_hash'], semester_id=c['semester_id'], academic_year=c['academic_year'],
        examination_session=job.report.examination_session, examination_type=job.report.examination_type,
        metadata_snapshot=c['metadata'], actor_id=current_user.user_id)
    db.session.add(publication)
    db.session.flush()
    for index in sorted(selected, key=int):
        row = by_index[index]
        db.session.add(UniversityLinkedResult(publication_token=publication.token, evidence_key=row['evidence_key'], attempt_key=row['attempt_key'],
            prn=row['prn'], student_name=db.session.get(Student, row['prn']).name, subject_code=row['local_code'],
            semester_id=c['semester_id'], academic_year=c['academic_year'], source=row['source'],
            mapping_note=row['mapping_note'], ese_copied=index in copy_ese))
        if index in copy_ese:
            selection = dict(prn=row['prn'], subject_code=row['local_code'], semester_id=c['semester_id'], academic_year=c['academic_year'])
            mark = ExternalMarks.query.filter_by(**selection).first()
            if not mark:
                mark = ExternalMarks(**selection)
                db.session.add(mark)
            mark.external_marks, mark.locked = Decimal(row['ese']), True
            db.session.add(AcceptedCourseworkMark(**selection, category='EXTERNAL', component='EXTERNAL', value=Decimal(row['ese']),
                state='PRESENT', review_token=review.token, actor_id=current_user.user_id))
    db.session.flush()
    for index in copy_ese:
        row = by_index[index]
        coursework.recalculate(dict(c, subject_code=row['local_code']), [row['prn']])
    review.context = dict(review.context, approved_rows=sorted(selected, key=int), copied_rows=sorted(copy_ese, key=int))
    review.confirmed_at = now()
    audit(current_user, 'university_results_linked', dict(publication=publication.token, review=review.token,
        source_hash=job.file_hash, results=len(selected), ese_filled=len(copy_ese), academic_year=c['academic_year']))
    db.session.commit()
    return True
