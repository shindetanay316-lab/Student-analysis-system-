"""Versioned syllabus evidence and explicit cohort-to-term curriculum bindings."""
from uuid import uuid4
from models import db
from workflow_models import now


class CurriculumVersion(db.Model):
    __tablename__ = 'curriculum_versions'
    token = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    title = db.Column(db.String(180), nullable=False)
    branch = db.Column(db.String(100), nullable=False)
    scheme = db.Column(db.String(30), nullable=False)
    effective_year = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='DRAFT')
    owner_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    approved_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    revision = db.Column(db.Integer, nullable=False, default=1)
    source_name = db.Column(db.String(255), nullable=False)
    source_hash = db.Column(db.String(64), nullable=False)
    source_pdf = db.Column(db.LargeBinary, nullable=False)
    extracted = db.Column(db.JSON, nullable=False)
    courses = db.Column(db.JSON, nullable=False)
    warnings = db.Column(db.JSON, nullable=False, default=list)
    predecessor = db.Column(db.String(36), db.ForeignKey('curriculum_versions.token'))


class CurriculumBinding(db.Model):
    __tablename__ = 'curriculum_bindings'
    __table_args__ = (db.UniqueConstraint('branch', 'regular_cohort', 'semester_id', 'academic_year', 'group_name', name='uq_curriculum_binding'),)
    id = db.Column(db.Integer, primary_key=True)
    version_token = db.Column(db.String(36), db.ForeignKey('curriculum_versions.token'), nullable=False)
    branch = db.Column(db.String(100), nullable=False)
    regular_cohort = db.Column(db.Integer, nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    group_name = db.Column(db.String(10), nullable=False, default='COMMON')
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    version = db.relationship('CurriculumVersion')


class StudentCurriculumTerm(db.Model):
    __tablename__ = 'student_curriculum_terms'
    __table_args__ = (db.UniqueConstraint('prn', 'semester_id', 'academic_year', name='uq_student_curriculum_term'),)
    id = db.Column(db.Integer, primary_key=True)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    binding_id = db.Column(db.Integer, db.ForeignKey('curriculum_bindings.id'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    binding = db.relationship('CurriculumBinding')
