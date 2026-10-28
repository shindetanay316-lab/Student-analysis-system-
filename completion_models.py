"""Additive term placement, assessment, and progression records."""
from uuid import uuid4
from models import db
from workflow_models import now


def token():
    return str(uuid4())


class StudentTerm(db.Model):
    __tablename__ = 'student_term_placements'
    __table_args__ = (
        db.UniqueConstraint('prn', 'semester_id', 'academic_year', name='uq_student_term_placement'),
        db.UniqueConstraint('semester_id', 'academic_year', 'division', 'roll_number', name='uq_term_division_roll'),
        db.ForeignKeyConstraint(['semester_id', 'academic_year'], ['semesters.semester_id', 'semesters.academic_year']),
    )
    id = db.Column(db.Integer, primary_key=True)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    roll_number = db.Column(db.String(20))
    division = db.Column(db.String(10))
    batch = db.Column(db.String(10))
    status = db.Column(db.String(20), nullable=False, default='ACTIVE')
    origin = db.Column(db.String(30), nullable=False, default='REVIEWED')
    revision = db.Column(db.Integer, nullable=False, default=1)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class PendingAdmission(db.Model):
    __tablename__ = 'pending_admissions'
    token = db.Column(db.String(36), primary_key=True, default=token)
    admission_number = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    admission_year = db.Column(db.Integer, nullable=False)
    placement = db.Column(db.JSON, nullable=False)
    activated_prn = db.Column(db.String(20), db.ForeignKey('students.prn'))
    revision = db.Column(db.Integer, nullable=False, default=1)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class AssessmentPolicy(db.Model):
    __tablename__ = 'assessment_policies'
    __table_args__ = (db.UniqueConstraint('subject_code', 'semester_id', 'academic_year', name='uq_assessment_policy_context'),)
    token = db.Column(db.String(36), primary_key=True, default=token)
    subject_code = db.Column(db.String(20), db.ForeignKey('subjects.subject_code'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    rules = db.Column(db.JSON, nullable=False)
    source_reference = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), default='DRAFT', nullable=False)
    revision = db.Column(db.Integer, default=1, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    approved_at = db.Column(db.DateTime(timezone=True))


class AssessmentScore(db.Model):
    __tablename__ = 'configured_assessment_scores'
    __table_args__ = (db.UniqueConstraint('policy_token', 'prn', name='uq_configured_score'),)
    id = db.Column(db.Integer, primary_key=True)
    policy_token = db.Column(db.String(36), db.ForeignKey('assessment_policies.token'), nullable=False)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    values = db.Column(db.JSON, nullable=False)
    revision = db.Column(db.Integer, default=1, nullable=False)
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class AssessmentScoreChange(db.Model):
    __tablename__ = 'configured_score_changes'
    id = db.Column(db.Integer, primary_key=True)
    policy_token = db.Column(db.String(36), db.ForeignKey('assessment_policies.token'), nullable=False)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    previous = db.Column(db.JSON)
    approved = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(1000), nullable=False)
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class ProgressionPolicy(db.Model):
    __tablename__ = 'progression_policies'
    token = db.Column(db.String(36), primary_key=True, default=token)
    title = db.Column(db.String(180), nullable=False)
    from_semester = db.Column(db.Integer, nullable=False)
    reviewed_semesters = db.Column(db.JSON, nullable=False)
    maximum_backlog_subjects = db.Column(db.Integer, nullable=False)
    maximum_backlog_credits = db.Column(db.Integer, nullable=False)
    minimum_earned_percent = db.Column(db.Numeric(5, 2), nullable=False)
    source_reference = db.Column(db.String(1000), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    approved_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class CourseOutcomeSelection(db.Model):
    __tablename__ = 'course_outcome_selections'
    __table_args__ = (db.UniqueConstraint('prn', 'subject_code', 'semester_id', name='uq_course_outcome_selection'),)
    id = db.Column(db.Integer, primary_key=True)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    subject_code = db.Column(db.String(20), db.ForeignKey('subjects.subject_code'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    source_key = db.Column(db.String(100), nullable=False)
    evidence = db.Column(db.JSON, nullable=False)
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'), nullable=False)
    revision = db.Column(db.Integer, default=1, nullable=False)
    approved_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class ProgressionDecision(db.Model):
    __tablename__ = 'progression_decisions'
    __table_args__ = (db.UniqueConstraint('prn', 'semester_id', 'academic_year', 'revision', name='uq_progression_revision'),)
    token = db.Column(db.String(36), primary_key=True, default=token)
    prn = db.Column(db.String(20), db.ForeignKey('students.prn'), nullable=False)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    target_year = db.Column(db.String(10))
    decision = db.Column(db.String(20), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    policy_token = db.Column(db.String(36), db.ForeignKey('progression_policies.token'), nullable=False)
    outcomes = db.Column(db.JSON, nullable=False)
    summary = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(1000), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
