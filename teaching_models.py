"""Additive staff-access records; existing students and marks are untouched."""
from datetime import datetime, timezone
from models import db


def now():
    return datetime.now(timezone.utc)


class TeachingAssignment(db.Model):
    __tablename__='teaching_assignments'
    __table_args__=(db.UniqueConstraint('teacher_id','subject_code','semester_id','academic_year',name='uq_teaching_context'),)
    id=db.Column(db.Integer,primary_key=True)
    teacher_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False,index=True)
    subject_code=db.Column(db.String(20),db.ForeignKey('subjects.subject_code'),nullable=False)
    semester_id=db.Column(db.Integer,nullable=False)
    academic_year=db.Column(db.String(10),nullable=False)
    is_active=db.Column(db.Boolean,nullable=False,default=True)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    updated_at=db.Column(db.DateTime(timezone=True),default=now,onupdate=now,nullable=False)
    teacher=db.relationship('User')
    subject=db.relationship('Subject')


class StaffAccessState(db.Model):
    __tablename__='staff_access_states'
    user_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),primary_key=True)
    credential_version=db.Column(db.Integer,default=0,nullable=False)
    must_change_password=db.Column(db.Boolean,default=False,nullable=False)


class StaffAccessAudit(db.Model):
    __tablename__='staff_access_audit'
    id=db.Column(db.Integer,primary_key=True)
    actor_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False)
    action=db.Column(db.String(50),nullable=False)
    details=db.Column(db.JSON,nullable=False,default=dict)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
