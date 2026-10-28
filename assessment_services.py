"""Approved assessment definitions and independently reviewed component scores."""
import csv
import io
import json
import re
from hashlib import sha256
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import abort
from flask_login import current_user
from models import db, Subject, TheoryMarks, LabMarks, ExternalMarks
from completion_models import AssessmentPolicy, AssessmentScore, AssessmentScoreChange
from workflow_models import WorkflowReview, now
from routes_teaching import audit
from teaching_access import require_assignment
from academic_link_services import digest
import workflow_services as core


DEFAULT_RULES = {
    'components': [dict(code='CT1', label='Class test 1', maximum=10), dict(code='CT2', label='Class test 2', maximum=10),
        dict(code='ASSIGNMENT', label='Assignment', maximum=10), dict(code='MSE', label='Mid-semester', maximum=20),
        dict(code='ESE', label='University examination', maximum=60, minimum=20, absence_fails=True)],
    'groups': [dict(label='Continuous assessment', components=['CT1','CT2','ASSIGNMENT'], method='BEST_N', best_n=2, maximum=20, category='INTERNAL'),
        dict(label='Mid-semester', components=['MSE'], method='SUM', maximum=20, category='INTERNAL'),
        dict(label='End-semester', components=['ESE'], method='SUM', maximum=60, category='EXTERNAL')],
    'total_minimum':40,
    'grades':[dict(minimum_percent=p, grade=g, point=gp) for p,g,gp in [(91,'EX',10),(86,'AA',9),(81,'AB',8.5),(76,'BB',8),
        (71,'BC',7.5),(66,'CC',7),(61,'CD',6.5),(56,'DD',6),(51,'DE',5.5),(0,'EE',5)]]
}


def number(value, label, minimum=0, maximum=10000):
    if isinstance(value, bool):
        raise ValueError(label + ': enter a finite number.')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(label + ': enter a finite number.')
    if not result.is_finite() or not Decimal(str(minimum)) <= result <= Decimal(str(maximum)):
        raise ValueError(f'{label}: use {minimum} to {maximum}.')
    if result != result.quantize(Decimal('.01')):
        raise ValueError(label + ': at most two decimal places.')
    return result


def validate_rules(raw):
    try:
        rules = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(rules, dict):
            raise ValueError('Rules must be a JSON object.')
        components, groups, grades = rules['components'], rules['groups'], rules['grades']
        if not isinstance(components,list) or not 1 <= len(components) <= 20 or not isinstance(groups,list) or not 1 <= len(groups) <= 10:
            raise ValueError('Use 1–20 components and 1–10 groups.')
        codes = set()
        for c in components:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,19}', c['code']) or c['code'] in codes:
                raise ValueError('Component codes must be unique uppercase identifiers, at most 20 characters.')
            if not isinstance(c['label'],str) or not 1 <= len(c['label'].strip()) <= 100:
                raise ValueError('Enter a component label, at most 100 characters.')
            maximum = number(c['maximum'], c['code'] + ' maximum', .01, 1000)
            number(c.get('minimum', 0), c['code'] + ' minimum', 0, maximum)
            if type(c.get('absence_fails',False)) is not bool:
                raise ValueError('absence_fails must be true or false.')
            codes.add(c['code'])
        assigned = []
        total = Decimal(0)
        for g in groups:
            if not isinstance(g['label'],str) or not 1 <= len(g['label'].strip()) <= 100 or g['category'] not in {'INTERNAL','EXTERNAL'}:
                raise ValueError('Groups need a label and INTERNAL or EXTERNAL category.')
            if g['method'] not in {'SUM','BEST_N'} or not isinstance(g['components'],list) or not g['components']:
                raise ValueError('Groups use SUM or BEST_N and contain component codes.')
            if any(code not in codes for code in g['components']):
                raise ValueError('A group refers to an unknown component.')
            assigned.extend(g['components'])
            if g['method'] == 'BEST_N' and (type(g.get('best_n')) is not int or not 1 <= g['best_n'] <= len(g['components'])):
                raise ValueError('BEST_N needs a whole best_n within its component count.')
            # Selecting scores with different raw maxima is ambiguous: require equal scales.
            maxima = {Decimal(str(next(c['maximum'] for c in components if c['code']==code))) for code in g['components']}
            if g['method'] == 'BEST_N' and len(maxima) != 1:
                raise ValueError('BEST_N components must share a maximum mark.')
            maximum = number(g['maximum'], 'Group maximum', .01, 1000)
            number(g.get('minimum',0), 'Group minimum', 0, maximum)
            total += maximum
        if len(assigned) != len(set(assigned)) or set(assigned) != codes:
            raise ValueError('Every component must belong to exactly one group.')
        number(rules['total_minimum'], 'Total passing minimum', 0, total)
        if not isinstance(grades,list) or not 1 <= len(grades) <= 20:
            raise ValueError('Enter 1–20 passing grade bands.')
        previous = Decimal(101)
        previous_point = Decimal(11)
        labels = set()
        for band in grades:
            threshold = number(band['minimum_percent'], 'Grade threshold', 0, 100)
            point = number(band['point'], 'Grade point', .01, 10)
            if threshold >= previous or point > previous_point or not re.fullmatch(r'[A-Z0-9+_-]{1,10}', band['grade']) or band['grade'] in labels:
                raise ValueError('Grade thresholds descend strictly; points cannot increase in lower bands; labels must be unique.')
            labels.add(band['grade'])
            if band['grade'] in {'FF','F','ABSENT','PENDING','REVIEW'}:
                raise ValueError('Use passing grade labels; FF / 0 is reserved for failures.')
            previous, previous_point = threshold, point
        if previous != 0:
            raise ValueError('The final passing grade band must start at 0%. Failing results always receive FF / 0.')
        # Round-trip rejects unserializable values and freezes only validated fields.
        return json.loads(json.dumps(rules, allow_nan=False))
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Incomplete assessment definition. Use the supplied example structure.') from error


def policy_for(subject_code, semester_id, academic_year):
    return AssessmentPolicy.query.filter_by(subject_code=subject_code, semester_id=semester_id, academic_year=academic_year, status='APPROVED').first()


def legacy_marks(c):
    keys = {k:c[k] for k in ('subject_code','semester_id','academic_year')}
    from workflow_models import AcceptedInternalMark
    from coursework_models import AcceptedCourseworkMark
    return any(model.query.filter_by(**keys).first() is not None for model in (TheoryMarks, LabMarks, ExternalMarks, AcceptedInternalMark, AcceptedCourseworkMark))


def create_policy(values):
    c = core.subject_context(values)
    subject = db.session.get(Subject, c['subject_code'])
    if subject.is_audit or subject.is_attendance_only:
        raise ValueError('Attendance-only/audit courses do not receive numeric assessment policies.')
    title, source = str(values.get('title','')).strip(), str(values.get('source_reference','')).strip()
    if not 1 <= len(title) <= 180 or not 10 <= len(source) <= 1000:
        raise ValueError('Enter a title and a source clause/reference of 10–1,000 characters.')
    if AssessmentPolicy.query.filter_by(**{k:c[k] for k in ('subject_code','semester_id','academic_year')}).first():
        raise ValueError('This subject/term already has a policy. Review its draft or use another teaching term.')
    if legacy_marks(c):
        raise ValueError('This term already has legacy marks. Preserve its existing rules; configure a policy before marks are recorded in a new term.')
    policy = AssessmentPolicy(**{k:c[k] for k in ('subject_code','semester_id','academic_year')}, title=title,
        rules=validate_rules(values.get('rules','')), source_reference=source, actor_id=current_user.user_id)
    db.session.add(policy)
    audit(current_user, 'assessment_policy_drafted', dict(**c, title=title))
    db.session.commit()
    return policy


def approve(policy, revision):
    db.session.execute(db.select(Subject).where(Subject.subject_code==policy.subject_code).with_for_update()).scalar_one()
    if policy.status == 'APPROVED':
        return False
    if str(policy.revision) != str(revision):
        raise ValueError('The draft changed. Reload and review it.')
    validate_rules(policy.rules)
    if legacy_marks(vars_context(policy)):
        raise ValueError('Marks were entered after this draft. Approval was blocked to preserve their original calculations.')
    claimed = db.session.execute(db.update(AssessmentPolicy).where(AssessmentPolicy.token==policy.token,
        AssessmentPolicy.status=='DRAFT', AssessmentPolicy.revision==policy.revision).values(status='APPROVED',approved_at=now(),actor_id=current_user.user_id)).rowcount
    if claimed != 1:
        raise ValueError('The policy changed concurrently. Reload before approving.')
    audit(current_user, 'assessment_policy_approved', dict(policy=policy.token, source=policy.source_reference))
    db.session.commit()
    return True


def edit_draft(policy, values):
    if policy.status!='DRAFT':
        raise ValueError('Approved assessment rules are immutable.')
    rules=validate_rules(values.get('rules',''))
    title,source=str(values.get('title','')).strip(),str(values.get('source_reference','')).strip()
    if not 1<=len(title)<=180 or not 10<=len(source)<=1000:
        raise ValueError('Enter a title and a source reference of 10–1,000 characters.')
    try:
        revision=int(values.get('revision'))
    except (TypeError,ValueError):
        raise ValueError('Reload the draft before editing.')
    count=db.session.execute(db.update(AssessmentPolicy).where(AssessmentPolicy.token==policy.token,AssessmentPolicy.status=='DRAFT',
        AssessmentPolicy.revision==revision).values(rules=rules,title=title,source_reference=source,revision=revision+1)).rowcount
    if count!=1:
        raise ValueError('The assessment draft changed. Reload it.')
    audit(current_user,'assessment_policy_draft_edited',dict(policy=policy.token,revision=revision+1))
    db.session.commit()


def vars_context(policy):
    return dict(subject_code=policy.subject_code, semester_id=policy.semester_id, academic_year=policy.academic_year, division='', batch='')


def evaluate(policy, values):
    rules = policy.rules
    components = {c['code']:c for c in rules['components']}
    pending = any(code not in values or values[code].get('state') not in {'PRESENT','ABSENT'} for code in components)
    result = dict(internal=None, external=None, total=None, grade=None, grade_point=None, result='PENDING', groups=[])
    if pending:
        return result
    passed = True
    numeric = {}
    for code,c in components.items():
        v = values[code]
        if v['state'] == 'ABSENT':
            numeric[code] = Decimal(0)
            passed = passed and not c.get('absence_fails',False) and Decimal(0)>=Decimal(str(c.get('minimum',0)))
        else:
            numeric[code] = number(v['value'], code, 0, c['maximum'])
            passed = passed and numeric[code] >= Decimal(str(c.get('minimum',0)))
    internal, external = Decimal(0), Decimal(0)
    maximum = Decimal(0)
    for group in rules['groups']:
        selected = sorted(group['components'], key=lambda code:numeric[code], reverse=True)
        if group['method'] == 'BEST_N':
            selected = selected[:group['best_n']]
        raw_max = sum(Decimal(str(components[code]['maximum'])) for code in selected)
        raw = sum(numeric[code] for code in selected)
        contribution = (raw / raw_max * Decimal(str(group['maximum']))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        passed = passed and contribution >= Decimal(str(group.get('minimum',0)))
        if group['category']=='INTERNAL':
            internal += contribution
        else:
            external += contribution
        maximum += Decimal(str(group['maximum']))
        result['groups'].append(dict(label=group['label'], value=float(contribution), maximum=group['maximum']))
    total = internal + external
    passed = passed and total >= Decimal(str(rules['total_minimum']))
    grade, point = 'FF', Decimal(0)
    if passed:
        band = next(b for b in rules['grades'] if total / maximum * 100 >= Decimal(str(b['minimum_percent'])))
        grade, point = band['grade'], Decimal(str(band['point']))
    result.update(internal=float(internal), external=float(external), total=float(total), grade=grade,
        grade_point=float(point), result='PASS' if passed else 'FAIL')
    return result


def result_for(policy, prn):
    score = AssessmentScore.query.filter_by(policy_token=policy.token, prn=prn).first()
    return evaluate(policy, score.values if score else {})


def fingerprint(policy):
    c = vars_context(policy)
    return digest(dict(policy=policy.rules, status=policy.status, roster=[(s.prn,s.name,s.division,s.batch) for s in core.roster(c)],
        scores=[(s.prn,s.values,s.revision) for s in AssessmentScore.query.filter_by(policy_token=policy.token).order_by(AssessmentScore.prn)]))


def template_metadata(policy):
    return {'Subject code':policy.subject_code,'Semester':str(policy.semester_id),'Teaching year':policy.academic_year,
        'Policy fingerprint':digest(dict(token=policy.token,rules=policy.rules))}


def template_workbook(policy, students, scores):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    book=Workbook()
    sheet=book.active
    sheet.title='Configured Marks'
    codes=[c['code'] for c in policy.rules['components']]
    sheet.append(['Sr. No.','PRN','Student Name']+codes)
    for i,s in enumerate(students,1):
        values=scores[s.prn].values if s.prn in scores else {}
        sheet.append([i,s.prn,s.name]+['AB' if values.get(code,{}).get('state')=='ABSENT' else
            float(values[code]['value']) if values.get(code,{}).get('value') is not None else None for code in codes])
    meta=book.create_sheet('_meta')
    for key,value in template_metadata(policy).items():
        meta.append([key,value])
    meta.sheet_state='hidden'
    sheet.freeze_panes='D2'
    for i in range(1,len(codes)+4):
        sheet.column_dimensions[get_column_letter(i)].width=10 if i==1 else 24 if i==2 else 34 if i==3 else 18
    for row in sheet:
        sheet.row_dimensions[row[0].row].height=30
        for cell in row:
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if cell.row==1:
                cell.font=Font(name='Calibri',bold=True,color='FFFFFF')
                cell.fill=PatternFill('solid',fgColor='14283F')
            if isinstance(cell.value,str):
                cell.data_type='s'
            if cell.column==2:
                cell.number_format='@'
    stream=io.BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


def parse_scores(policy, content, filename='marks.csv'):
    if len(content)>5*1024*1024:
        raise ValueError('Marks CSV must be at most 5 MB.')
    try:
        expected_meta=template_metadata(policy)
        if filename.lower().endswith('.xlsx'):
            from openpyxl import load_workbook
            try:
                book=load_workbook(io.BytesIO(content),data_only=False)
            except Exception as error:
                raise ValueError('Cannot read this XLSX marks template.') from error
            if '_meta' not in book.sheetnames or 'Configured Marks' not in book.sheetnames:
                raise ValueError('Use the generated configured marks workbook, including its metadata.')
            if any(s.max_row>5001 or s.max_column>30 for s in book):
                raise ValueError('Marks workbook exceeds the supported roster/component size.')
            metadata={str(row[0]):str(row[1]) for row in book['_meta'].iter_rows(max_col=2,values_only=True) if row[0]}
            sheet=book['Configured Marks']
            for row in sheet:
                if any(c.data_type=='f' for c in row):
                    raise ValueError('Enter marks as numbers or AB; formulas are not accepted.')
                if row[0].row>1 and row[1].value is not None and not isinstance(row[1].value,str):
                    raise ValueError('PRNs must remain text to preserve every digit and leading zero.')
            rows=list(sheet.iter_rows(values_only=True))
            reader=[dict(zip(rows[0],row)) for row in rows[1:]] if rows else []
            fieldnames=list(rows[0]) if rows else []
        elif filename.lower().endswith('.csv'):
            lines=csv.reader(io.StringIO(content.decode('utf-8-sig')))
            if next(lines,None)!=['ACADPULSE configured assessment marks']:
                raise ValueError('Use the generated configured marks CSV with its context header.')
            metadata={}
            for _ in expected_meta:
                row=next(lines,[])
                if len(row)!=2:
                    raise ValueError('Marks CSV context metadata is missing.')
                metadata[row[0]]=row[1]
            if next(lines,None)!=[]:
                raise ValueError('Keep the blank row after the CSV context header.')
            fieldnames=next(lines,[])
            reader=[dict(zip(fieldnames,row)) for row in lines]
        else:
            raise ValueError('Upload the generated .xlsx workbook or CSV UTF-8 template.')
        if any(metadata.get(k)!=v for k,v in expected_meta.items()):
            raise ValueError('Marks file belongs to another policy, subject, semester or teaching year. Download a fresh template.')
        codes = [c['code'] for c in policy.rules['components']]
        if fieldnames != ['Sr. No.','PRN','Student Name'] + codes:
            raise ValueError('Use this policy’s generated CSV template with its exact component headers.')
        roster = {s.prn:s for s in core.roster(vars_context(policy))}
        seen, rows = set(), []
        for line,row in enumerate(reader, 2):
            if not any(str(v or '').strip() for v in row.values()):
                continue
            prn = str(row.get('PRN') or '').strip()
            if prn not in roster or prn in seen:
                raise ValueError(f'Row {line}: unknown, unenrolled or duplicate PRN.')
            if ' '.join(row['Student Name'].split()).casefold() != ' '.join(roster[prn].name.split()).casefold():
                raise ValueError(f'Row {line}: name differs from the enrolled student.')
            values = {}
            for c in policy.rules['components']:
                original = row.get(c['code'])
                raw = str(original if original is not None else '').strip()
                if raw.upper() in {'AB','ABSENT'}:
                    values[c['code']] = dict(state='ABSENT',value=None)
                elif not raw:
                    values[c['code']] = dict(state='PENDING',value=None)
                else:
                    values[c['code']] = dict(state='PRESENT',value=str(number(raw,c['label'],0,c['maximum'])))
            seen.add(prn)
            rows.append(dict(prn=prn,name=roster[prn].name,values=values,result=evaluate(policy,values)))
            if len(rows)>5000:
                raise ValueError('Use at most 5,000 students per CSV.')
        if not rows:
            raise ValueError('No enrolled student rows were provided.')
        return rows
    except UnicodeDecodeError as error:
        raise ValueError('Save the template as CSV UTF-8.') from error
    except (csv.Error, TypeError, AttributeError) as error:
        raise ValueError('Malformed CSV. Use the policy template.') from error


def preview(policy, content, reason, filename='configured-marks.csv'):
    if policy.status != 'APPROVED':
        raise ValueError('Approve the assessment definition first.')
    require_assignment(policy.subject_code,policy.semester_id,policy.academic_year)
    rows = parse_scores(policy,content,filename)
    correction = AssessmentScore.query.filter(AssessmentScore.policy_token==policy.token,AssessmentScore.prn.in_([r['prn'] for r in rows])).first() is not None
    reason = str(reason or '').strip()
    if len(reason)>1000 or (correction and len(reason)<10):
        raise ValueError('Changes to submitted scores need a reason of 10–1,000 characters and administrator approval.')
    from werkzeug.utils import secure_filename
    review = WorkflowReview(owner_id=current_user.user_id,kind='CONFIGURED_MARKS',context=dict(policy_token=policy.token,
        correction=correction,reason=reason or 'Initial reviewed score submission'),rows=rows,snapshot=fingerprint(policy),
        source_name=secure_filename(filename),source_hash=sha256(content).hexdigest(),source_workbook=content)
    db.session.add(review)
    db.session.commit()
    return review


def confirm(review):
    from completion_services import claim
    current=db.session.get(AssessmentPolicy,review.context['policy_token'])
    if not current:
        raise ValueError('Assessment policy is unavailable.')
    db.session.execute(db.select(Subject).where(Subject.subject_code==current.subject_code).with_for_update()).scalar_one()
    policy = db.session.execute(db.select(AssessmentPolicy).where(AssessmentPolicy.token==review.context['policy_token']).with_for_update()).scalar_one()
    require_assignment(policy.subject_code,policy.semester_id,policy.academic_year)
    if current_user.role!='ADMIN' and (review.owner_id!=current_user.user_id or review.context['correction']):
        abort(403,'Submitted-score changes require administrator approval.')
    if review.confirmed_at:
        return False
    claim(review)
    if policy.status!='APPROVED' or fingerprint(policy)!=review.snapshot:
        raise ValueError('The policy, roster or marks changed. Create a fresh preview.')
    for row in review.rows:
        score = AssessmentScore.query.filter_by(policy_token=policy.token,prn=row['prn']).first()
        previous = score.values if score else None
        db.session.add(AssessmentScoreChange(policy_token=policy.token,prn=row['prn'],previous=previous,approved=row['values'],
            reason=review.context['reason'],review_token=review.token,actor_id=current_user.user_id))
        if score:
            score.values, score.revision, score.review_token, score.updated_at = row['values'],score.revision+1,review.token,now()
        else:
            db.session.add(AssessmentScore(policy_token=policy.token,prn=row['prn'],values=row['values'],review_token=review.token))
    db.session.flush()
    import models
    from calculations import update_sgpa_cgpa_for_student
    for row in review.rows:
        update_sgpa_cgpa_for_student(row['prn'],policy.semester_id,policy.academic_year,db,models,commit=False)
    review.confirmed_at = now()
    audit(current_user,'configured_scores_approved',dict(policy=policy.token,review=review.token,rows=len(review.rows),correction=review.context['correction']))
    db.session.commit()
    return True
