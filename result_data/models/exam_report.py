from datetime import datetime, timezone

from models import db


class ExamReport(db.Model):
    __tablename__ = "result_exam_reports"

    id = db.Column(db.Integer, primary_key=True)
    import_job_id = db.Column(
        db.Integer,
        db.ForeignKey("result_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    parser_name = db.Column(db.String(100), nullable=False)
    parser_version = db.Column(db.String(50), nullable=False)
    university = db.Column(db.String(255), nullable=False)
    examination_title = db.Column(db.Text, nullable=False)
    programme = db.Column(db.String(255), nullable=False)
    branch = db.Column(db.String(255))
    semester = db.Column(db.String(30))
    examination_session = db.Column(db.String(80))
    examination_type = db.Column(db.String(50))
    institute_code = db.Column(db.String(30))
    institute_name = db.Column(db.String(255))
    maximum_marks = db.Column(db.Numeric(10, 2))
    maximum_credits = db.Column(db.Numeric(10, 2))
    maximum_grade_points = db.Column(db.Numeric(10, 2))
    report_generated_at_raw = db.Column(db.String(80))
    calculation_rule_version = db.Column(db.String(80))
    validation_status = db.Column(
        db.String(30), nullable=False, default="NOT_VALIDATED", server_default="NOT_VALIDATED"
    )
    validation_error_count = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    validation_warning_count = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    validated_at = db.Column(db.DateTime(timezone=True))
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

    import_job = db.relationship("ImportJob", back_populates="report")
    subjects = db.relationship(
        "ResultSubject",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ResultSubject.display_order",
    )
    students = db.relationship(
        "ReportStudent",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportStudent.id",
    )
    validation_issues = db.relationship(
        "ValidationIssue",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ValidationIssue.id",
    )
    corrections = db.relationship(
        "DataCorrection",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="DataCorrection.created_at.desc()",
    )

    @property
    def result_count(self) -> int:
        return sum(len(student.subject_results) for student in self.students)

    source_data = db.relationship(
        "ResultSourceData", back_populates="report", cascade="all, delete-orphan",
        single_parent=True, uselist=False,
    )

    def subject_codes_for_page(self, page):
        """Legacy reports used one common matrix; new reports retain each page."""
        if self.source_data is not None:
            return self.source_data.data.get("page_subject_codes", {}).get(str(page), [])
        return [subject.subject_code for subject in self.subjects]

    def additional_summary_for(self, seat_number):
        if self.source_data is None:
            return {}
        return self.source_data.data.get("additional_summaries", {}).get(seat_number, {})

    @property
    def expected_result_count(self):
        return sum(len(self.subject_codes_for_page(student.source_page)) for student in self.students)
