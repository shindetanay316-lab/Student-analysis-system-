"""Reviewed rosters, internal marks and analysis of the selected subject."""
from decimal import Decimal
from io import BytesIO
from flask import Blueprint,abort,flash,redirect,render_template,request,send_file,url_for
from flask_login import login_required,current_user
from sqlalchemy.exc import IntegrityError,OperationalError
from models import db,Subject,Student,Semester,TheoryMarks,LabMarks,ExternalMarks
from routes_teaching import admin_required,normalize_academic_year
from teaching_access import require_assignment
from workflow_models import WorkflowReview,AcceptedInternalMark
import workflow_services as services

workflow_bp=Blueprint('workflow',__name__,url_prefix='/workflow')


def get_context(values):
    values=dict(values)
    if not values.get('academic_year'):
        from academic_utils import get_academic_year_for_semester
        try:values['academic_year']=get_academic_year_for_semester(int(values.get('semester_id','')))
        except (ValueError,TypeError):pass
    try:return services.subject_context(values)
    except ValueError as error:abort(400,str(error))


def teacher_name(proposed=''):
    # A caller cannot impersonate another teacher by editing the URL/form.
    if current_user.role=='TEACHER':return current_user.username
    return proposed.strip() or current_user.username


@workflow_bp.before_request
def protect_writes():
    if request.method=='POST':
        from result_data import csrf
        csrf.protect()


@workflow_bp.get('/roster')
@admin_required
def roster_page():
    from academic_utils import get_academic_year_for_semester
    sem=request.args.get('semester_id',type=int)
    active=Semester.query.filter_by(is_active=True).first()
    sem=sem or (active.semester_id if active else 1)
    if sem not in range(1,9):abort(400)
    try:year=normalize_academic_year(request.args.get('academic_year') or get_academic_year_for_semester(sem))
    except ValueError as error:abort(400,str(error))
    subjects=Subject.query.filter_by(semester_id=sem,is_active=True).filter(db.or_(Subject.is_elective.is_(False),Subject.parent_subject_code.isnot(None))).order_by(Subject.subject_name).all()
    code=request.args.get('subject_code','')
    context=get_context({'subject_code':code,'semester_id':sem,'academic_year':year}) if code else None
    enrolled=services.roster(context) if context else []
    query=Student.query
    cohort=request.args.get('cohort',type=int)
    if cohort:query=query.filter_by(year_of_admission=cohort)
    search=request.args.get('q','').strip()
    if search:query=query.filter(db.or_(Student.prn.ilike('%'+search+'%'),Student.name.ilike('%'+search+'%')))
    from result_data.models import ImportJob
    sources=ImportJob.query.filter(ImportJob.confirmed_at.isnot(None),ImportJob.status.in_(['READY','EXPORTED'])).all()
    sources=[j for j in sources if j.report and str(j.report.semester)==str(sem)]
    return render_template('workflow/roster.html',context=context,academic_year=year,semester_id=sem,subjects=subjects,
        selected_code=code,enrolled=enrolled,students=query.order_by(Student.prn).limit(1000).all(),sources=sources,cohort=cohort,search=search)


@workflow_bp.get('/roster/template')
@admin_required
def roster_template():
    context=get_context(request.args)
    try:stream=services.roster_template(context,request.args.get('source_id',type=int))
    except ValueError as error:abort(400,str(error))
    return send_file(stream,download_name=f"Roster_{context['subject_code']}_{context['academic_year']}.xlsx",as_attachment=True,mimetype=services.XLSX)


@workflow_bp.post('/roster/preview')
@admin_required
def roster_preview():
    context=get_context(request.form)
    try:
        if request.files.get('roster_file'):
            rows=services.parse_roster(request.files['roster_file'],context)
        else:
            prns=request.form.getlist('student_prns')
            students=Student.query.filter(Student.prn.in_(prns)).order_by(Student.prn).all()
            if len(students)!=len(set(prns)):raise ValueError('One or more selected students no longer exist.')
            rows=[{'prn':s.prn,'name':s.name,'admission_year':s.year_of_admission,'division':s.division or '','batch':s.batch or ''} for s in students]
            services.validate_roster_rows(context,rows)
        review=services.new_review('ROSTER',context,rows,request.files.get('roster_file'))
    except ValueError as error:
        flash(str(error),'danger');return redirect(url_for('workflow.roster_page',**context))
    return redirect(url_for('workflow.review_page',token=review.token))


def preview_internal_upload():
    """Both the new UI and legacy upload URL stage rather than save marks."""
    context=get_context(request.form)
    require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    exam=request.form.get('exam_type','CT1').strip().upper()
    if exam not in services.COMPONENTS:abort(400,'Invalid internal assessment.')
    subject=db.session.get(Subject,context['subject_code'])
    if subject.subject_type!='THEORY' or subject.is_audit or subject.is_attendance_only:abort(400,'Select a theory subject for internal assessments.')
    context['exam_type']=exam
    try:
        rows=services.parse_marks(request.files.get('ct1_file'),context)
        review=services.new_review('MARKS',context,rows,request.files.get('ct1_file'))
    except ValueError as error:
        flash('Upload needs correction: '+str(error),'error')
        return redirect(url_for('ct1_page',**context))
    return redirect(url_for('workflow.review_page',token=review.token))


@workflow_bp.post('/marks/preview')
@login_required
def marks_preview():return preview_internal_upload()


def authorized_review(token):
    review=db.get_or_404(WorkflowReview,token)
    if review.owner_id!=current_user.user_id and current_user.role!='ADMIN':abort(403)
    if review.kind=='ROSTER' and current_user.role!='ADMIN':abort(403)
    context=review.context
    require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    return review


@workflow_bp.get('/reviews/<token>')
@login_required
def review_page(token):
    review=authorized_review(token)
    template='coursework/review.html' if review.kind in {'LAB_MARKS','EXTERNAL_MARKS'} else 'workflow/review.html'
    return render_template(template,review=review,subject=db.session.get(Subject,review.context['subject_code']))


@workflow_bp.get('/reviews/<token>/source')
@login_required
def review_source(token):
    review=authorized_review(token)
    if not review.source_workbook:abort(404)
    return send_file(BytesIO(review.source_workbook),download_name=review.source_name or 'source.xlsx',as_attachment=True,mimetype=services.XLSX)


@workflow_bp.post('/reviews/<token>/confirm')
@login_required
def confirm_review(token):
    review=authorized_review(token)
    try:changed=services.confirm(review)
    except (ValueError,IntegrityError,OperationalError) as error:
        db.session.rollback()
        message=str(error) if isinstance(error,ValueError) else 'Records changed concurrently. Refresh and create a fresh preview; no partial changes were saved.'
        return render_template('workflow/conflict.html',message=message,context=review.context,kind=review.kind),409
    flash('Saved and locked after confirmation.' if changed and review.kind!='ROSTER' else 'Roster confirmed.' if changed else 'This preview was already confirmed. No duplicate records were created.','success')
    return redirect(url_for('workflow.subject_analysis',**review.context))


@workflow_bp.get('/subject')
@login_required
def subject_analysis():
    context=get_context(request.args);require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    subject=db.session.get(Subject,context['subject_code']);students=services.roster(context)
    attendance_only=subject.is_audit or subject.is_attendance_only
    lab=subject.subject_type in {'LAB','PROJECT'}
    fields=[('ca1','CA1',30),('ca2','CA2',30),('external','External',40)] if lab else [('ct1','CT1',10),('ct2','CT2',10),('assignment','Assignment',10),('midsem','Mid-semester',20),('external','External ESE',60)]
    if attendance_only:fields=[]
    model=LabMarks if lab else TheoryMarks
    marks={m.prn:m for m in model.query.filter_by(**{k:context[k] for k in ('subject_code','semester_id','academic_year')})}
    from coursework_services import effective_states
    states=effective_states(context)
    external={r.prn:r for r in ExternalMarks.query.filter_by(**{k:context[k] for k in ('subject_code','semester_id','academic_year')})}
    accepted={}
    for (prn,category,component),state in states.items():
        if category=='INTERNAL':field=services.COMPONENTS[component][0]
        elif category=='LAB':field={'CA1':'ca1','CA2':'ca2','LAB_EXTERNAL':'external'}[component]
        else:field='external'
        accepted[(prn,field)]=state
    rows=[]
    for student in students:
        mark=marks.get(student.prn);values=[]
        for field,_,_ in fields:
            value=getattr(external.get(student.prn),'external_marks',None) if field=='external' and not lab else getattr(mark,field,None)
            values.append(value if value is not None else 'Absent' if accepted.get((student.prn,field))=='ABSENT' else 'Pending')
        rows.append({'student':student,'values':values,'complete':bool(values) and all(not isinstance(v,str) for v in values)})
    summaries=[]
    for index,(_,label,maximum) in enumerate(fields):
        numeric=[r['values'][index] for r in rows if not isinstance(r['values'][index],str)]
        summaries.append({'label':label,'maximum':maximum,'count':len(numeric),'average':round(sum(numeric)/len(numeric),2) if numeric else None})
    return render_template('workflow/subject.html',context=context,subject=subject,rows=rows,fields=fields,summaries=summaries,complete=sum(r['complete'] for r in rows),lab=lab,attendance_only=attendance_only)


def preserve_pending_internal(data,context):
    """Keep approved report geometry while distinguishing unsubmitted cells."""
    marks={r.prn:r for r in services.matching_marks(context)}
    from coursework_services import internal_states
    accepted=internal_states(context)
    for row in data:
        mark=marks.get(row['prn'])
        for field in ('ct1','ct2','assignment','midsem'):
            value=getattr(mark,field,None)
            if value is None:row['mse' if field=='midsem' else field]='Absent' if accepted.get((row['prn'],field))=='ABSENT' else 'Pending'
        if any(getattr(mark,field,None) is None for field in ('ct1','ct2','assignment')):
            for field in ('ca1','ca2','ca_total','best_ct','assignment_component','ca'):row[field]='Pending'
        if any(getattr(mark,field,None) is None for field in ('ct1','ct2','assignment','midsem')):row['internal']='Pending'
    return data
