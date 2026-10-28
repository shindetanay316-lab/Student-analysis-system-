"""Approved university evidence, separate from current coursework calculations."""
from uuid import uuid4
from models import db
from workflow_models import now


class UniversityPublication(db.Model):
    __tablename__ = 'university_publications'
    token = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'), unique=True, nullable=False)
    source_job_id = db.Column(db.Integer, nullable=False)  # Snapshot reference; survives deletion/re-extraction.
    source_hash = db.Column(db.String(64), nullable=False)
    dataset_hash = db.Column(db.String(64), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    examination_session = db.Column(db.String(80))
    examination_type = db.Column(db.String(50))
    metadata_snapshot = db.Column(db.JSON, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    approved_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    review = db.relationship('WorkflowReview')
    actor = db.relationship('User')


class UniversityLinkedResult(db.Model):
    __tablename__ = 'university_linked_results'
    id = db.Column(db.Integer, primary_key=True)
    publication_token = db.Column(db.String(36), db.ForeignKey('university_publications.token'), nullable=False, index=True)
    evidence_key = db.Column(db.String(64), unique=True, nullable=False)
    attempt_key = db.Column(db.String(64), nullable=False, index=True)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    subject_code = db.Column(db.String(20), db.ForeignKey('subjects.subject_code'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    source = db.Column(db.JSON, nullable=False)
    mapping_note = db.Column(db.String(1000))
    ese_copied = db.Column(db.Boolean, nullable=False, default=False)
    publication = db.relationship('UniversityPublication')


class StudentPortfolio(db.Model):
    __tablename__ = 'student_portfolios'
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), primary_key=True)
    details = db.Column(db.JSON, nullable=False, default=dict)
    revision = db.Column(db.Integer, nullable=False, default=1)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)
