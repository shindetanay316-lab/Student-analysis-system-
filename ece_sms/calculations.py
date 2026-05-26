# ─────────────────────────────────────────────────────────────────────────────
#  calculations.py
#  ECE Student Management System  |  CSMSS Chh. Shahu College of Engineering
#
#  PURPOSE:
#    Helper functions for final result computation once External marks arrive.
#    All functions are PURE (no side-effects) — test them independently first.
#    Call these from your routes AFTER saving ExternalMarks to DB.
#
#  INTEGRATION:
#    Import into your existing calculations.py   OR   import directly in routes:
#      from calculations import compute_final_result, update_sgpa_cgpa
# ─────────────────────────────────────────────────────────────────────────────

from decimal import Decimal, ROUND_HALF_UP


# ── GRADING TABLE (as per DBATU Syllabus) ────────────────────────────────────

GRADE_TABLE = [
    (91, 100, "EX", Decimal("10.0")),
    (86,  90, "AA", Decimal("9.0")),
    (81,  85, "AB", Decimal("8.5")),
    (76,  80, "BB", Decimal("8.0")),
    (71,  75, "BC", Decimal("7.5")),
    (66,  70, "CC", Decimal("7.0")),
    (61,  65, "CD", Decimal("6.5")),
    (56,  60, "DD", Decimal("6.0")),
    (51,  55, "DE", Decimal("5.5")),
    (40,  50, "EE", Decimal("5.0")),
    ( 0,  39, "EF", Decimal("0.0")),   # FAIL
]


def get_grade(total_marks: float):
    """
    Returns (grade_letter, grade_point) for a given total out of 100.
    Always based on TOTAL marks — NOT on external alone.
    """
    total = float(total_marks)
    for low, high, grade, gp in GRADE_TABLE:
        if low <= total <= high:
            return grade, gp
    return "EF", Decimal("0.0")


# ── FINAL RESULT COMPUTATION ──────────────────────────────────────────────────

def compute_final_result(internal_marks: float, external_marks: float, credits: int):
    """
    Combines Internal (max 40) + External (max 60) → Final result dict.

    Pass conditions (BOTH must hold):
      1. Total >= 40
      2. External >= 20  (ESE minimum)

    Returns dict with:
      internal, external, total, grade, grade_point,
      credits_registered, credits_earned, is_passed, fail_reason
    """
    internal = float(internal_marks) if internal_marks is not None else 0.0
    external = float(external_marks) if external_marks is not None else None

    result = {
        "internal":           round(internal, 1),
        "external":           round(external, 1) if external is not None else None,
        "total":              None,
        "grade":              None,
        "grade_point":        None,
        "credits_registered": credits,
        "credits_earned":     0,
        "is_passed":          False,
        "fail_reason":        None,
    }

    if external is None:
        result["fail_reason"] = "External marks not entered"
        return result

    total = internal + external
    result["total"] = round(total, 1)

    # Determine pass / fail
    ese_pass   = external >= 20.0
    total_pass = total   >= 40.0

    if not ese_pass:
        result["is_passed"]   = False
        result["fail_reason"] = f"ESE below minimum (got {external}/60, need ≥20)"
        result["grade"]       = "EF"
        result["grade_point"] = Decimal("0.0")
        result["credits_earned"] = 0
    elif not total_pass:
        result["is_passed"]   = False
        result["fail_reason"] = f"Total below 40 (got {total}/100)"
        result["grade"]       = "EF"
        result["grade_point"] = Decimal("0.0")
        result["credits_earned"] = 0
    else:
        grade, gp = get_grade(total)
        result["is_passed"]      = True
        result["grade"]          = grade
        result["grade_point"]    = gp
        result["credits_earned"] = credits
        result["fail_reason"]    = None

    return result


# ── SGPA CALCULATION ──────────────────────────────────────────────────────────

def calculate_sgpa(subject_results: list):
    """
    subject_results: list of dicts, each with keys:
        credits_registered, grade_point, is_passed
        (audit subjects should be EXCLUDED before passing in)

    Returns: (sgpa, credits_registered_total, credits_earned_total)
    """
    total_credit_points = Decimal("0.0")
    total_credits_registered = 0
    total_credits_earned = 0

    for r in subject_results:
        cr = int(r["credits_registered"])
        gp = Decimal(str(r["grade_point"]))
        total_credit_points      += cr * gp
        total_credits_registered += cr
        if r["is_passed"]:
            total_credits_earned += cr

    if total_credits_registered == 0:
        return Decimal("0.00"), 0, 0

    sgpa = (total_credit_points / total_credits_registered).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return sgpa, total_credits_registered, total_credits_earned


def calculate_cgpa(semester_sgpa_list: list):
    """
    semester_sgpa_list: list of dicts, each with:
        credits_registered, credits_earned, sgpa
        (one dict per completed semester)

    Returns: cgpa (Decimal)
    """
    # CGPA = Σ(credits_registered_i × sgpa_i) / Σ(credits_registered_i)
    numerator   = Decimal("0.0")
    denominator = 0

    for s in semester_sgpa_list:
        cr   = int(s["credits_registered"])
        sgpa = Decimal(str(s["sgpa"]))
        numerator   += cr * sgpa
        denominator += cr

    if denominator == 0:
        return Decimal("0.00")

    return (numerator / denominator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── DB UPDATE HELPERS (call from Flask routes after saving ExternalMarks) ─────

def update_sgpa_cgpa_for_student(prn, semester_id, academic_year, db, models):
    """
    Recalculates and saves SGPA + CGPA for one student after external marks upload.

    Parameters:
        prn           : str
        semester_id   : int
        academic_year : str  e.g. "2024-25"
        db            : SQLAlchemy db instance
        models        : module or object exposing:
                          TheoryMarks, ExternalMarks, Subject,
                          Enrollment, SgpaCgpa, LabMarks

    Returns: dict  { "sgpa": ..., "cgpa": ..., "credits_registered": ..., "credits_earned": ... }
    """
    # 1. Fetch all enrolled subjects for this semester (non-audit)
    enrollments = (
        models.Enrollment.query
        .filter_by(prn=prn, semester_id=semester_id, academic_year=academic_year)
        .all()
    )

    subject_results = []
    has_missing_marks = False
    total_non_audit_credits = 0

    for enr in enrollments:
        subj = models.Subject.query.filter_by(subject_code=enr.subject_code).first()
        if subj is None or subj.is_audit:
            continue  # skip audit subjects

        total_non_audit_credits += subj.credits

        if subj.subject_type == 'THEORY':
            tm_row = models.TheoryMarks.query.filter_by(
                prn=prn,
                subject_code=subj.subject_code,
                academic_year=academic_year,
            ).first()

            ext_row = models.ExternalMarks.query.filter_by(
                prn=prn,
                subject_code=subj.subject_code,
                academic_year=academic_year,
            ).first()

            ext_val = None
            if tm_row and tm_row.external is not None:
                ext_val = float(tm_row.external)
            elif ext_row and ext_row.external_marks is not None:
                ext_val = float(ext_row.external_marks)

            if tm_row is None or tm_row.internal_total is None or ext_val is None:
                has_missing_marks = True
            else:
                internal_val = float(tm_row.internal_total)
                res = compute_final_result(internal_val, ext_val, subj.credits)
                subject_results.append(res)
        else:
            # LAB, PROJECT, etc.
            lm_row = models.LabMarks.query.filter_by(
                prn=prn,
                subject_code=subj.subject_code,
                academic_year=academic_year,
            ).first()

            if lm_row is None or lm_row.internal is None or lm_row.external is None:
                has_missing_marks = True
            else:
                subject_results.append({
                    "credits_registered": subj.credits,
                    "grade_point": float(lm_row.grade_point) if lm_row.grade_point is not None else 0.0,
                    "is_passed": lm_row.is_passed
                })

    # 2. Upsert into sgpa_cgpa table for THIS semester
    row = models.SgpaCgpa.query.filter_by(
        prn=prn,
        semester_id=semester_id,
        academic_year=academic_year,
    ).first()

    if row is None:
        row = models.SgpaCgpa(
            prn=prn,
            semester_id=semester_id,
            academic_year=academic_year,
        )
        db.session.add(row)

    if has_missing_marks:
        sgpa = None
        cr_reg = total_non_audit_credits
        cr_earned = 0
        
        row.sgpa               = None
        row.credits_registered = cr_reg
        row.credits_earned     = cr_earned
    else:
        sgpa, cr_reg, cr_earned = calculate_sgpa(subject_results)
        row.sgpa               = sgpa
        row.credits_registered = cr_reg
        row.credits_earned     = cr_earned

    # 3. Recalculate CGPA across ALL semesters for this student
    all_sem_rows = (
        models.SgpaCgpa.query
        .filter_by(prn=prn)
        .order_by(models.SgpaCgpa.semester_id)
        .all()
    )

    total_credit_points = Decimal("0.0")
    total_registered_credits = 0

    for s in all_sem_rows:
        if s.sgpa is not None:
            cr = int(s.credits_registered)
            sg = Decimal(str(s.sgpa))
            total_credit_points += cr * sg
            total_registered_credits += cr

    if total_registered_credits == 0:
        cgpa = None
    else:
        cgpa = (total_credit_points / total_registered_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Update CGPA on all semester rows (cumulative)
    for s in all_sem_rows:
        s.cgpa = cgpa

    db.session.commit()

    return {
        "sgpa":               float(sgpa) if sgpa is not None else None,
        "cgpa":               float(cgpa) if cgpa is not None else None,
        "credits_registered": cr_reg,
        "credits_earned":     cr_earned,
    }


# ── VALIDATION ────────────────────────────────────────────────────────────────

def validate_external_marks(value, subject_type="THEORY"):
    """
    Returns (is_valid: bool, error_message: str | None)
    Theory external: 0 – 60
    Lab external   : 0 – 40  (if you ever need it)
    """
    if value is None or str(value).strip() == "":
        return False, "External marks cannot be empty"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return False, f"'{value}' is not a valid number"

    if subject_type.upper() == "THEORY":
        if not (0.0 <= v <= 60.0):
            return False, f"Theory external must be 0–60 (got {v})"
    else:
        if not (0.0 <= v <= 40.0):
            return False, f"Lab external must be 0–40 (got {v})"

    return True, None


def update_internal_totals(row):
    ct1 = float(row.ct1 or 0)
    ct2 = float(row.ct2 or 0)
    assignment = float(row.assignment or 0)
    midsem = float(row.midsem or 0)

    row.best_ct = max(ct1, ct2)
    row.ca_marks = row.best_ct + assignment
    row.internal_total = row.ca_marks + midsem

    return row

