"""Immutable lab/ESE acceptances and reasoned administrator decisions."""
from uuid import uuid4
from workflow_models import now
from models import db


class AcceptedCourseworkMark(db.Model):
    __tablename__='accepted_coursework_marks'
    __table_args__=(db.UniqueConstraint('prn','subject_code','semester_id','academic_year','category','component',name='uq_accepted_coursework_component'),)
    id=db.Column(db.Integer,primary_key=True)
    prn=db.Column(db.String(20),db.ForeignKey('students.prn'),nullable=False)
    subject_code=db.Column(db.String(20),db.ForeignKey('subjects.subject_code'),nullable=False)
    semester_id=db.Column(db.Integer,nullable=False)
    academic_year=db.Column(db.String(10),nullable=False)
    category=db.Column(db.String(20),nullable=False)
    component=db.Column(db.String(20),nullable=False)
    value=db.Column(db.Numeric(5,2))
    state=db.Column(db.String(20),nullable=False)
    review_token=db.Column(db.String(36),db.ForeignKey('workflow_reviews.token'),nullable=False)
    actor_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False)
    accepted_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)


class MarkRevision(db.Model):
    __tablename__='mark_revisions'
    token=db.Column(db.String(36),primary_key=True,default=lambda:str(uuid4()))
    requester_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False)
    approver_id=db.Column(db.Integer,db.ForeignKey('users.user_id'))
    prn=db.Column(db.String(20),db.ForeignKey('students.prn'),nullable=False)
    context=db.Column(db.JSON,nullable=False)
    category=db.Column(db.String(20),nullable=False)
    component=db.Column(db.String(20),nullable=False)
    previous=db.Column(db.JSON,nullable=False)
    proposed=db.Column(db.JSON,nullable=False)
    reason=db.Column(db.String(1500),nullable=False)
    decision_note=db.Column(db.String(1500))
    snapshot=db.Column(db.String(64),nullable=False)
    status=db.Column(db.String(20),default='PENDING',nullable=False,index=True)
    claimed=db.Column(db.Boolean,default=False,nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    decided_at=db.Column(db.DateTime(timezone=True))
    requester=db.relationship('User',foreign_keys=[requester_id])
    approver=db.relationship('User',foreign_keys=[approver_id])
    student=db.relationship('Student')
