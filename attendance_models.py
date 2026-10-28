"""Term calendars and append-only attendance decisions; legacy rows stay intact."""
from models import db
from workflow_models import now


class AttendanceCalendar(db.Model):
    __tablename__ = 'attendance_calendars'
    __table_args__ = (db.UniqueConstraint('semester_id', 'academic_year', name='uq_attendance_calendar_term'),)
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class AttendanceHoliday(db.Model):
    __tablename__ = 'attendance_holidays'
    __table_args__ = (db.UniqueConstraint('semester_id', 'academic_year', 'holiday_date', 'division', name='uq_attendance_holiday_scope'),)
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    holiday_date = db.Column(db.Date, nullable=False)
    division = db.Column(db.String(10), nullable=False, default='ALL')
    reason = db.Column(db.String(300), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class AttendanceChange(db.Model):
    __tablename__ = 'attendance_changes'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    before = db.Column(db.JSON, nullable=False, default=dict)
    after = db.Column(db.JSON, nullable=False, default=dict)
    review_token = db.Column(db.String(36), db.ForeignKey('workflow_reviews.token'))
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
    actor = db.relationship('User')
