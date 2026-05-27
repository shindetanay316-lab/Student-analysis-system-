from sqlalchemy import or_

from models import db, Subject, TheoryMarks, Enrollment


# ── Optional faculty overrides ───────────────────────────────
# These are NOT used as the subject source anymore.
# Subjects now come from the subjects table dynamically.
FACULTY_MAP = {
    "BTECPC601": {
        "abbr":    "IoT",
        "faculty": "Prof. J.N. Mohite",
    },
    "BTECPC602": {
        "abbr":    "AIML",
        "faculty": "Dr. P.G. Thombare",
    },
    "BTECPE603": {
        "abbr":    "PEC-3",
        "faculty": "Prof. A.V. Khake",
    },
    "BTECOE604": {
        "abbr":    "OEC-2",
        "faculty": "Prof. S.B. Dhumal",
    },
    "BTECHM605": {
        "abbr":    "HSSMEC",
        "faculty": "Prof. B.R. Pawar",
    },
}

# ── Pass thresholds per exam type ────────────────────────────
PASS_THRESHOLD = {
    "CT1":        4,
    "CT2":        4,
    "MIDSEM":     8,
    "ASSIGNMENT": 4,
}

# ── Maps exam_type to theory_marks column name ────────────────
EXAM_COLUMN_MAP = {
    "CT1":        "ct1",
    "CT2":        "ct2",
    "MIDSEM":     "midsem",
    "ASSIGNMENT": "assignment",
}

# ── Class label per semester ──────────────────────────────────
SEMESTER_CLASS_LABEL = {
    1: "First Year",
    2: "First Year",
    3: "Second Year",
    4: "Second Year",
    5: "Third Year",
    6: "Third Year",
    7: "Final Year",
    8: "Final Year",
}

# ── Exam type display labels ──────────────────────────────────
EXAM_DISPLAY_LABEL = {
    "CT1":        "CLASS TEST – 1",
    "CT2":        "CLASS TEST – 2",
    "MIDSEM":     "MID SEMESTER EXAMINATION",
    "ASSIGNMENT": "ASSIGNMENT",
}


def _visible_summary_subjects(semester_id):
    """Fetch summary subjects from database, not from a hardcoded list.

    Rules:
    - THEORY subjects only
    - audit subjects excluded
    - compulsory subjects included
    - real elective options included
    - generic elective parent rows hidden
    """
    return (
        Subject.query
        .filter(Subject.semester_id == semester_id)
        .filter(Subject.subject_type == "THEORY")
        .filter(Subject.is_audit == False)
        .filter(
            or_(
                Subject.is_elective == False,
                Subject.parent_subject_code.isnot(None),
            )
        )
        .order_by(Subject.subject_code)
        .all()
    )


def _subject_abbr(subject):
    """Create a readable abbreviation when no faculty override exists."""
    if subject.elective_group:
        return subject.elective_group
    if subject.category:
        return subject.category
    return subject.subject_code


def _faculty_info(subject):
    override = FACULTY_MAP.get(subject.subject_code, {})
    return {
        "abbr": override.get("abbr") or _subject_abbr(subject),
        "name": subject.subject_name,
        "faculty": override.get("faculty") or "N/A",
    }


def build_summary_data(
    semester_id,
    exam_type    = "CT1",
    academic_year= "2024-25",
    date_from    = None,
    date_to      = None,
    coordinator  = "",
    dean         = "",
    principal    = "",
):
    """
    Queries existing subjects + theory_marks + enrollment tables.

    Dynamic cleanup:
    - No SEMESTER_SUBJECTS hardcoded list.
    - Subject list comes from the subjects table.
    - Audit subjects and generic elective parent rows are hidden.
    """
    exam_type   = exam_type.upper()
    subjects    = _visible_summary_subjects(semester_id)
    column_name = EXAM_COLUMN_MAP.get(exam_type, "ct1")
    pass_mark   = PASS_THRESHOLD.get(exam_type, 4)

    subject_stats = []

    for subj in subjects:
        code = subj.subject_code
        fm = _faculty_info(subj)

        # Total enrolled for this subject + semester
        enrolled_count = (
            db.session.query(Enrollment)
            .filter(
                Enrollment.subject_code  == code,
                Enrollment.semester_id   == semester_id,
                Enrollment.academic_year == academic_year,
            )
            .count()
        )

        # All theory_marks rows for this subject
        marks_rows = (
            TheoryMarks.query
            .filter_by(
                subject_code  = code,
                academic_year = academic_year,
                semester_id   = semester_id,
            )
            .all()
        )

        # Build a lookup: prn → mark value (or None)
        marks_lookup = {}
        for row in marks_rows:
            val = getattr(row, column_name, None)
            marks_lookup[row.prn] = (
                float(val) if val is not None else None
            )

        # Get all enrolled PRNs
        enrolled_prns = [
            e.prn for e in
            db.session.query(Enrollment)
            .filter(
                Enrollment.subject_code  == code,
                Enrollment.semester_id   == semester_id,
                Enrollment.academic_year == academic_year,
            )
            .all()
        ]

        absent = passed = failed = 0

        for prn in enrolled_prns:
            mark = marks_lookup.get(prn, None)
            if mark is None:
                absent += 1
            elif mark >= pass_mark:
                passed += 1
            else:
                failed += 1

        appeared   = passed + failed
        total      = enrolled_count if enrolled_count > 0 else len(enrolled_prns)
        result_pct = round((passed / appeared) * 100) if appeared > 0 else 0

        subject_stats.append({
            "subject_code": code,
            "abbr":         fm["abbr"],
            "name":         fm["name"],
            "faculty":      fm["faculty"],
            "total":        total,
            "appeared":     appeared,
            "passed":       passed,
            "failed":       failed,
            "absent":       absent,
            "result_pct":   result_pct,
        })

    # Average class result across all subjects
    pcts = [s["result_pct"] for s in subject_stats if s["appeared"] > 0]
    average_class_result = round(sum(pcts) / len(pcts)) if pcts else 0

    # Faculty table rows (ordered same as subject_stats)
    faculty_table = [
        {
            "abbr":    s["abbr"],
            "name":    s["name"],
            "faculty": s["faculty"],
        }
        for s in subject_stats
    ]

    exam_label = EXAM_DISPLAY_LABEL.get(exam_type, exam_type)
    class_label = SEMESTER_CLASS_LABEL.get(semester_id, f"Semester {semester_id}")

    date_range = ""
    if date_from and date_to:
        date_range = f"{date_from} to {date_to}"
    elif date_from:
        date_range = f"From {date_from}"

    return {
        "report_meta": {
            "college":       "CSMSS Chh. Shahu College of Engineering",
            "trust":         "Chhatrapati Shahu Maharaj Shikshan Sanstha's",
            "department":    "Department of Electronics and Computer Engineering",
            "academic_year": academic_year,
            "semester_id":   semester_id,
            "exam_type":     exam_type,
            "exam_label":    exam_label,
            "report_title":  f"{exam_label} RESULT SUMMARY",
            "date_range":    date_range,
            "form_no":       "AC-12",
        },
        "class_summary": {
            "class_name":           class_label,
            "division":             "All",
            "average_class_result": average_class_result,
        },
        "subjects":      subject_stats,
        "faculty_table": faculty_table,
        "signatories": {
            "coordinator": coordinator or "—",
            "hod":         "Dr. D. L. Bhuyar",
            "dean":        dean or "—",
            "principal":   principal or "—",
        },
    }
