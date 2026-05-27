"""
One-time SGPA/CGPA refresh script for ECE SMS.
Run this after replacing calculations.py to repair already-created sgpa_cgpa rows.

Usage:
    python recalculate_all_sgpa_cgpa.py
"""

from app import app
from models import db, Enrollment
import models
from calculations import update_sgpa_cgpa_for_student


with app.app_context():
    pairs = (
        db.session.query(
            Enrollment.prn,
            Enrollment.semester_id,
            Enrollment.academic_year,
        )
        .distinct()
        .order_by(Enrollment.prn, Enrollment.semester_id)
        .all()
    )

    total = len(pairs)
    ok = 0
    failed = []

    for prn, semester_id, academic_year in pairs:
        try:
            update_sgpa_cgpa_for_student(
                prn=prn,
                semester_id=semester_id,
                academic_year=academic_year,
                db=db,
                models=models,
            )
            ok += 1
        except Exception as exc:
            db.session.rollback()
            failed.append((prn, semester_id, academic_year, str(exc)))

    print(f"SGPA/CGPA refresh complete: {ok}/{total} semester-student rows processed.")

    if failed:
        print("\nFailed rows:")
        for prn, semester_id, academic_year, error in failed[:50]:
            print(f"- {prn}, Sem {semester_id}, {academic_year}: {error}")
        if len(failed) > 50:
            print(f"... and {len(failed) - 50} more failures")
