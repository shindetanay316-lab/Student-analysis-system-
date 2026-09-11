from datetime import datetime, timezone

from models import db


class DataCorrection(db.Model):
    __tablename__ = "result_data_corrections"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer,
        db.ForeignKey("result_exam_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("result_report_students.id", ondelete="SET NULL"),
        index=True,
    )
    subject_result_id = db.Column(
        db.Integer,
        db.ForeignKey("result_subject_results.id", ondelete="SET NULL"),
        index=True,
    )
    result_component_id = db.Column(
        db.Integer,
        db.ForeignKey("result_result_components.id", ondelete="SET NULL"),
        index=True,
    )
    changed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="SET NULL"),
        index=True,
    )
    entity_type = db.Column(db.String(40), nullable=False, index=True)
    entity_label = db.Column(db.String(255), nullable=False)
    field_name = db.Column(db.String(80), nullable=False)
    original_value = db.Column(db.Text)
    previous_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    report = db.relationship("ExamReport", back_populates="corrections")
    student = db.relationship(
        "ReportStudent", back_populates="corrections", foreign_keys=[student_id]
    )
    subject_result = db.relationship("SubjectResult", foreign_keys=[subject_result_id])
    result_component = db.relationship(
        "ResultComponent", foreign_keys=[result_component_id]
    )
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])
