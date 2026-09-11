from models import db


class StudentSummary(db.Model):
    __tablename__ = "result_student_summaries"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("result_report_students.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    reported_sgpa = db.Column(db.Numeric(8, 2))
    reported_total_grade_points = db.Column(db.Numeric(10, 2))
    reported_earned_credits = db.Column(db.Numeric(10, 2))
    reported_total_marks = db.Column(db.Numeric(10, 2))
    reported_status = db.Column(db.String(30))
    calculated_sgpa = db.Column(db.Numeric(8, 2))
    calculated_total_grade_points = db.Column(db.Numeric(10, 2))
    calculated_earned_credits = db.Column(db.Numeric(10, 2))
    calculated_total_marks = db.Column(db.Numeric(10, 2))
    calculated_status = db.Column(db.String(30))

    student = db.relationship("ReportStudent", back_populates="summary")
