from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
db = SQLAlchemy()


# ── TABLE 1: students ────────────────────────────────────────
class Student(db.Model):
    __tablename__ = 'students'

    prn               = db.Column(db.String(20), primary_key=True)
    name              = db.Column(db.String(100), nullable=False)
    year_of_admission = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            'prn':               self.prn,
            'name':              self.name,
            'year_of_admission': self.year_of_admission
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
    is_elective = db.Column(db.Boolean, default=False)
    is_audit    = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'subject_code': self.subject_code,
            'subject_name': self.subject_name,
            'semester_id':  self.semester_id,
            'subject_type': self.subject_type,
            'credits':      self.credits,
            'category':     self.category,
            'is_elective':  self.is_elective,
            'is_audit':     self.is_audit
        }


# ── TABLE 4: student_subject_enrollment ─────────────────────
class Enrollment(db.Model):
    __tablename__ = 'student_subject_enrollment'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'academic_year',
                            name='uq_enrollment'),
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
        db.UniqueConstraint('prn', 'subject_code', 'academic_year',
                            name='uq_theory'),
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
        db.UniqueConstraint('prn', 'subject_code', 'academic_year',
                            name='uq_lab'),
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

    internal    = db.Column(db.Numeric(5, 2), default=None)
    external    = db.Column(db.Numeric(5, 2), default=None)
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
            'internal':      f(self.internal),
            'external':      f(self.external),
            'total_marks':   f(self.total_marks),
            'grade':         self.grade,
            'grade_point':   f(self.grade_point),
            'is_passed':     self.is_passed
        }


# ── TABLE 7: attendance ──────────────────────────────────────
class Attendance(db.Model):
    __tablename__ = 'attendance'
    __table_args__ = (
        db.UniqueConstraint('prn', 'subject_code', 'academic_year',
                            name='uq_attendance'),
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
    sgpa               = db.Column(db.Numeric(4, 2), default=0.00)
    cgpa               = db.Column(db.Numeric(4, 2), default=0.00)
    credits_registered = db.Column(db.Integer, default=0)
    credits_earned     = db.Column(db.Integer, default=0)

    student = db.relationship('Student', backref='sgpa_cgpa')

    def to_dict(self):
        return {
            'prn':                self.prn,
            'semester_id':        self.semester_id,
            'academic_year':      self.academic_year,
            'sgpa':               float(self.sgpa) if self.sgpa else 0,
            'cgpa':               float(self.cgpa) if self.cgpa else 0,
            'credits_registered': self.credits_registered,
            'credits_earned':     self.credits_earned
        }


# ── TABLE 9: users ───────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'

    user_id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username          = db.Column(db.String(50), unique=True, nullable=False)
    password_hash     = db.Column(db.String(255), nullable=False)
    role              = db.Column(db.Enum('ADMIN', 'TEACHER'), nullable=False)
    assigned_subjects = db.Column(db.Text, default=None)
    is_active         = db.Column(db.Boolean, default=True)

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
    Combined with InternalMarks to compute Final Total, Grade, Grade Point, Credits.
    """
    __tablename__ = "external_marks"

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    prn           = db.Column(db.String(20),  db.ForeignKey("students.prn", ondelete="CASCADE"), nullable=False)
    subject_code  = db.Column(db.String(20),  db.ForeignKey("subjects.subject_code", ondelete="CASCADE"), nullable=False)
    semester_id   = db.Column(db.Integer,     nullable=False)
    academic_year = db.Column(db.String(10),  nullable=False)          # e.g. "2024-25"
    external_marks= db.Column(db.Numeric(4,1),nullable=True)           # 0.0 – 60.0
    locked        = db.Column(db.Boolean,     default=False, nullable=False)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships (adjust back-ref names to match your existing models)
    student  = db.relationship("Student",  backref=db.backref("external_marks", lazy="dynamic"))
    subject  = db.relationship("Subject",  backref=db.backref("external_marks", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("prn", "subject_code", "academic_year",
                            name="uq_external_student_subject_year"),
    )

    def __repr__(self):
        return (f"<ExternalMarks student={self.prn} "
                f"subject={self.subject_code} marks={self.external_marks}>")

    # ── Convenience Properties ────────────────────────────────────────────────

    @property
    def is_passed_external(self):
        """ESE pass condition: external >= 20"""
        if self.external_marks is None:
            return None
        return float(self.external_marks) >= 20.0

    def to_dict(self):
        return {
            "id":            self.id,
            "prn":           self.prn,
            "subject_code":  self.subject_code,
            "semester_id":   self.semester_id,
            "academic_year": self.academic_year,
            "external_marks":float(self.external_marks) if self.external_marks is not None else None,
            "locked":        self.locked,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
            "updated_at":    self.updated_at.isoformat() if self.updated_at else None,
        }
