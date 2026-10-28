"""Term records, configured marks, progression approval and department exports."""
import csv
import io
import json
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, OperationalError
from models import db, Student, Subject, Semester, Enrollment
from completion_models import StudentTerm, PendingAdmission, AssessmentPolicy, AssessmentScore, AssessmentScoreChange, ProgressionPolicy, ProgressionDecision
from workflow_models import WorkflowReview
from routes_teaching import admin_required
from teaching_access import require_assignment
import term_services as terms
import assessment_services as assessments
import progression_services as progression

completion_bp = Blueprint('completion',__name__,url_prefix='/records')


@completion_bp.before_request
def protect():
    if request.method=='POST':
        from result_data import csrf
        csrf.protect()


def selected_term(values):
    try:
        return terms.term(values)
    except ValueError as error:
        abort(400,str(error))


def all_terms():
    return Semester.query.order_by(Semester.academic_year.desc(),Semester.semester_id).all()


def fail(error,endpoint,**values):
    db.session.rollback()
    flash(str(error) if isinstance(error,ValueError) else 'Records changed concurrently. Reload and review again.','error')
    return redirect(url_for(endpoint,**values))


@completion_bp.get('/terms')
@admin_required
def term_records():
    c = selected_term(request.args) if request.args.get('semester_id') else None
    query = Student.query
    cohort = request.args.get('cohort',type=int)
    if cohort:
        query=query.filter_by(year_of_admission=cohort)
    search=request.args.get('q','').strip()
    if search:
        query=query.filter(db.or_(Student.prn.ilike('%'+search+'%'),Student.name.ilike('%'+search+'%')))
    students=query.order_by(Student.prn).limit(1000).all() if c else []
    students=terms.students_in_term(students,**c) if c else []
    return render_template('completion/terms.html',terms=all_terms(),c=c,students=students,cohort=cohort,search=search)


def csv_download(headers,rows,filename,metadata=None):
    def safe(value):
        text=str(value or '') if not isinstance(value,(int,float)) else value
        return '\t'+text if isinstance(text,str) and text.startswith(('=','+','-','@')) else text
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    if metadata:
        writer.writerow(['ACADPULSE configured assessment marks'])
        writer.writerows(metadata.items())
        writer.writerow([])
    writer.writerow(headers)
    writer.writerows([[safe(v) for v in row] for row in rows])
    return send_file(io.BytesIO(stream.getvalue().encode('utf-8-sig')),download_name=filename,as_attachment=True,mimetype='text/csv')


@completion_bp.get('/terms/template')
@admin_required
def term_template():
    c=selected_term(request.args)
    query=Student.query
    cohort=request.args.get('cohort',type=int)
    if cohort:
        query=query.filter_by(year_of_admission=cohort)
    students=terms.students_in_term(query.order_by(Student.prn).all(),**c)
    return csv_download(['Sr. No.','PRN','Student Name','Roll Number','Division','Practical Batch'],
        [[i,s.prn,s.name,s.roll_number,s.division,s.batch] for i,s in enumerate(students,1)],'Term_placements.csv')


@completion_bp.post('/terms/preview')
@admin_required
def term_preview():
    c=selected_term(request.form)
    try:
        file=request.files.get('placement_file')
        if file:
            content=file.read(5*1024*1024+1)
            if len(content)>5*1024*1024:
                raise ValueError('Placement CSV must be at most 5 MB.')
            reader=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
            if reader.fieldnames!=['Sr. No.','PRN','Student Name','Roll Number','Division','Practical Batch']:
                raise ValueError('Use the generated term-placement CSV template.')
            rows=[dict(prn=str(r['PRN'] or '').strip(),name=str(r['Student Name'] or '').strip(),roll_number=r['Roll Number'],division=r['Division'],batch=r['Practical Batch'])
                for r in reader if r.get('PRN')]
        else:
            rows=[]
            for prn in request.form.getlist('prns'):
                student=db.session.get(Student,prn)
                if not student:
                    raise ValueError('A selected student no longer exists.')
                rows.append(dict(prn=prn,name=student.name,roll_number=request.form.get('roll_'+prn,''),division=request.form.get('division_'+prn,''),batch=request.form.get('batch_'+prn,'')))
        review=terms.preview(c,rows)
    except (ValueError,UnicodeDecodeError,csv.Error,IntegrityError,OperationalError) as error:
        return fail(error,'completion.term_records',**c)
    return redirect(url_for('completion.review',token=review.token))


@completion_bp.get('/admissions')
@admin_required
def admissions():
    return render_template('completion/admissions.html',terms=all_terms(),admissions=PendingAdmission.query.order_by(PendingAdmission.created_at.desc()).limit(1000).all())


@completion_bp.post('/admissions')
@admin_required
def admission_create():
    try:
        terms.admission(request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.admissions')
    flash('Admission recorded. Activate the real PRN when it is available, then confirm the subject roster.','success')
    return redirect(url_for('completion.admissions'))


@completion_bp.post('/admissions/<token>/preview')
@admin_required
def admission_preview(token):
    try:
        review=terms.activation_preview(db.get_or_404(PendingAdmission,token),request.form.get('prn'))
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.admissions')
    return redirect(url_for('completion.review',token=review.token))


@completion_bp.post('/admissions/<token>/edit')
@admin_required
def admission_edit(token):
    try:
        terms.edit_admission(db.get_or_404(PendingAdmission,token),request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.admissions')
    return redirect(url_for('completion.admissions'))


@completion_bp.get('/assessments')
@login_required
def assessment_list():
    from student_history_services import allowed_contexts
    allowed=allowed_contexts()
    policies=AssessmentPolicy.query.order_by(AssessmentPolicy.academic_year.desc(),AssessmentPolicy.subject_code).all()
    if allowed is not None:
        policies=[p for p in policies if (p.subject_code,p.semester_id,p.academic_year) in allowed and p.status=='APPROVED']
    requests=WorkflowReview.query.filter_by(kind='CONFIGURED_MARKS',confirmed_at=None).order_by(WorkflowReview.created_at.desc()).all()
    requests=[r for r in requests if r.context.get('correction') and (current_user.role=='ADMIN' or r.owner_id==current_user.user_id)]
    return render_template('completion/assessments.html',policies=policies,requests=requests,terms=all_terms(),
        subjects=Subject.query.filter_by(is_active=True,is_audit=False,is_attendance_only=False).order_by(Subject.subject_name).all() if current_user.role=='ADMIN' else [],
        example=json.dumps(assessments.DEFAULT_RULES,indent=2))


@completion_bp.post('/assessments')
@admin_required
def assessment_create():
    try:
        policy=assessments.create_policy(request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.assessment_list')
    return redirect(url_for('completion.assessment_detail',token=policy.token))


def permitted_policy(token):
    policy=db.get_or_404(AssessmentPolicy,token)
    require_assignment(policy.subject_code,policy.semester_id,policy.academic_year)
    if current_user.role!='ADMIN' and policy.status!='APPROVED':
        abort(403)
    return policy


@completion_bp.get('/assessments/<token>')
@login_required
def assessment_detail(token):
    policy=permitted_policy(token)
    students=__import__('workflow_services').roster(assessments.vars_context(policy))
    scores={r.prn:r for r in AssessmentScore.query.filter_by(policy_token=policy.token)}
    rows=[dict(student=s,score=scores.get(s.prn),result=assessments.result_for(policy,s.prn)) for s in students]
    return render_template('completion/assessment.html',policy=policy,rows=rows,
        changes=AssessmentScoreChange.query.filter_by(policy_token=policy.token).order_by(AssessmentScoreChange.id.desc()).limit(100).all())


@completion_bp.post('/assessments/<token>/approve')
@admin_required
def assessment_approve(token):
    try:
        if request.form.get('verified')!='on':
            raise ValueError('Verify the source and assessment rules before approval.')
        assessments.approve(db.get_or_404(AssessmentPolicy,token),request.form.get('revision'))
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.assessment_detail',token=token)
    return redirect(url_for('completion.assessment_detail',token=token))


@completion_bp.post('/assessments/<token>/edit')
@admin_required
def assessment_edit(token):
    try:
        assessments.edit_draft(db.get_or_404(AssessmentPolicy,token),request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.assessment_detail',token=token)
    return redirect(url_for('completion.assessment_detail',token=token))


@completion_bp.get('/assessments/<token>/template')
@login_required
def assessment_template(token):
    policy=permitted_policy(token)
    if policy.status!='APPROVED':
        abort(400,'Approve the policy first.')
    students=__import__('workflow_services').roster(assessments.vars_context(policy))
    scores={r.prn:r for r in AssessmentScore.query.filter_by(policy_token=policy.token)}
    if request.args.get('format')!='csv':
        return send_file(assessments.template_workbook(policy,students,scores),download_name='Assessment_'+policy.subject_code+'.xlsx',
            as_attachment=True,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    codes=[c['code'] for c in policy.rules['components']]
    rows=[]
    for i,s in enumerate(students,1):
        values=scores[s.prn].values if s.prn in scores else {}
        rows.append([i,s.prn,s.name]+['AB' if values.get(code,{}).get('state')=='ABSENT' else values.get(code,{}).get('value') for code in codes])
    return csv_download(['Sr. No.','PRN','Student Name']+codes,rows,'Assessment_'+policy.subject_code+'.csv',assessments.template_metadata(policy))


@completion_bp.post('/assessments/<token>/preview')
@login_required
def assessment_preview(token):
    policy=permitted_policy(token)
    try:
        file=request.files.get('marks_file')
        if not file:
            raise ValueError('Choose the generated CSV with component marks.')
        review=assessments.preview(policy,file.read(5*1024*1024+1),request.form.get('reason'),file.filename or '')
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.assessment_detail',token=token)
    return redirect(url_for('completion.review',token=review.token))


@completion_bp.get('/progression')
@admin_required
def progression_page():
    student=db.session.get(Student,request.args.get('prn',''))
    policy=db.session.get(ProgressionPolicy,request.args.get('policy',''))
    rows=[]
    year=request.args.get('academic_year','')
    if student and policy and year:
        try:
            year=__import__('routes_teaching').normalize_academic_year(year)
            rows,_=progression.analyze(student,policy,year)
        except ValueError as error:
            flash(str(error),'error')
    return render_template('completion/progression.html',policies=ProgressionPolicy.query.order_by(ProgressionPolicy.approved_at.desc()).all(),
        student=student,policy=policy,rows=rows,year=year,terms=all_terms(),
        decisions=ProgressionDecision.query.order_by(ProgressionDecision.created_at.desc()).limit(100).all())


@completion_bp.post('/progression/policies')
@admin_required
def progression_policy_create():
    try:
        if request.form.get('verified')!='on':
            raise ValueError('Verify the institution’s progression rules before approving this policy.')
        progression.create_policy(request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.progression_page')
    return redirect(url_for('completion.progression_page'))


@completion_bp.post('/progression/preview')
@admin_required
def progression_preview():
    student=db.get_or_404(Student,request.form.get('prn'))
    policy=db.get_or_404(ProgressionPolicy,request.form.get('policy'))
    try:
        review=progression.preview(student,policy,request.form)
    except (ValueError,IntegrityError,OperationalError) as error:
        return fail(error,'completion.progression_page',prn=student.prn,policy=policy.token,academic_year=request.form.get('academic_year',''))
    return redirect(url_for('completion.review',token=review.token))


REVIEW_KINDS={'TERM_PLACEMENT','PRN_ACTIVATION','CONFIGURED_MARKS','PROGRESSION'}


def permitted_review(token):
    review=db.get_or_404(WorkflowReview,token)
    if review.kind not in REVIEW_KINDS:
        abort(404)
    if review.kind!='CONFIGURED_MARKS':
        if current_user.role!='ADMIN':
            abort(403)
    else:
        permitted_policy(review.context['policy_token'])
        if current_user.role!='ADMIN' and review.owner_id!=current_user.user_id:
            abort(403)
    return review


@completion_bp.get('/reviews/<token>')
@login_required
def review(token):
    return render_template('completion/review.html',review=permitted_review(token))


@completion_bp.get('/reviews/<token>/source')
@login_required
def review_source(token):
    item=permitted_review(token)
    if not item.source_workbook:
        abort(404)
    return send_file(io.BytesIO(item.source_workbook),as_attachment=True,download_name=item.source_name,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if (item.source_name or '').endswith('.xlsx') else 'text/csv')


@completion_bp.post('/reviews/<token>/confirm')
@login_required
def confirm(token):
    item=permitted_review(token)
    try:
        if not item.confirmed_at and request.form.get('verified')!='on':
            raise ValueError('Verify this preview before confirming.')
        service={'TERM_PLACEMENT':terms.confirm,'PRN_ACTIVATION':terms.activate,'CONFIGURED_MARKS':assessments.confirm,'PROGRESSION':progression.confirm}[item.kind]
        changed=service(item)
    except (ValueError,IntegrityError,OperationalError) as error:
        db.session.rollback()
        message=str(error) if isinstance(error,ValueError) else 'Records changed concurrently. No partial changes were saved. Create a fresh preview.'
        return render_template('completion/conflict.html',message=message),409
    flash('Approved and saved.' if changed else 'Already confirmed. No duplicate records were created.','success')
    return redirect(url_for('completion.review',token=token))


@completion_bp.get('/master')
@admin_required
def master_page():
    return render_template('completion/master.html',terms=all_terms())


@completion_bp.get('/master/excel')
@admin_required
def master_export():
    c=selected_term(request.args)
    from department_reports import build_master
    try:
        stream=build_master(c,request.args)
    except ValueError as error:
        abort(400,str(error))
    return send_file(stream,as_attachment=True,download_name=f"ACADPULSE_Master_S{c['semester_id']}_{c['academic_year']}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
