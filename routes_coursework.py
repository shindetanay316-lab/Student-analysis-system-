"""Reviewed lab/external uploads and the local marks correction queue."""
from flask import Blueprint,request,abort,flash,redirect,url_for,render_template,jsonify
from flask_login import login_required,current_user
from sqlalchemy.exc import IntegrityError,OperationalError
from models import db,Subject,Student
from routes_teaching import admin_required
from routes_workflow import get_context
from teaching_access import require_assignment
from workflow_models import WorkflowReview
from coursework_models import MarkRevision
import coursework_services as service
import workflow_services as core

coursework_bp=Blueprint('coursework',__name__,url_prefix='/coursework')


@coursework_bp.before_request
def csrf():
    if request.method=='POST':
        from result_data import csrf as protection
        protection.protect()


def preview_upload(category):
    context=get_context(request.form);require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    field='lab_file' if category=='LAB' else 'file'
    endpoint='lab.lab_marks_page' if category=='LAB' else 'external.external_marks_page'
    try:
        rows=service.parse_upload(request.files.get(field),context,category)
        review=core.new_review(service.KINDS[category],context,rows,request.files.get(field))
    except ValueError as error:
        flash('Upload needs correction: '+str(error),'error');return redirect(url_for(endpoint,**context))
    return redirect(url_for('workflow.review_page',token=review.token))


@coursework_bp.post('/lab/preview')
@login_required
def preview_lab():return preview_upload('LAB')


@coursework_bp.post('/external/preview')
@login_required
def preview_external():return preview_upload('EXTERNAL')


def preview_external_json():
    data=request.get_json(silent=True) or {};context=get_context(data)
    require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    try:
        service.validate_category(context,'EXTERNAL')
        students={s.prn:s for s in core.roster(context)};values=data.get('marks')
        if not isinstance(values,list) or not values:raise ValueError('Provide a nonempty list of student marks for review.')
        rows=[];seen=set()
        for item in values:
            if not isinstance(item,dict):raise ValueError('Invalid marks row.')
            prn=item.get('prn',item.get('student_id'))
            if not isinstance(prn,str):raise ValueError('PRN must be provided as text.')
            prn=prn.strip()
            if prn not in students or prn in seen:raise ValueError('Unknown, duplicate or unenrolled PRN in this context.')
            seen.add(prn)
            rows.append({'prn':prn,'name':students[prn].name,'values':{'EXTERNAL':service.value_state(item.get('external_marks'),'EXTERNAL','EXTERNAL')}})
        service.ensure_unlocked(context,'EXTERNAL',rows)
        review=core.new_review('EXTERNAL_MARKS',context,rows)
    except ValueError as error:return jsonify(success=False,saved=0,errors=[str(error)]),400
    return jsonify(success=True,saved=0,requires_confirmation=True,review_url=url_for('workflow.review_page',token=review.token))


@coursework_bp.route('/corrections/new',methods=['GET','POST'])
@login_required
def request_correction():
    context=get_context(request.form if request.method=='POST' else request.args)
    require_assignment(context['subject_code'],context['semester_id'],context['academic_year'])
    subject=db.session.get(Subject,context['subject_code'])
    if request.method=='POST':
        try:
            revision=service.propose(context,request.form.get('prn',''),request.form.get('category',''),request.form.get('component',''),request.form.get('new_value'),request.form.get('reason',''))
        except ValueError as error:
            flash(str(error),'danger');return redirect(url_for('coursework.request_correction',**context))
        flash('Correction requested. Current marks remain unchanged until administrator approval.','success')
        return redirect(url_for('coursework.correction_detail',token=revision.token))
    categories={'LAB':service.SPECS['LAB']} if subject.subject_type in {'LAB','PROJECT'} else {'INTERNAL':service.SPECS['INTERNAL'],'EXTERNAL':service.SPECS['EXTERNAL']}
    return render_template('coursework/request.html',context=context,subject=subject,students=core.roster(context),categories=categories)


@coursework_bp.get('/corrections')
@login_required
def corrections():
    query=MarkRevision.query
    if current_user.role!='ADMIN':query=query.filter_by(requester_id=current_user.user_id)
    rows=query.order_by(MarkRevision.created_at.desc()).limit(200).all()
    return render_template('coursework/corrections.html',revisions=rows)


@coursework_bp.get('/corrections/<token>')
@login_required
def correction_detail(token):
    revision=db.get_or_404(MarkRevision,token)
    if current_user.role!='ADMIN':
        if revision.requester_id!=current_user.user_id:abort(403)
        require_assignment(revision.context['subject_code'],revision.context['semester_id'],revision.context['academic_year'])
    from workflow_models import AcceptedInternalMark
    from coursework_models import AcceptedCourseworkMark
    model=AcceptedInternalMark if revision.category=='INTERNAL' else AcceptedCourseworkMark
    query=model.query.filter_by(prn=revision.prn,component=revision.component,**service.keys(revision.context))
    if revision.category!='INTERNAL':query=query.filter_by(category=revision.category)
    accepted=query.first()
    source=db.session.get(WorkflowReview,accepted.review_token) if accepted else None
    if source and current_user.role!='ADMIN' and source.owner_id!=current_user.user_id:source=None
    return render_template('coursework/detail.html',revision=revision,subject=db.session.get(Subject,revision.context['subject_code']),student=db.session.get(Student,revision.prn),source=source)


@coursework_bp.post('/corrections/<token>/decide')
@admin_required
def decide_correction(token):
    revision=db.get_or_404(MarkRevision,token)
    decision=request.form.get('decision')
    if decision not in {'APPROVE','REJECT'}:abort(400,'Choose approve or reject.')
    try:changed=service.decide(revision,decision=='APPROVE',request.form.get('decision_note',''))
    except (ValueError,IntegrityError,OperationalError) as error:
        db.session.rollback();message=str(error) if isinstance(error,ValueError) else 'Records changed concurrently. Refresh before deciding; no partial correction was saved.'
        return render_template('workflow/conflict.html',message=message,context=revision.context,kind='CORRECTION'),409
    flash('Correction decision saved.' if changed else 'This request was already decided; no duplicate changes were made.','success')
    return redirect(url_for('coursework.correction_detail',token=revision.token))
