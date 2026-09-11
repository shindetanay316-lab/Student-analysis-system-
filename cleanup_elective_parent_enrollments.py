"""
Remove invalid elective parent enrollments and refresh SGPA/CGPA.

Why this is needed:
Elective parent rows such as BTECHM505, BTECPE503 or BTECOE504 are only
containers. Students must be enrolled in one selected option such as BTECHM505B,
BTECPE503D, BTECOE504C. If a parent row is present in
student_subject_enrollment, final result / SGPA can show PENDING even though the
real option marks are complete.

Run from the ece_sms folder:
    python cleanup_elective_parent_enrollments.py
"""

from app import app
from models import db, Enrollment, Subject
import models
from calculations import update_sgpa_cgpa_for_student


with app.app_context():
    bad_rows = (
        db.session.query(Enrollment)
        .join(Subject, Enrollment.subject_code == Subject.subject_code)
        .filter(
            Subject.is_elective == True,
            Subject.parent_subject_code.is_(None),
        )
        .all()
    )

    affected = sorted({
        (row.prn, row.semester_id, row.academic_year)
        for row in bad_rows
    })

    deleted = len(bad_rows)

    try:
        for row in bad_rows:
            db.session.delete(row)

        for prn, semester_id, academic_year in affected:
            update_sgpa_cgpa_for_student(
                prn=prn,
                semester_id=semester_id,
                academic_year=academic_year,
                db=db,
                models=models,
                commit=False,
            )

        db.session.commit()

        print(f"Deleted invalid elective parent enrollment rows: {deleted}")
        print(f"Recalculated SGPA/CGPA for affected student-semester rows: {len(affected)}")
        if affected:
            print("Affected rows:")
            for prn, semester_id, academic_year in affected:
                print(f"  {prn} | Sem {semester_id} | {academic_year}")

    except Exception as exc:
        db.session.rollback()
        print("Cleanup failed. No partial changes were committed.")
        print(exc)
        raise
