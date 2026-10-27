"""Administrator staff management and the teacher's assigned-subject workspace."""
import re
from datetime import date
from functools import wraps
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from models import db, User, Subject, Semester, Enrollment, Student
from sqlalchemy import func
from teaching_models import TeachingAssignment, StaffAccessState, StaffAccessAudit
from teaching_access import record_login

teaching_bp=Blueprint('teaching',__name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def checked(*args,**kwargs):
        if current_user.role!='ADMIN':abort(403)
        return view(*args,**kwargs)
    return checked


def audit(user,action,details):
    db.session.add(StaffAccessAudit(actor_id=current_user.user_id,user_id=user.user_id,action=action,details=details))


def access_state(user):
    state=db.session.get(StaffAccessState,user.user_id)
    if state is None:
        state=StaffAccessState(user_id=user.user_id,credential_version=0,must_change_password=False)
        db.session.add(state)
    return state


def teacher_or_404(user_id):
    user=db.get_or_404(User,user_id)
    if user.role!='TEACHER':abort(400,'Select a teacher account.')
    return user


def normalize_academic_year(value):
    """One canonical label, without tying academic years to admission cohorts."""
    match=re.fullmatch(r'(\d{4})\s*[-–/]\s*(\d{2}|\d{4})',str(value or '').strip())
    if not match:raise ValueError('Enter an academic year such as 2026-27 or 2026-2027.')
    start=int(match[1]);end=int(match[2])
    if not 1900<=start<=2199 or (end!=start+1 if len(match[2])==4 else end!=(start+1)%100):
        raise ValueError('The academic year must contain consecutive years, for example 2026-27.')
    return f'{start}-{(start+1)%100:02}'


def assignment_page_url(year,semester_id):
    return url_for('teaching.teachers',academic_year=year,semester_id=semester_id)+'#assign-subject'


@teaching_bp.get('/my-subjects')
@login_required
def my_subjects():
    query=TeachingAssignment.query.join(Subject).join(User).filter(
        TeachingAssignment.is_active.is_(True),Subject.is_active.is_(True),User.is_active.is_(True))
    if current_user.role!='ADMIN':query=query.filter(TeachingAssignment.teacher_id==current_user.user_id)
    year=request.args.get('academic_year','').strip()
    if year:query=query.filter(TeachingAssignment.academic_year==year)
    assignments=query.order_by(TeachingAssignment.academic_year.desc(),TeachingAssignment.semester_id,Subject.subject_name).all()
    cards=[]
    for assignment in assignments:
        subject=assignment.subject
        context={'subject_code':assignment.subject_code,'semester_id':assignment.semester_id,'academic_year':assignment.academic_year}
        if subject.subject_type=='THEORY':context['exam_type']='CT1'
        cards.append({'assignment':assignment,'subject':subject,'count':Enrollment.query.filter_by(
            subject_code=assignment.subject_code,semester_id=assignment.semester_id,academic_year=assignment.academic_year).count(),
            'context':context,
            'marks_endpoint':None if subject.is_audit or subject.is_attendance_only else
                'lab.lab_marks_page' if subject.subject_type in {'LAB','PROJECT'} else 'ct1_page'})
    return render_template('teaching/my_subjects.html',cards=cards,selected_year=year)


@teaching_bp.get('/teachers')
@admin_required
def teachers():
    from academic_utils import get_academic_year_for_semester
    semester_id=request.args.get('semester_id',type=int)
    active=Semester.query.filter_by(is_active=True).first()
    if semester_id is None:semester_id=active.semester_id if active else 1
    if semester_id not in range(1,9):abort(400,'Select semester 1 to 8.')
    raw=request.args.get('academic_year') or get_academic_year_for_semester(semester_id)
    try:year=normalize_academic_year(raw)
    except ValueError as error:abort(400,str(error))
    subjects=Subject.query.filter(Subject.is_active.is_(True),Subject.semester_id==semester_id,
        db.or_(Subject.is_elective.is_(False),Subject.parent_subject_code.isnot(None))).order_by(Subject.subject_name,Subject.subject_code).all()
    years={term.academic_year for term in Semester.query.all()}
    for start in range(date.today().year-4,date.today().year+2):years.add(f'{start}-{(start+1)%100:02}')
    years.add(year)
    groups={subject.subject_code:[] for subject in subjects}
    rows=db.session.query(Enrollment.subject_code,Student.year_of_admission,Student.division,Student.batch,func.count()).join(
        Student,Student.prn==Enrollment.prn).filter(Enrollment.semester_id==semester_id,Enrollment.academic_year==year).group_by(
        Enrollment.subject_code,Student.year_of_admission,Student.division,Student.batch).order_by(
        Student.year_of_admission,Student.division,Student.batch).all()
    for code,cohort,division,batch,count in rows:
        if code in groups:groups[code].append({'cohort':cohort,'division':division or 'Not assigned','batch':batch or 'Not assigned','count':count})
    return render_template('teaching/teachers.html',teachers=User.query.filter_by(role='TEACHER').order_by(User.username).all(),
        subjects=subjects,academic_year=year,semester_id=semester_id,academic_years=sorted(years,reverse=True),roster_groups=groups,
        assignments=TeachingAssignment.query.order_by(TeachingAssignment.academic_year.desc(),TeachingAssignment.id.desc()).all(),
        events=StaffAccessAudit.query.order_by(StaffAccessAudit.id.desc()).limit(30).all())


@teaching_bp.post('/teachers/create')
@admin_required
def create_teacher():
    username=request.form.get('username','').strip()
    password=request.form.get('password','')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,50}',username):abort(400,'Username must contain 3–50 letters, digits, dots, @, underscores or hyphens.')
    if len(password)<10:abort(400,'Use a temporary password of at least 10 characters.')
    if User.query.filter_by(username=username).first():abort(400,'That username already exists.')
    user=User(username=username,role='TEACHER',is_active=True)
    user.set_password(password);db.session.add(user);db.session.flush()
    access_state(user).must_change_password=True
    audit(user,'TEACHER_CREATED',{'username':username})
    try:db.session.commit()
    except IntegrityError:
        db.session.rollback();abort(409,'That username was just created. Refresh the page.')
    flash('Teacher created. Share the temporary password directly; the teacher must change it on first login.','success')
    return redirect(url_for('teaching.teachers'))


@teaching_bp.post('/teachers/<int:user_id>/status')
@admin_required
def teacher_status(user_id):
    user=teacher_or_404(user_id)
    active=request.form.get('active')=='1'
    if user.is_active!=active:
        user.is_active=active;access_state(user).credential_version+=1
        audit(user,'TEACHER_ACTIVATED' if active else 'TEACHER_DEACTIVATED',{})
        db.session.commit()
    flash('Account updated. Existing sessions have been invalidated.','success')
    return redirect(url_for('teaching.teachers'))


@teaching_bp.post('/teachers/<int:user_id>/password')
@admin_required
def reset_password(user_id):
    user=teacher_or_404(user_id);password=request.form.get('password','')
    if len(password)<10:abort(400,'Use a temporary password of at least 10 characters.')
    user.set_password(password);state=access_state(user)
    state.credential_version+=1;state.must_change_password=True
    audit(user,'PASSWORD_RESET',{})
    db.session.commit()
    flash('Temporary password set. Existing sessions have been invalidated.','success')
    return redirect(url_for('teaching.teachers'))


@teaching_bp.post('/teachers/assign')
@admin_required
def assign_subject():
    try:teacher_id=int(request.form.get('teacher_id',''));semester_id=int(request.form.get('semester_id',''))
    except (ValueError,TypeError):abort(400,'Select a teacher and semester.')
    user=teacher_or_404(teacher_id)
    try:year=normalize_academic_year(request.form.get('academic_year',''))
    except ValueError as error:abort(400,str(error))
    code=request.form.get('subject_code','').strip()
    subject=db.session.get(Subject,code)
    if not user.is_active:abort(400,'Activate the teacher before assigning subjects.')
    if not subject or not subject.is_active or (subject.is_elective and not subject.parent_subject_code):abort(400,'Select an active subject or actual elective option.')
    if semester_id not in range(1,9) or subject.semester_id!=semester_id:abort(400,'Subject and semester do not match. Load the subjects for the selected semester first.')
    assignment=TeachingAssignment.query.filter_by(teacher_id=teacher_id,subject_code=code,semester_id=semester_id,academic_year=year).first()
    if assignment is None:
        assignment=TeachingAssignment(teacher_id=teacher_id,subject_code=code,semester_id=semester_id,academic_year=year)
        db.session.add(assignment)
    elif assignment.is_active:
        flash('That assignment already exists.','info');return redirect(assignment_page_url(year,semester_id))
    else:assignment.is_active=True
    if db.session.get(Semester,(semester_id,year)) is None:
        db.session.add(Semester(semester_id=semester_id,academic_year=year,is_active=False))
        audit(user,'ACADEMIC_TERM_CREATED',{'semester_id':semester_id,'academic_year':year})
    audit(user,'SUBJECT_ASSIGNED',{'subject_code':code,'semester_id':semester_id,'academic_year':year})
    try:db.session.commit()
    except IntegrityError:
        db.session.rollback();abort(409,'Assignment changed concurrently. Refresh the page.')
    flash('Subject assigned for the selected academic year and semester.','success')
    return redirect(assignment_page_url(year,semester_id))


@teaching_bp.post('/teachers/assignments/<int:assignment_id>/revoke')
@admin_required
def revoke_assignment(assignment_id):
    assignment=db.get_or_404(TeachingAssignment,assignment_id)
    if assignment.is_active:
        assignment.is_active=False
        audit(assignment.teacher,'SUBJECT_REVOKED',{'subject_code':assignment.subject_code,
            'semester_id':assignment.semester_id,'academic_year':assignment.academic_year})
        db.session.commit()
    flash('Assignment revoked. Existing academic records were preserved.','success')
    return redirect(url_for('teaching.teachers'))


@teaching_bp.route('/profile/password',methods=['GET','POST'])
@login_required
def password():
    if request.method=='POST':
        value=request.form.get('new_password','')
        if not current_user.check_password(request.form.get('current_password','')):abort(400,'Current password is incorrect.')
        if len(value)<10 or value!=request.form.get('confirm_password'):abort(400,'New passwords must match and contain at least 10 characters.')
        if current_user.check_password(value):abort(400,'Choose a different password.')
        current_user.set_password(value);state=access_state(current_user)
        state.credential_version+=1;state.must_change_password=False
        audit(current_user,'PASSWORD_CHANGED',{})
        db.session.commit();record_login(current_user)
        flash('Password changed.','success')
        return redirect(url_for('index'))
    state=db.session.get(StaffAccessState,current_user.user_id)
    return render_template('teaching/password.html',required=state.must_change_password if state else False)
