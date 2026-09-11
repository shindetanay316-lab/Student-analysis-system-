from datetime import datetime, timezone

from models import db


class SubjectResult(db.Model):
    __tablename__ = "result_subject_results"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "subject_id", name="uq_result_data_student_subject"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("result_report_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_page = db.Column(db.Integer, nullable=False)
    total_raw = db.Column(db.String(50))
    total_value = db.Column(db.Numeric(8, 2))
    total_is_carried_forward = db.Column(db.Boolean, nullable=False, default=False)
    total_special_code = db.Column(db.String(30))
    grade_raw = db.Column(db.String(80))
    grade = db.Column(db.String(20))
    grade_point = db.Column(db.Numeric(8, 2))
    credit_points = db.Column(db.Numeric(8, 2))
    grace_marks = db.Column(db.Numeric(8, 2))
    audit_grade = db.Column(db.String(30))
    attempt_session = db.Column(db.String(80))
    component_sum = db.Column(db.Numeric(8, 2))
    expected_grade = db.Column(db.String(20))
    expected_grade_point = db.Column(db.Numeric(8, 2))
    expected_credit_points = db.Column(db.Numeric(8, 2))
    validation_status = db.Column(
        db.String(30), nullable=False, default="NOT_VALIDATED", server_default="NOT_VALIDATED"
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student = db.relationship("ReportStudent", back_populates="subject_results")
    subject = db.relationship("ResultSubject", back_populates="results")
    components = db.relationship(
        "ResultComponent",
        back_populates="subject_result",
        cascade="all, delete-orphan",
        order_by="ResultComponent.id",
    )
    validation_issues = db.relationship(
        "ValidationIssue",
        back_populates="subject_result",
        foreign_keys="ValidationIssue.subject_result_id",
    )


class ResultComponent(db.Model):
    __tablename__ = "result_result_components"
    __table_args__ = (
        db.UniqueConstraint(
            "subject_result_id",
            "component_type",
            name="uq_result_component_result_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    subject_result_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subject_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subject_assessments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    component_type = db.Column(db.String(50), nullable=False)
    raw_text = db.Column(db.String(50), nullable=False)
    numeric_value = db.Column(db.Numeric(8, 2))
    is_carried_forward = db.Column(db.Boolean, nullable=False, default=False)
    special_code = db.Column(db.String(30))

    subject_result = db.relationship("SubjectResult", back_populates="components")
    assessment = db.relationship("SubjectAssessment", back_populates="values")
