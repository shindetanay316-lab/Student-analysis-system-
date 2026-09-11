from datetime import datetime, timezone

from models import db


class ReportStudent(db.Model):
    __tablename__ = "result_report_students"
    __table_args__ = (
        db.UniqueConstraint(
            "report_id", "seat_number", name="uq_result_student_report_seat"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("result_exam_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_number = db.Column(db.String(30), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    gender_marker = db.Column(db.String(10))
    center_code = db.Column(db.String(30))
    registration_scope = db.Column(db.String(30))
    institute_code = db.Column(db.String(30))
    institute_name = db.Column(db.String(255))
    source_page = db.Column(db.Integer, nullable=False)
    result_status = db.Column(db.String(30), nullable=False, index=True)
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

    report = db.relationship("ExamReport", back_populates="students")
    subject_results = db.relationship(
        "SubjectResult",
        back_populates="student",
        cascade="all, delete-orphan",
        order_by="SubjectResult.id",
    )
    summary = db.relationship(
        "StudentSummary",
        back_populates="student",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    validation_issues = db.relationship(
        "ValidationIssue", back_populates="student", foreign_keys="ValidationIssue.student_id"
    )
    corrections = db.relationship(
        "DataCorrection",
        back_populates="student",
        foreign_keys="DataCorrection.student_id",
        order_by="DataCorrection.created_at.desc()",
    )
