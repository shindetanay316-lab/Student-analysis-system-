from models import db


class ResultSourceData(db.Model):
    """Printed page applicability and optional source fields, without schema churn.

    A separate additive table keeps existing installations upgradeable with
    create_all(); no student/marks tables or existing columns are rewritten.
    """

    __tablename__ = "result_source_data"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer, db.ForeignKey("result_exam_reports.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    data = db.Column(db.JSON, nullable=False)
    report = db.relationship("ExamReport", back_populates="source_data")
