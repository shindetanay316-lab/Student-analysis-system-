from datetime import datetime, timezone

from models import db


class ValidationIssue(db.Model):
    __tablename__ = "result_validation_issues"

    SEVERITY_ERROR = "ERROR"
    SEVERITY_WARNING = "WARNING"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("result_exam_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("result_report_students.id", ondelete="CASCADE"),
        index=True,
    )
    subject_result_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subject_results.id", ondelete="CASCADE"),
        index=True,
    )
    severity = db.Column(db.String(20), nullable=False, index=True)
    scope = db.Column(db.String(30), nullable=False)
    code = db.Column(db.String(80), nullable=False, index=True)
    field_name = db.Column(db.String(80))
    message = db.Column(db.Text, nullable=False)
    reported_value = db.Column(db.String(100))
    calculated_value = db.Column(db.String(100))
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    report = db.relationship("ExamReport", back_populates="validation_issues")
    student = db.relationship(
        "ReportStudent",
        back_populates="validation_issues",
        foreign_keys=[student_id],
    )
    subject_result = db.relationship(
        "SubjectResult",
        back_populates="validation_issues",
        foreign_keys=[subject_result_id],
    )
