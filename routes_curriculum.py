"""Admin-reviewed syllabus imports and immutable curriculum versions."""
from copy import deepcopy
from io import BytesIO
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from sqlalchemy.exc import IntegrityError, OperationalError
from flask_login import current_user
from models import db, Student
from curriculum_models import CurriculumVersion, CurriculumBinding, StudentCurriculumTerm
from workflow_models import WorkflowReview
import curriculum_enrollment as enrollment
from routes_teaching import admin_required
import curriculum_services as services

curriculum_bp = Blueprint('curriculum', __name__, url_prefix='/curriculum')


@curriculum_bp.before_request
def protect():
    if request.method == 'POST':
        from result_data import csrf
        csrf.protect()


@curriculum_bp.get('')
@admin_required
def index():
    return render_template('curriculum/index.html', versions=CurriculumVersion.query.order_by(CurriculumVersion.created_at.desc()).all(),
        bindings=CurriculumBinding.query.order_by(CurriculumBinding.academic_year.desc(), CurriculumBinding.semester_id).all())


@curriculum_bp.post('/upload')
@admin_required
def upload():
    try:
        version = services.create_version(request.files.get('syllabus'), request.form)
    except ValueError as error:
        flash(str(error), 'error')
        return redirect(url_for('curriculum.index'))
    return redirect(url_for('curriculum.detail', token=version.token))


@curriculum_bp.get('/<token>')
@admin_required
def detail(token):
    version = db.get_or_404(CurriculumVersion, token)
    errors = []
    if version.status == 'DRAFT':
        try:
            rows = services.validate_courses(deepcopy(version.courses), approval=True)
            errors = services.conflicts(rows)[0]
        except ValueError as error:
            errors = [str(error)]
    return render_template('curriculum/detail.html', version=version, errors=errors)


@curriculum_bp.get('/<token>/source')
@admin_required
def source(token):
    version = db.get_or_404(CurriculumVersion, token)
    return send_file(BytesIO(version.source_pdf), download_name=version.source_name, mimetype='application/pdf', as_attachment=True)


@curriculum_bp.post('/<token>/<action>')
@admin_required
def action(token, action):
    version = db.get_or_404(CurriculumVersion, token)
    try:
        revision = int(request.form.get('revision', 0))
        if action == 'save':
            services.save_draft(version, services.proposed_courses(version, request.form), revision)
            flash('Draft saved. Review all selected rows, then approve.', 'success')
        elif action == 'add':
            if version.status != 'DRAFT':
                raise ValueError('Create a revision to edit an approved syllabus.')
            rows = deepcopy(version.courses)
            rows.append(dict(row_id=max((r['row_id'] for r in rows), default=0) + 1,
                code='', name='', semester_id=1, group='COMMON', category='', subject_type='THEORY',
                credits='', l='', t='', p='', ca='', mse='', ese='', total='', choice_group='',
                include=False, is_audit=False, is_bucket=False, manual=True, evidence='', page=None,
                source_text='Manual entry; source reference required', issues=['Enter verified details and source/page evidence.']))
            services.save_draft(version, rows, revision)
        elif action == 'approve':
            if request.form.get('verified') != 'on':
                raise ValueError('Confirm that you checked the selected course rows against the source.')
            changed = services.approve(version, revision)
            flash('Curriculum approved; new subjects are available for assignments and rosters.' if changed else 'Already approved. No duplicate subjects created.', 'success')
        elif action == 'revise':
            if version.status != 'APPROVED':
                raise ValueError('Only an approved syllabus can start a new revision.')
            new = CurriculumVersion(title=version.title, branch=version.branch, scheme=version.scheme,
                effective_year=version.effective_year, owner_id=current_user.user_id,
                source_name=version.source_name, source_hash=version.source_hash, source_pdf=version.source_pdf,
                courses=deepcopy(version.courses), extracted=deepcopy(version.extracted),
                warnings=deepcopy(version.warnings), predecessor=version.token)
            db.session.add(new)
            db.session.commit()
            return redirect(url_for('curriculum.detail', token=new.token))
        elif action == 'bind':
            services.bind_version(version, request.form)
            flash('Approved curriculum bound to the selected regular cohort and teaching term.', 'success')
        else:
            abort(404)
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else 'Records changed concurrently. Reload and try again; no partial changes were saved.'
        flash(message, 'error')
        return redirect(url_for('curriculum.detail', token=token)), 303
    return redirect(url_for('curriculum.detail', token=token))


@curriculum_bp.get('/bindings/<int:binding_id>/roster')
@admin_required
def roster(binding_id):
    binding = db.get_or_404(CurriculumBinding, binding_id)
    q = request.args.get('q', '').strip()
    query = Student.query
    if q:
        query = query.filter(db.or_(Student.prn.ilike('%' + q + '%'), Student.name.ilike('%' + q + '%')))
    else:
        admissions = [binding.regular_cohort] + ([binding.regular_cohort + 1] if binding.semester_id >= 3 else [])
        query = query.filter(Student.year_of_admission.in_(admissions))
    rows = enrollment.courses(binding)
    groups = {}
    for row in rows:
        if row.get('choice_group') and not row.get('is_bucket'):
            groups.setdefault(row['choice_group'], []).append(row)
    return render_template('curriculum/roster.html', binding=binding, students=query.order_by(Student.prn).limit(1000).all(),
        courses=rows, groups=groups, search=q,
        linked=StudentCurriculumTerm.query.filter_by(binding_id=binding.id).count())


@curriculum_bp.post('/bindings/<int:binding_id>/preview')
@admin_required
def roster_preview(binding_id):
    binding = db.get_or_404(CurriculumBinding, binding_id)
    try:
        review = enrollment.preview(binding, request.form.getlist('prns'), request.form.getlist('options'))
    except ValueError as error:
        flash(str(error), 'error')
        return redirect(url_for('curriculum.roster', binding_id=binding.id))
    return redirect(url_for('curriculum.roster_review', token=review.token))


@curriculum_bp.get('/roster-reviews/<token>')
@admin_required
def roster_review(token):
    review = db.get_or_404(WorkflowReview, token)
    if review.kind != 'CURRICULUM_ROSTER':
        abort(404)
    binding = db.get_or_404(CurriculumBinding, review.context['binding_id'])
    return render_template('curriculum/roster_review.html', review=review, binding=binding)


@curriculum_bp.post('/roster-reviews/<token>/confirm')
@admin_required
def roster_confirm(token):
    review = db.get_or_404(WorkflowReview, token)
    if review.kind != 'CURRICULUM_ROSTER':
        abort(404)
    try:
        changed = enrollment.confirm(review)
    except (ValueError, IntegrityError, OperationalError) as error:
        db.session.rollback()
        message = str(error) if isinstance(error, ValueError) else 'Records changed concurrently. Create a fresh enrollment preview.'
        flash(message, 'error')
        return redirect(url_for('curriculum.roster_review', token=token)), 303
    flash('Curriculum enrollment confirmed.' if changed else 'Already confirmed. No duplicate enrollment created.', 'success')
    return redirect(url_for('curriculum.roster', binding_id=review.context['binding_id']))
