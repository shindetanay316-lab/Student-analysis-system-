"""
One-time SGPA/CGPA refresh script for ECE SMS.
Run this after replacing calculations.py to repair already-created sgpa_cgpa rows.

Usage:
    python recalculate_all_sgpa_cgpa.py

This version recalculates all rows in one transaction. If any row fails,
no partial SGPA/CGPA update is committed.
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
    failed = []

    try:
        for prn, semester_id, academic_year in pairs:
            update_sgpa_cgpa_for_student(
                prn=prn,
                semester_id=semester_id,
                academic_year=academic_year,
                db=db,
                models=models,
                commit=False,
            )

        db.session.commit()
        print(f"SGPA/CGPA refresh complete: {total}/{total} semester-student rows processed.")

    except Exception as exc:
        db.session.rollback()
        failed.append((prn, semester_id, academic_year, str(exc)))

        print("SGPA/CGPA refresh failed. No partial updates were committed.")
        print(f"Failed at: {prn}, Sem {semester_id}, {academic_year}: {exc}")
