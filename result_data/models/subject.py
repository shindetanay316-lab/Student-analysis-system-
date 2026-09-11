from datetime import datetime, timezone

from models import db


class ResultSubject(db.Model):
    """A subject detected inside an uploaded university result report.

    This is deliberately separate from the curriculum ``Subject`` model used
    by the Student Analysis System.
    """

    __tablename__ = "result_subjects"
    __table_args__ = (
        db.UniqueConstraint(
            "report_id", "subject_code", name="uq_result_subject_report_code"
        ),
        db.UniqueConstraint(
            "report_id", "display_order", name="uq_result_subject_report_order"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("result_exam_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_code = db.Column(db.String(80), nullable=False)
    subject_name = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, nullable=False)
    credits = db.Column(db.Numeric(8, 2))
    is_audit = db.Column(db.Boolean, nullable=False, default=False)
    total_maximum = db.Column(db.Numeric(8, 2))
    total_minimum = db.Column(db.Numeric(8, 2))
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

    report = db.relationship("ExamReport", back_populates="subjects")
    assessments = db.relationship(
        "SubjectAssessment",
        back_populates="subject",
        cascade="all, delete-orphan",
        order_by="SubjectAssessment.display_order",
    )
    results = db.relationship(
        "SubjectResult", back_populates="subject", cascade="all, delete-orphan"
    )


class SubjectAssessment(db.Model):
    __tablename__ = "result_subject_assessments"
    __table_args__ = (
        db.UniqueConstraint(
            "subject_id",
            "component_type",
            name="uq_result_assessment_subject_component",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_type = db.Column(db.String(50), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    source_row = db.Column(db.String(50), nullable=False)
    maximum_marks = db.Column(db.Numeric(8, 2), nullable=False)
    minimum_marks = db.Column(db.Numeric(8, 2))
    display_order = db.Column(db.Integer, nullable=False)

    subject = db.relationship("ResultSubject", back_populates="assessments")
    values = db.relationship("ResultComponent", back_populates="assessment")


# Keep the source module's public service API while avoiding a SQLAlchemy
# class-name collision with the curriculum Subject model.
Subject = ResultSubject
