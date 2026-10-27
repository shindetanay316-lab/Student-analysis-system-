from models import db


class ResultReportSettings(db.Model):
    __tablename__ = 'result_report_settings'
    id = db.Column(db.Integer, primary_key=True)
    import_job_id = db.Column(db.Integer, db.ForeignKey('result_import_jobs.id', ondelete='CASCADE'),
                              nullable=False, unique=True, index=True)
    data = db.Column(db.JSON, nullable=False)
    import_job = db.relationship('ImportJob', back_populates='report_settings')
