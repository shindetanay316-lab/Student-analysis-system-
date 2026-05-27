"""
Safe Phase 1 seed/backfill for ECE SMS.
This script does NOT insert fake students or fake subjects.
It only:
1. Ensures tables exist.
2. Creates/updates admin and teacher login users with hashed passwords.
3. Ensures compulsory non-elective, non-audit enrollments exist.
4. Leaves elective option assignment for the admin page/manual SQL.

Run from ece_sms folder:
    python seed.py
"""

from app import app, db
from models import User, Student, Subject, Semester, Enrollment


ACADEMIC_YEAR_MAP = {
    3: "2024-25",
    4: "2024-25",
    5: "2025-26",
    6: "2025-26",
    7: "2026-27",
    8: "2026-27",
}


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
        .filter(Subject.semester_id.in_([3, 4, 5, 6, 7, 8]))
        .filter(Subject.is_elective == False)
        .filter(Subject.is_audit == False)
        .order_by(Subject.semester_id, Subject.subject_code)
        .all()
    )

    created = 0
    skipped = 0

    for student in students:
        for subject in subjects:
            academic_year = ACADEMIC_YEAR_MAP.get(subject.semester_id)
            if not academic_year:
                continue

            existing = Enrollment.query.filter_by(
                prn=student.prn,
                subject_code=subject.subject_code,
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
        print(f"Subjects: {Subject.query.count()}")
        ensure_users()
        ensure_compulsory_enrollments()
        print(f"Total enrollments: {Enrollment.query.count()}")
        print("Seed complete.")


if __name__ == "__main__":
    main()
