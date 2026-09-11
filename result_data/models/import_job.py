from datetime import datetime, timezone

from models import db


class ImportJob(db.Model):
    __tablename__ = "result_import_jobs"

    STATUS_UPLOADED = "UPLOADED"
    STATUS_EXTRACTING = "EXTRACTING"
    STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
    STATUS_READY = "READY"
    STATUS_FAILED = "FAILED"
    STATUS_EXPORTED = "EXPORTED"

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    page_count = db.Column(db.Integer)
    parser_version = db.Column(db.String(50))
    status = db.Column(
        db.String(30), nullable=False, default=STATUS_UPLOADED, index=True
    )
    error_message = db.Column(db.Text)
    confirmed_at = db.Column(db.DateTime(timezone=True))
    confirmed_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.user_id",
            name="fk_result_import_jobs_confirmed_by_id_users",
            ondelete="SET NULL",
        ),
        index=True,
    )
    confirmation_notes = db.Column(db.Text)
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

    report = db.relationship(
        "ExamReport",
        back_populates="import_job",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_id])

    @property
    def size_label(self) -> str:
        size = self.file_size_bytes
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"
