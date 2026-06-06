from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
db = SQLAlchemy()


# ── TABLE 1: students ────────────────────────────────────────
class Student(db.Model):
    __tablename__ = 'students'

    prn               = db.Column(db.String(20), primary_key=True)
    name              = db.Column(db.String(100), nullable=False)
    year_of_admission = db.Column(db.Integer, nullable=False)
    division          = db.Column(db.String(10), nullable=True)   # e.g. A / B
    batch             = db.Column(db.String(10), nullable=True)   # e.g. A1 / A2 / B1

    def to_dict(self):
        return {
            'prn':               self.prn,
            'name':              self.name,
            'year_of_admission': self.year_of_admission,
            'division':          self.division,
            'batch':             self.batch
        }


# ── TABLE 2: semesters ───────────────────────────────────────
class Semester(db.Model):
    __tablename__ = 'semesters'
    __table_args__ = (
        db.PrimaryKeyConstraint('semester_id', 'academic_year'),
    )

    semester_id   = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    is_active     = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'semester_id':   self.semester_id,
            'academic_year': self.academic_year,
            'is_active':     self.is_active
        }


# ── TABLE 3: subjects ────────────────────────────────────────
class Subject(db.Model):
    __tablename__ = 'subjects'

    subject_code = db.Column(db.String(20), primary_key=True)
    subject_name = db.Column(db.String(150), nullable=False)
    semester_id  = db.Column(db.Integer, nullable=False)
    subject_type = db.Column(
        db.Enum('THEORY', 'LAB', 'PROJECT', 'AUDIT'),
        nullable=False
    )
    credits     = db.Column(db.Integer, default=0)
    l_hours     = db.Column(db.Integer, default=0)
    t_hours     = db.Column(db.Integer, default=0)
    p_hours     = db.Column(db.Integer, default=0)
    category    = db.Column(db.String(20), default='')
    is_elective          = db.Column(db.Boolean, default=False)
    elective_group       = db.Column(db.String(50), nullable=True)
    parent_subject_code  = db.Column(db.String(20), nullable=True)
    is_audit             = db.Column(db.Boolean, default=False)
    is_attendance_only   = db.Column(db.Boolean, default=False, nullable=False)
    is_active            = db.Column(db.Boolean, default=True, nullable=False)

    def to_dict(self):
        return {
            'subject_code': self.subject_code,
            'subject_name': self.subject_name,
            'semester_id':  self.semester_id,
            'subject_type': self.subject_type,
            'credits':      self.credits,
            'category':     self.category,
            'is_elective':         self.is_elective,
            'elective_group':      self.elective_group,
            'parent_subject_code': self.parent_subject_code,
            'is_audit':            self.is_audit,
            'is_attendance_only':   self.is_attendance_only,
            'is_active':           self.is_active
        }


# ── TABLE 4: student_subject_enrollment ─────────────────────
class Enrollment(db.Model):
    __tablename__ = 'student_subject_enrollment'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'semester_id', 'academic_year',
                            name='uq_enrollment_prn_subject_sem_year'),
    )

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn           = db.Column(db.String(20),
                              db.ForeignKey('students.prn', ondelete='CASCADE'),
                              nullable=False)
    subject_code  = db.Column(db.String(20),
                              db.ForeignKey('subjects.subject_code', ondelete='CASCADE'),
                              nullable=False)
    semester_id   = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)

    student = db.relationship('Student', backref='enrollments')
    subject = db.relationship('Subject', backref='enrollments')


# ── TABLE 5: theory_marks ────────────────────────────────────
class TheoryMarks(db.Model):
    __tablename__ = 'theory_marks'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'semester_id', 'academic_year',
                            name='uq_theory_prn_subject_sem_year'),
    )

    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn            = db.Column(db.String(20),
                               db.ForeignKey('students.prn', ondelete='CASCADE'),
                               nullable=False)
    subject_code   = db.Column(db.String(20),
                               db.ForeignKey('subjects.subject_code', ondelete='CASCADE'),
                               nullable=False)
    semester_id    = db.Column(db.Integer, nullable=False)
    academic_year  = db.Column(db.String(10), nullable=False)

    # Raw marks entered by teacher via Excel
    ct1        = db.Column(db.Numeric(5, 2), default=None)
    ct2        = db.Column(db.Numeric(5, 2), default=None)
    assignment = db.Column(db.Numeric(5, 2), default=None)
    midsem     = db.Column(db.Numeric(5, 2), default=None)
    external   = db.Column(db.Numeric(5, 2), default=None)

    # Computed by Python automatically — never enter manually
    best_ct        = db.Column(db.Numeric(5, 2), default=None)
    ca_marks       = db.Column(db.Numeric(5, 2), default=None)
    internal_total = db.Column(db.Numeric(5, 2), default=None)
    total_marks    = db.Column(db.Numeric(5, 2), default=None)
    grade          = db.Column(db.String(4),     default=None)
    grade_point    = db.Column(db.Numeric(4, 2), default=None)
    is_passed      = db.Column(db.Boolean,       default=None)

    student = db.relationship('Student', backref='theory_marks')
    subject = db.relationship('Subject', backref='theory_marks')

    def to_dict(self):
        def f(v):
            return float(v) if v is not None else None
        return {
            'prn':            self.prn,
            'subject_code':   self.subject_code,
            'semester_id':    self.semester_id,
            'academic_year':  self.academic_year,
            'ct1':            f(self.ct1),
            'ct2':            f(self.ct2),
            'assignment':     f(self.assignment),
            'midsem':         f(self.midsem),
            'external':       f(self.external),
            'best_ct':        f(self.best_ct),
            'ca_marks':       f(self.ca_marks),
            'internal_total': f(self.internal_total),
            'total_marks':    f(self.total_marks),
            'grade':          self.grade,
            'grade_point':    f(self.grade_point),
            'is_passed':      self.is_passed
        }


# ── TABLE 6: lab_marks ───────────────────────────────────────
class LabMarks(db.Model):
    __tablename__ = 'lab_marks'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'semester_id', 'academic_year',
                            name='uq_lab_prn_subject_sem_year'),
    )

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn           = db.Column(db.String(20),
                              db.ForeignKey('students.prn', ondelete='CASCADE'),
                              nullable=False)
    subject_code  = db.Column(db.String(20),
                              db.ForeignKey('subjects.subject_code', ondelete='CASCADE'),
                              nullable=False)
    semester_id   = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)

    # Raw lab marks entered through Lab Marks module
    # CA1 + CA2 becomes internal marks (/60)
    ca1         = db.Column(db.Numeric(5, 2), default=None)   # /30
    ca2         = db.Column(db.Numeric(5, 2), default=None)   # /30

    internal    = db.Column(db.Numeric(5, 2), default=None)   # ca1 + ca2 = /60
    external    = db.Column(db.Numeric(5, 2), default=None)   # /40
    total_marks = db.Column(db.Numeric(5, 2), default=None)
    grade       = db.Column(db.String(4),     default=None)
    grade_point = db.Column(db.Numeric(4, 2), default=None)
    is_passed   = db.Column(db.Boolean,       default=None)

    student = db.relationship('Student', backref='lab_marks')
    subject = db.relationship('Subject', backref='lab_marks')

    def to_dict(self):
        def f(v):
            return float(v) if v is not None else None
        return {
            'prn':           self.prn,
            'subject_code':  self.subject_code,
            'semester_id':   self.semester_id,
            'academic_year': self.academic_year,
            'ca1':           f(self.ca1),
            'ca2':           f(self.ca2),
            'internal':      f(self.internal),
            'external':      f(self.external),
            'total_marks':   f(self.total_marks),
            'grade':         self.grade,
            'grade_point':   f(self.grade_point),
            'is_passed':     self.is_passed
        }


# ── TABLE 7: attendance ──────────────────────────────────────


# ── TABLE 7A: timetable_slots ─────────────────────────────────
class TimetableSlot(db.Model):
    """Weekly timetable slot uploaded once per semester.

    This is used to generate date-wise attendance sheets automatically.
    Example: Monday 10:00-11:15, Semester 6, Division A, Batch ALL, BTECPC601.
    """
    __tablename__ = 'timetable_slots'
    __table_args__ = (
        db.UniqueConstraint(
            'semester_id', 'academic_year', 'division', 'batch', 'day_of_week',
            'start_time', 'end_time', 'subject_code',
            name='uq_timetable_slot_unique'
        ),
    )

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    semester_id   = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    division      = db.Column(db.String(10), default='ALL', nullable=False)
    batch         = db.Column(db.String(10), default='ALL', nullable=False)
    day_of_week   = db.Column(db.String(10), nullable=False)  # Monday...Saturday
    start_time    = db.Column(db.Time, nullable=False)
    end_time      = db.Column(db.Time, nullable=False)
    subject_code  = db.Column(db.String(20), db.ForeignKey('subjects.subject_code', ondelete='CASCADE'), nullable=False)
    faculty_name  = db.Column(db.String(100), nullable=True)
    session_type  = db.Column(db.String(30), default='THEORY', nullable=False)
    room          = db.Column(db.String(50), nullable=True)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subject = db.relationship('Subject', backref=db.backref('timetable_slots', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'semester_id': self.semester_id,
            'academic_year': self.academic_year,
            'division': self.division,
            'batch': self.batch,
            'day_of_week': self.day_of_week,
            'start_time': self.start_time.strftime('%H:%M') if self.start_time else None,
            'end_time': self.end_time.strftime('%H:%M') if self.end_time else None,
            'subject_code': self.subject_code,
            'faculty_name': self.faculty_name,
            'session_type': self.session_type,
            'room': self.room,
            'is_active': self.is_active,
        }


# ── TABLE 7B: attendance_sessions ─────────────────────────────
class AttendanceSession(db.Model):
    """Actual lecture/lab dates generated from weekly timetable.

    One row means one conducted/scheduled class session for a subject on a date.
    """
    __tablename__ = 'attendance_sessions'
    __table_args__ = (
        db.UniqueConstraint(
            'semester_id', 'academic_year', 'division', 'batch', 'subject_code',
            'lecture_date', 'start_time', 'end_time',
            name='uq_attendance_session_unique'
        ),
    )

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    semester_id   = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    division      = db.Column(db.String(10), default='ALL', nullable=False)
    batch         = db.Column(db.String(10), default='ALL', nullable=False)
    subject_code  = db.Column(db.String(20), db.ForeignKey('subjects.subject_code', ondelete='CASCADE'), nullable=False)
    lecture_date  = db.Column(db.Date, nullable=False)
    start_time    = db.Column(db.Time, nullable=False)
    end_time      = db.Column(db.Time, nullable=False)
    session_type  = db.Column(db.String(30), default='THEORY', nullable=False)
    status        = db.Column(db.String(20), default='COMPLETED', nullable=False)  # COMPLETED/CANCELLED/EXTRA
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subject = db.relationship('Subject', backref=db.backref('attendance_sessions', lazy='dynamic'))


# ── TABLE 7C: attendance_entries ──────────────────────────────
class AttendanceEntry(db.Model):
    """Per-student date-wise attendance entry."""
    __tablename__ = 'attendance_entries'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'prn', name='uq_attendance_entry_session_prn'),
    )

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id', ondelete='CASCADE'), nullable=False)
    prn        = db.Column(db.String(20), db.ForeignKey('students.prn', ondelete='CASCADE'), nullable=False)
    status     = db.Column(db.String(10), default='A', nullable=False)  # P/A/L/O
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = db.relationship('AttendanceSession', backref=db.backref('entries', lazy='dynamic'))
    student = db.relationship('Student', backref=db.backref('attendance_entries', lazy='dynamic'))

class Attendance(db.Model):
    __tablename__ = 'attendance'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'semester_id', 'academic_year',
                            name='uq_attendance_prn_subject_sem_year'),
    )

    id                = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn               = db.Column(db.String(20),
                                  db.ForeignKey('students.prn', ondelete='CASCADE'),
                                  nullable=False)
    subject_code      = db.Column(db.String(20),
                                  db.ForeignKey('subjects.subject_code', ondelete='CASCADE'),
                                  nullable=False)
    semester_id       = db.Column(db.Integer, nullable=False)
    academic_year     = db.Column(db.String(10), nullable=False)
    total_lectures    = db.Column(db.Integer, default=0)
    attended_lectures = db.Column(db.Integer, default=0)
    percentage        = db.Column(db.Numeric(5, 2), default=0.00)

    student = db.relationship('Student', backref='attendance')

    def to_dict(self):
        return {
            'prn':               self.prn,
            'subject_code':      self.subject_code,
            'total_lectures':    self.total_lectures,
            'attended_lectures': self.attended_lectures,
            'percentage':        float(self.percentage) if self.percentage else 0
        }


# ── TABLE 8: sgpa_cgpa ───────────────────────────────────────
class SgpaCgpa(db.Model):
    __tablename__ = 'sgpa_cgpa'
    __table_args__ = (
        db.UniqueConstraint('prn', 'semester_id', 'academic_year',
                            name='uq_sgpa'),
    )

    id                 = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn                = db.Column(db.String(20),
                                   db.ForeignKey('students.prn', ondelete='CASCADE'),
                                   nullable=False)
    semester_id        = db.Column(db.Integer, nullable=False)
    academic_year      = db.Column(db.String(10), nullable=False)
    sgpa               = db.Column(db.Numeric(4, 2), default=None, nullable=True)
    cgpa               = db.Column(db.Numeric(4, 2), default=None, nullable=True)
    credits_registered = db.Column(db.Integer, default=0)
    credits_earned     = db.Column(db.Integer, default=0)

    student = db.relationship('Student', backref='sgpa_cgpa')

    def to_dict(self):
        return {
            'prn':                self.prn,
            'semester_id':        self.semester_id,
            'academic_year':      self.academic_year,
            'sgpa':               float(self.sgpa) if self.sgpa is not None else None,
            'cgpa':               float(self.cgpa) if self.cgpa is not None else None,
            'credits_registered': self.credits_registered,
            'credits_earned':     self.credits_earned
        }


# ── TABLE 9: users ───────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    user_id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username          = db.Column(db.String(50), unique=True, nullable=False)
    password_hash     = db.Column(db.String(255), nullable=False)
    role              = db.Column(db.Enum('ADMIN', 'TEACHER'), nullable=False)
    assigned_subjects = db.Column(db.Text, default=None)
    is_active         = db.Column(db.Boolean, default=True)

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_assigned_subjects(self):
        if self.assigned_subjects:
            return [s.strip() for s in self.assigned_subjects.split(',')]
        return []

    def to_dict(self):
        return {
            'user_id':  self.user_id,
            'username': self.username,
            'role':     self.role,
            'is_active':self.is_active
        }
# ─────────────────────────────────────────────────────────────────────────────
#  EXTERNAL MARKS MODULE  —  models_external.py
#  ECE Student Management System  |  CSMSS Chh. Shahu College of Engineering
#
#  ADD THIS CLASS TO YOUR EXISTING models.py
#  Do NOT replace the file — copy the class definition below into models.py
# ─────────────────────────────────────────────────────────────────────────────


# Import db from your existing app  →  from app import db   (already done in models.py)

class ExternalMarks(db.Model):
    """
    Stores ESE (End Semester Exam) external marks for THEORY subjects.
    Max = 60  |  Minimum to pass = 20
    Combined with internal marks to compute final total, grade, grade point, and credits.
    """
    __tablename__ = "external_marks"
    __table_args__ = (
        db.UniqueConstraint(
            "prn", "subject_code", "semester_id", "academic_year",
            name="uq_external_prn_subject_sem_year"
        ),
    )

    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prn            = db.Column(db.String(20), db.ForeignKey("students.prn", ondelete="CASCADE"), nullable=False)
    subject_code   = db.Column(db.String(20), db.ForeignKey("subjects.subject_code", ondelete="CASCADE"), nullable=False)
    semester_id    = db.Column(db.Integer, nullable=False)
    academic_year  = db.Column(db.String(10), nullable=False)
    external_marks = db.Column(db.Numeric(4, 1), nullable=True)
    locked         = db.Column(db.Boolean, default=False, nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student", backref=db.backref("external_marks", lazy="dynamic"))
    subject = db.relationship("Subject", backref=db.backref("external_marks", lazy="dynamic"))

    def __repr__(self):
        return (
            f"<ExternalMarks prn={self.prn} subject={self.subject_code} "
            f"semester={self.semester_id} marks={self.external_marks}>"
        )

    @property
    def is_passed_external(self):
        """ESE pass condition: external >= 20."""
        if self.external_marks is None:
            return None
        return float(self.external_marks) >= 20.0

    def to_dict(self):
        return {
            "id":             self.id,
            "prn":            self.prn,
            "subject_code":   self.subject_code,
            "semester_id":    self.semester_id,
            "academic_year":  self.academic_year,
            "external_marks": float(self.external_marks) if self.external_marks is not None else None,
            "locked":         self.locked,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "updated_at":     self.updated_at.isoformat() if self.updated_at else None,
        }
