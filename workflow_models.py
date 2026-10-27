"""Server-held previews and immutable evidence of confirmed coursework."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from models import db


def now():return datetime.now(timezone.utc)


class WorkflowReview(db.Model):
    __tablename__='workflow_reviews'
    token=db.Column(db.String(36),primary_key=True,default=lambda:str(uuid4()))
    owner_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False,index=True)
    kind=db.Column(db.String(20),nullable=False)
    context=db.Column(db.JSON,nullable=False)
    rows=db.Column(db.JSON,nullable=False)
    snapshot=db.Column(db.String(64),nullable=False)
    source_name=db.Column(db.String(255))
    source_hash=db.Column(db.String(64))
    source_workbook=db.Column(db.LargeBinary)
    created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
    expires_at=db.Column(db.DateTime(timezone=True),default=lambda:now()+timedelta(hours=2),nullable=False)
    confirmed_at=db.Column(db.DateTime(timezone=True))
    claimed=db.Column(db.Boolean,default=False,nullable=False)


class AcceptedInternalMark(db.Model):
    __tablename__='accepted_internal_marks'
    __table_args__=(db.UniqueConstraint('prn','subject_code','semester_id','academic_year','component',name='uq_accepted_internal_component'),)
    id=db.Column(db.Integer,primary_key=True)
    prn=db.Column(db.String(20),db.ForeignKey('students.prn'),nullable=False)
    subject_code=db.Column(db.String(20),db.ForeignKey('subjects.subject_code'),nullable=False)
    semester_id=db.Column(db.Integer,nullable=False)
    academic_year=db.Column(db.String(10),nullable=False)
    component=db.Column(db.String(20),nullable=False)
    value=db.Column(db.Numeric(5,2))
    state=db.Column(db.String(20),nullable=False)
    review_token=db.Column(db.String(36),db.ForeignKey('workflow_reviews.token'),nullable=False)
    actor_id=db.Column(db.Integer,db.ForeignKey('users.user_id'),nullable=False)
    accepted_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
