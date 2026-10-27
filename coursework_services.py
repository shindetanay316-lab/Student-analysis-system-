"""Shared lab/ESE preview, immutable evidence and controlled corrections."""
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone
from hashlib import sha256
import json
from flask import abort
from flask_login import current_user
from models import db,Subject,Student,Enrollment,TheoryMarks,LabMarks,ExternalMarks,User
from teaching_models import StaffAccessAudit
from teaching_access import require_assignment,permitted
from workflow_models import WorkflowReview,AcceptedInternalMark
from coursework_models import AcceptedCourseworkMark,MarkRevision
import workflow_services as core

SPECS={'LAB':{'CA1':('ca1',30,2),'CA2':('ca2',30,2),'LAB_EXTERNAL':('external',40,2)},
       'EXTERNAL':{'EXTERNAL':('external_marks',60,1)},
       'INTERNAL':{key:(field,maximum,2) for key,(field,maximum) in core.COMPONENTS.items()}}
KINDS={'LAB':'LAB_MARKS','EXTERNAL':'EXTERNAL_MARKS'}


def keys(context):return {k:context[k] for k in ('subject_code','semester_id','academic_year')}


def validate_category(context,category):
    if category not in SPECS:raise ValueError('Invalid assessment group.')
    subject=db.session.get(Subject,context['subject_code'])
    valid=subject and subject.is_active and not subject.is_audit and not subject.is_attendance_only
    if not valid or (category=='LAB' and subject.subject_type not in {'LAB','PROJECT'}) or (category!='LAB' and subject.subject_type!='THEORY'):
        raise ValueError('Choose the correct theory or lab/project subject for this assessment.')


def value_state(raw,category,component):
    if category not in SPECS or component not in SPECS[category]:raise ValueError('Invalid assessment component.')
    if raw is None or not str(raw).strip():raise ValueError('Mark is missing. Enter a number or A for absent.')
    if str(raw).strip().upper() in {'A','AB','ABSENT'}:return {'value':None,'state':'ABSENT'}
    _,maximum,precision=SPECS[category][component]
    try:
        value=Decimal(str(raw))
        valid=value.is_finite() and 0<=value<=maximum and value.as_tuple().exponent>=-precision
    except (InvalidOperation,ValueError):valid=False
    if not valid:raise ValueError(f'{component}: enter 0–{maximum}, at most {precision} decimal place(s), or A.')
    return {'value':format(value.normalize(),'f'),'state':'PRESENT'}


def effective_states(context):
    states={}
    for row in AcceptedInternalMark.query.filter_by(**keys(context)):
        states[(row.prn,'INTERNAL',row.component)]=row.state
    for row in AcceptedCourseworkMark.query.filter_by(**keys(context)):
        states[(row.prn,row.category,row.component)]=row.state
    for row in approved_revisions(context):states[(row.prn,row.category,row.component)]=row.proposed['state']
    return states


def approved_revisions(context):
    return MarkRevision.query.filter(MarkRevision.status=='APPROVED',
        MarkRevision.context['subject_code'].as_string()==context['subject_code'],
        MarkRevision.context['semester_id'].as_integer()==context['semester_id'],
        MarkRevision.context['academic_year'].as_string()==context['academic_year']).order_by(MarkRevision.decided_at,MarkRevision.token).all()


def internal_states(context):
    return {(prn,core.COMPONENTS[component][0]):state for (prn,category,component),state in effective_states(context).items() if category=='INTERNAL'}


def fingerprint(context):
    selection=keys(context)
    data={'roster':[(s.prn,s.name,s.division,s.batch) for s in core.roster(context)],
        'theory':[(r.prn,str(r.ct1),str(r.ct2),str(r.assignment),str(r.midsem),str(r.external)) for r in TheoryMarks.query.filter_by(**selection).order_by(TheoryMarks.prn)],
        'lab':[(r.prn,str(r.ca1),str(r.ca2),str(r.internal),str(r.external)) for r in LabMarks.query.filter_by(**selection).order_by(LabMarks.prn)],
        'external':[(r.prn,str(r.external_marks),r.locked) for r in ExternalMarks.query.filter_by(**selection).order_by(ExternalMarks.prn)],
        'accepted':[(r.prn,r.category,r.component,r.state,str(r.value)) for r in AcceptedCourseworkMark.query.filter_by(**selection).order_by(AcceptedCourseworkMark.id)],
        'revisions':[r.token for r in approved_revisions(context)]}
    return sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def parse_upload(file,context,category):
    validate_category(context,category)
    book=core.workbook(file);sheet=book.active
    if '_meta' not in book.sheetnames:raise ValueError('Download a fresh template; its academic context is required.')
    meta={str(r[0]):str(r[1] or '').strip() for r in book['_meta'].iter_rows(min_row=1,max_row=8,max_col=2,values_only=True) if r[0]}
    if any(meta.get(k,'')!=str(context[k]) for k in ('subject_code','semester_id','academic_year')):raise ValueError('This workbook belongs to another subject, semester or academic year.')
    if any((meta.get(k) or 'ALL')!=(context.get(k) or 'ALL') for k in ('division','batch')):raise ValueError('This workbook belongs to another division or batch.')
    header=next((n for n in range(1,min(sheet.max_row,30)+1) if str(sheet.cell(n,3).value).upper()=='PRN' and 'ROLL' in str(sheet.cell(n,2).value).upper()),None)
    if header is None:raise ValueError('Template headers were not found. Download a fresh official template.')
    students={s.prn:s for s in core.roster(context)}
    if not students:raise ValueError('No enrolled students match this subject/context. Configure its roster first.')
    columns={'CA1':5,'CA2':6,'LAB_EXTERNAL':8} if category=='LAB' else {'EXTERNAL':5}
    rows=[];seen=set();errors=[]
    for number in range(header+1,sheet.max_row+1):
        raw=sheet.cell(number,3).value
        if raw is None or str(raw).lower().startswith('note'):continue
        try:
            if not isinstance(raw,str) or sheet.cell(number,3).data_type=='f':raise ValueError('PRN must remain text as downloaded.')
            prn=raw.strip()
            if prn in seen:raise ValueError('Duplicate PRN in workbook.')
            seen.add(prn)
            if prn not in students:raise ValueError('Student is not enrolled in this subject/filter.')
            if ' '.join(str(sheet.cell(number,4).value or '').split()).casefold()!=' '.join(students[prn].name.split()).casefold():raise ValueError('Student name and PRN do not match the roster.')
            values={}
            for component,col in columns.items():
                cell=sheet.cell(number,col)
                if cell.data_type=='f':raise ValueError('Enter a mark, not an Excel formula.')
                values[component]=value_state(cell.value,category,component)
            rows.append({'prn':prn,'name':students[prn].name,'values':values})
        except ValueError as error:errors.append(f'Row {number}: {error}')
    if set(students)-seen:errors.append(f'{len(set(students)-seen)} enrolled student(s) are missing. Download a fresh template.')
    if errors:raise ValueError('\n'.join(errors[:25]))
    ensure_unlocked(context,category,rows);return rows


def ensure_unlocked(context,category,rows):
    selection=keys(context)
    accepted={r.prn for r in AcceptedCourseworkMark.query.filter_by(category=category,**selection)}
    model=LabMarks if category=='LAB' else ExternalMarks
    existing={r.prn:r for r in model.query.filter_by(**selection)}
    students={s.prn for s in core.roster(context)}
    for row in rows:
        if row['prn'] not in students:raise ValueError('Student enrollment changed. Create a fresh preview.')
        old=existing.get(row['prn'])
        legacy_locked=old is not None and (old.locked if category=='EXTERNAL' else any(getattr(old,k) is not None for k in ('ca1','ca2','internal','external')))
        if row['prn'] in accepted or legacy_locked:raise ValueError(f"{row['prn']}: marks are already submitted/locked. Request a correction instead of overwriting them.")


def recalculate(context,prns):
    import models
    from final_result_utils import recalculate_theory_result,recalculate_lab_result
    from calculations import update_sgpa_cgpa_for_student
    for prn in sorted(set(prns)):
        theory=TheoryMarks.query.filter_by(prn=prn,**keys(context)).first()
        external=ExternalMarks.query.filter_by(prn=prn,**keys(context)).first()
        if theory:
            if external:theory.external=external.external_marks
            recalculate_theory_result(theory)
        lab=LabMarks.query.filter_by(prn=prn,**keys(context)).first()
        if lab:recalculate_lab_result(lab)
        db.session.flush()
        update_sgpa_cgpa_for_student(prn,context['semester_id'],context['academic_year'],db,models,commit=False)


def confirm(review):
    context=review.context;core.subject_context(context)
    category='LAB' if review.kind=='LAB_MARKS' else 'EXTERNAL'
    validate_category(context,category)
    if review.owner_id!=current_user.user_id and current_user.role!='ADMIN':abort(403)
    require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    if review.confirmed_at:return False
    expiry=review.expires_at.replace(tzinfo=timezone.utc) if review.expires_at.tzinfo is None else review.expires_at
    if datetime.now(timezone.utc)>expiry:raise ValueError('This preview expired. Upload again.')
    db.session.execute(db.select(Subject).where(Subject.subject_code==context['subject_code']).with_for_update()).scalar_one()
    claim=db.session.execute(db.update(WorkflowReview).where(WorkflowReview.token==review.token,WorkflowReview.claimed.is_(False),WorkflowReview.confirmed_at.is_(None)).values(claimed=True)).rowcount
    if not claim:raise ValueError('This preview is already being confirmed. Refresh.')
    db.session.expire_all()
    if fingerprint(context)!=review.snapshot:raise ValueError('The roster, marks or correction history changed. Upload and review a fresh preview.')
    ensure_unlocked(context,category,review.rows)
    for row in review.rows:
        if category=='LAB':
            mark=LabMarks.query.filter_by(prn=row['prn'],**keys(context)).first()
            if mark is None:mark=LabMarks(prn=row['prn'],**keys(context));db.session.add(mark)
        else:
            mark=ExternalMarks.query.filter_by(prn=row['prn'],**keys(context)).first()
            if mark is None:mark=ExternalMarks(prn=row['prn'],**keys(context));db.session.add(mark)
            mark.locked=True
        for component,value in row['values'].items():
            numeric=Decimal(value['value']) if value['value'] is not None else None
            setattr(mark,SPECS[category][component][0],numeric)
            db.session.add(AcceptedCourseworkMark(prn=row['prn'],**keys(context),category=category,component=component,value=numeric,state=value['state'],review_token=review.token,actor_id=current_user.user_id))
        if category=='LAB':mark.internal=mark.ca1+mark.ca2 if mark.ca1 is not None and mark.ca2 is not None else None
    db.session.flush();recalculate(context,[r['prn'] for r in review.rows])
    review.confirmed_at=datetime.now(timezone.utc)
    db.session.add(StaffAccessAudit(actor_id=current_user.user_id,user_id=current_user.user_id,action=review.kind+'_CONFIRMED',details={'review':review.token,'context':context,'students':len(review.rows)}))
    db.session.commit();return True


def current_state(context,prn,category,component):
    validate_category(context,category)
    if component not in SPECS[category]:raise ValueError('Invalid assessment component.')
    model={'INTERNAL':TheoryMarks,'LAB':LabMarks,'EXTERNAL':ExternalMarks}[category]
    mark=model.query.filter_by(prn=prn,**keys(context)).first()
    value=getattr(mark,SPECS[category][component][0]) if mark else None
    state=effective_states(context).get((prn,category,component))
    if value is None and state!='ABSENT':raise ValueError('This component has no submitted mark to correct. Use a normal marks submission.')
    return {'value':format(Decimal(value).normalize(),'f') if value is not None else None,'state':'PRESENT' if value is not None else 'ABSENT'}


def propose(context,prn,category,component,raw,reason):
    core.subject_context(context);require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    if prn not in {s.prn for s in core.roster(context)}:raise ValueError('Select a student in this subject roster.')
    if len(reason.strip())<10 or len(reason)>1500:raise ValueError('Explain the correction in 10–1500 characters.')
    previous=current_state(context,prn,category,component);proposed=value_state(raw,category,component)
    if previous==proposed:raise ValueError('The proposed mark is unchanged.')
    revision=MarkRevision(requester_id=current_user.user_id,prn=prn,context=context,category=category,component=component,previous=previous,proposed=proposed,reason=reason.strip(),snapshot=fingerprint(context))
    db.session.add(revision);db.session.flush()
    db.session.add(StaffAccessAudit(actor_id=current_user.user_id,user_id=current_user.user_id,action='MARK_CORRECTION_REQUESTED',details={'revision':revision.token,'context':context,'prn':prn,'component':component}))
    db.session.commit();return revision


def decide(revision,approve,note):
    if current_user.role!='ADMIN':abort(403)
    if revision.status!='PENDING':return False
    if len(note)>1500 or (not approve and len(note.strip())<5):raise ValueError('Provide a rejection reason of at least five characters; notes must be at most 1500 characters.')
    context=revision.context
    if approve:core.subject_context(context)
    requester=db.session.get(User,revision.requester_id)
    if approve and (not requester or not requester.is_active or not permitted(requester,context['subject_code'],context['semester_id'],context['academic_year'])):raise ValueError('The requester no longer has access to this subject. An authorized teacher or administrator must create a fresh request.')
    db.session.execute(db.select(Subject).where(Subject.subject_code==context['subject_code']).with_for_update()).scalar_one()
    claim=db.session.execute(db.update(MarkRevision).where(MarkRevision.token==revision.token,MarkRevision.status=='PENDING',MarkRevision.claimed.is_(False)).values(claimed=True)).rowcount
    if not claim:raise ValueError('This correction is being decided. Refresh its status.')
    db.session.expire_all()
    if approve:
        if fingerprint(context)!=revision.snapshot or current_state(context,revision.prn,revision.category,revision.component)!=revision.previous:raise ValueError('Marks, roster or correction history changed. Reject this stale request and request a fresh correction.')
        if revision.prn not in {s.prn for s in core.roster(context)}:raise ValueError('This student is no longer enrolled in this subject.')
        model={'INTERNAL':TheoryMarks,'LAB':LabMarks,'EXTERNAL':ExternalMarks}[revision.category]
        mark=model.query.filter_by(prn=revision.prn,**keys(context)).one()
        setattr(mark,SPECS[revision.category][revision.component][0],Decimal(revision.proposed['value']) if revision.proposed['value'] is not None else None)
        if revision.category=='LAB':mark.internal=mark.ca1+mark.ca2 if mark.ca1 is not None and mark.ca2 is not None else None
        if revision.category=='EXTERNAL':mark.locked=True
        db.session.flush();recalculate(context,[revision.prn])
    revision.status='APPROVED' if approve else 'REJECTED';revision.approver_id=current_user.user_id;revision.decision_note=note.strip();revision.decided_at=datetime.now(timezone.utc)
    db.session.add(StaffAccessAudit(actor_id=current_user.user_id,user_id=revision.requester_id,action='MARK_CORRECTION_'+revision.status,
        details={'revision':revision.token,'context':context,'prn':revision.prn,'previous':revision.previous,'proposed':revision.proposed,'reason':revision.reason,'decision_note':note}))
    db.session.commit();return True
