"""
Safe Phase 1 seed/backfill for ECE SMS.

This script does NOT insert fake students.
It only:
1. Ensures tables exist.
2. Creates/updates admin and teacher login users with hashed passwords.
3. Ensures Semester 1 and Semester 2 Group B subjects exist from DBATU First Year syllabus.
4. Ensures compulsory non-elective, non-audit enrollments exist.
5. Leaves elective option assignment for the admin page/manual SQL.

Run from ece_sms folder:
    python seed.py
"""

from app import app, db
from models import User, Student, Subject, Semester, Enrollment


FALLBACK_ACADEMIC_YEAR_MAP = {
    1: "2023-24",
    2: "2023-24",
    3: "2024-25",
    4: "2024-25",
    5: "2025-26",
    6: "2025-26",
    7: "2026-27",
    8: "2026-27",
}


# DBATU First Year Engineering — Group B syllabus subjects.
# Sem I total credits = 18, Sem II total credits = 19.
# Audit subjects are inserted but not enrolled/calculated in SGPA.
FIRST_YEAR_GROUP_B_SUBJECTS = [
    # Semester 1
    {
        "subject_code": "BTBS101",
        "subject_name": "Engineering Mathematics-I",
        "semester_id": 1,
        "subject_type": "THEORY",
        "credits": 4,
        "l_hours": 3,
        "t_hours": 1,
        "p_hours": 0,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTBS102",
        "subject_name": "Engineering Chemistry",
        "semester_id": 1,
        "subject_type": "THEORY",
        "credits": 4,
        "l_hours": 3,
        "t_hours": 1,
        "p_hours": 0,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES103",
        "subject_name": "Engineering Mechanics",
        "semester_id": 1,
        "subject_type": "THEORY",
        "credits": 3,
        "l_hours": 2,
        "t_hours": 1,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES104",
        "subject_name": "Computer Programming in C",
        "semester_id": 1,
        "subject_type": "THEORY",
        "credits": 3,
        "l_hours": 3,
        "t_hours": 0,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES105L",
        "subject_name": "Workshop Practices",
        "semester_id": 1,
        "subject_type": "LAB",
        "credits": 2,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 4,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES106",
        "subject_name": "Basic Electrical and Electronics Engineering",
        "semester_id": 1,
        "subject_type": "AUDIT",
        "credits": 0,
        "l_hours": 2,
        "t_hours": 0,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": True,
    },
    {
        "subject_code": "BTBS107L",
        "subject_name": "Engineering Chemistry Lab",
        "semester_id": 1,
        "subject_type": "LAB",
        "credits": 1,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 2,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES108L",
        "subject_name": "Engineering Mechanics Lab",
        "semester_id": 1,
        "subject_type": "LAB",
        "credits": 1,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 2,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },

    # Semester 2
    {
        "subject_code": "BTBS201",
        "subject_name": "Engineering Mathematics-II",
        "semester_id": 2,
        "subject_type": "THEORY",
        "credits": 4,
        "l_hours": 3,
        "t_hours": 1,
        "p_hours": 0,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTBS202",
        "subject_name": "Engineering Physics",
        "semester_id": 2,
        "subject_type": "THEORY",
        "credits": 4,
        "l_hours": 3,
        "t_hours": 1,
        "p_hours": 0,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES203",
        "subject_name": "Engineering Graphics",
        "semester_id": 2,
        "subject_type": "THEORY",
        "credits": 2,
        "l_hours": 2,
        "t_hours": 0,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTHM204",
        "subject_name": "Communication Skills",
        "semester_id": 2,
        "subject_type": "THEORY",
        "credits": 2,
        "l_hours": 2,
        "t_hours": 0,
        "p_hours": 0,
        "category": "HSSMC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES205",
        "subject_name": "Energy and Environment Engineering",
        "semester_id": 2,
        "subject_type": "THEORY",
        "credits": 2,
        "l_hours": 2,
        "t_hours": 0,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES206",
        "subject_name": "Basic Civil and Mechanical Engineering",
        "semester_id": 2,
        "subject_type": "AUDIT",
        "credits": 0,
        "l_hours": 2,
        "t_hours": 0,
        "p_hours": 0,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": True,
    },
    {
        "subject_code": "BTBS207L",
        "subject_name": "Engineering Physics Lab",
        "semester_id": 2,
        "subject_type": "LAB",
        "credits": 1,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 2,
        "category": "BSC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES208L",
        "subject_name": "Engineering Graphics Lab",
        "semester_id": 2,
        "subject_type": "LAB",
        "credits": 2,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 3,
        "category": "ESC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTHM209L",
        "subject_name": "Communication Skills Lab",
        "semester_id": 2,
        "subject_type": "LAB",
        "credits": 1,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 2,
        "category": "HSSMC",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    {
        "subject_code": "BTES210S",
        "subject_name": "Seminar",
        "semester_id": 2,
        "subject_type": "PROJECT",
        "credits": 1,
        "l_hours": 0,
        "t_hours": 0,
        "p_hours": 2,
        "category": "Seminar",
        "is_elective": False,
        "elective_group": None,
        "parent_subject_code": None,
        "is_audit": False,
    },
    # BTES211P appears in the FY Group B scheme as training to be evaluated in III Sem.
    # It is intentionally NOT inserted for Semester 2 here because this project already
    # uses BTES211P as the Semester 3 Internship-I Evaluation subject code.
]


def academic_year_for_subject(subject):
    """Prefer the semesters table; use fallback only if that row is missing."""
    sem = (
        Semester.query
        .filter_by(semester_id=subject.semester_id, is_active=True)
        .first()
    )
    if not sem:
        sem = (
            Semester.query
            .filter_by(semester_id=subject.semester_id)
            .order_by(Semester.academic_year.desc())
            .first()
        )
    return sem.academic_year if sem else FALLBACK_ACADEMIC_YEAR_MAP.get(subject.semester_id)


def ensure_semester_rows():
    """Create semester rows 1–8 if missing, without changing active semester."""
    created = 0
    for semester_id, academic_year in FALLBACK_ACADEMIC_YEAR_MAP.items():
        sem = Semester.query.filter_by(
            semester_id=semester_id,
            academic_year=academic_year,
        ).first()
        if sem is None:
            db.session.add(Semester(
                semester_id=semester_id,
                academic_year=academic_year,
                is_active=False,
            ))
            created += 1
    db.session.commit()
    print(f"Semester rows ready. Created: {created}")


def ensure_first_year_group_b_subjects():
    """Insert/update Sem 1 and Sem 2 Group B subjects from the DBATU FY syllabus."""
    created = 0
    updated = 0

    for data in FIRST_YEAR_GROUP_B_SUBJECTS:
        subject = Subject.query.get(data["subject_code"])
        if subject is None:
            subject = Subject(subject_code=data["subject_code"])
            db.session.add(subject)
            created += 1
        else:
            updated += 1

        subject.subject_name = data["subject_name"]
        subject.semester_id = data["semester_id"]
        subject.subject_type = data["subject_type"]
        subject.credits = data["credits"]
        subject.l_hours = data["l_hours"]
        subject.t_hours = data["t_hours"]
        subject.p_hours = data["p_hours"]
        subject.category = data["category"]
        subject.is_elective = data["is_elective"]
        subject.elective_group = data["elective_group"]
        subject.parent_subject_code = data["parent_subject_code"]
        subject.is_audit = data["is_audit"]

    db.session.commit()
    print(f"First Year Group B subjects ready. Created: {created}; updated: {updated}")


def ensure_active_semester():
    """Set exactly one active semester based on Config.CURRENT_SEMESTER."""
    current_semester = int(app.config.get("CURRENT_SEMESTER", 6))
    current_year = app.config.get("CURRENT_ACADEMIC_YEAR", FALLBACK_ACADEMIC_YEAR_MAP.get(current_semester, "2025-26"))

    sem = Semester.query.filter_by(
        semester_id=current_semester,
        academic_year=current_year,
    ).first()

    if sem is None:
        sem = Semester(
            semester_id=current_semester,
            academic_year=current_year,
            is_active=False,
        )
        db.session.add(sem)
        db.session.flush()

    Semester.query.update({Semester.is_active: False})
    sem.is_active = True
    db.session.commit()
    print(f"Active semester ready: Sem {current_semester} ({current_year})")


def ensure_users():
    users = [
        ("admin", "admin123", "ADMIN", None),
        ("teacher", "teacher123", "TEACHER", "BTECPC601,BTECPC602,BTECHM605"),
    ]

    for username, password, role, assigned_subjects in users:
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, role=role, assigned_subjects=assigned_subjects, is_active=True)
            db.session.add(user)
        else:
            user.role = role
            user.assigned_subjects = assigned_subjects
            user.is_active = True
        user.set_password(password)

    db.session.commit()
    print("Users ready: admin/admin123, teacher/teacher123")


def ensure_compulsory_enrollments():
    students = Student.query.order_by(Student.prn).all()
    if not students:
        print("No students found. Add students through your SQL first.")
        return

    subjects = (
        Subject.query
        .filter(Subject.semester_id.in_([1, 2, 3, 4, 5, 6, 7, 8]))
        .filter(Subject.is_elective == False)
        .filter(Subject.is_audit == False)
        .order_by(Subject.semester_id, Subject.subject_code)
        .all()
    )

    created = 0
    skipped = 0

    for student in students:
        for subject in subjects:
            academic_year = academic_year_for_subject(subject)
            if not academic_year:
                continue

            existing = Enrollment.query.filter_by(
                prn=student.prn,
                subject_code=subject.subject_code,
                semester_id=subject.semester_id,
                academic_year=academic_year,
            ).first()

            if existing:
                skipped += 1
                continue

            db.session.add(Enrollment(
                prn=student.prn,
                subject_code=subject.subject_code,
                semester_id=subject.semester_id,
                academic_year=academic_year,
            ))
            created += 1

    db.session.commit()
    print(f"Compulsory enrollments created: {created}; skipped existing: {skipped}")


def main():
    with app.app_context():
        db.create_all()
        print(f"Students: {Student.query.count()}")
        print(f"Subjects before seed: {Subject.query.count()}")
        ensure_semester_rows()
        ensure_first_year_group_b_subjects()
        ensure_users()
        ensure_active_semester()
        ensure_compulsory_enrollments()
        print(f"Subjects after seed: {Subject.query.count()}")
        print(f"Total enrollments: {Enrollment.query.count()}")
        print("Seed complete.")


if __name__ == "__main__":
    main()
