"""Compatibility URLs for reviewed, semester-specific placement changes."""
from flask import Blueprint, redirect, url_for, request, abort, flash
from flask_login import login_required, current_user
from models import db, Student

batches_bp=Blueprint('batches',__name__)


def administrator():
    if current_user.role!='ADMIN':
        flash('Only administrators can manage semester placements.','error')
        return redirect(url_for('index'))


@batches_bp.get('/batches')
@login_required
def batch_assignment_page():
    denied=administrator()
    if denied:
        return denied
    return redirect(url_for('completion.term_records'))


def preview_change(clear=False):
    denied=administrator()
    if denied:
        return denied
    from result_data import csrf
    csrf.protect()
    import term_services as terms
    try:
        c=terms.term(request.form)
        rows=[]
        for prn in request.form.getlist('student_prns'):
            student=db.session.get(Student,prn)
            if not student:
                raise ValueError('Unknown student PRN.')
            old=terms.placement(prn,**c)
            rows.append(dict(prn=prn,name=student.name,division='' if clear else request.form.get('division',''),
                batch='' if clear else request.form.get('batch',''),roll_number=None if clear else old.roll_number if old else None))
        review=terms.preview(c,rows)
    except ValueError as error:
        abort(400,str(error))
    return redirect(url_for('completion.review',token=review.token))


@batches_bp.post('/batches/save')
@login_required
def save_batch_assignment():
    return preview_change()


@batches_bp.post('/batches/clear')
@login_required
def clear_batch_assignment():
    return preview_change(clear=True)
