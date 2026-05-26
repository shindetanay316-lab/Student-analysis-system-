from models import db, Student, Subject, TheoryMarks, Enrollment

# ── Subject lists per semester ────────────────────────────────
SEMESTER_SUBJECTS = {
    6: [
        "BTECPC601",
        "BTECPC602",
        "BTECPE603",
        "BTECOE604",
        "BTECHM605",
    ],
    4: [],
}

# ── Faculty map ───────────────────────────────────────────────
FACULTY_MAP = {
    "BTECPC601": {
        "abbr":    "IoT",
        "name":    "Internet of Things",
        "faculty": "Prof. J.N. Mohite",
    },
    "BTECPC602": {
        "abbr":    "AIML",
        "name":    "Artificial Intelligence & Machine Learning",
        "faculty": "Dr. P.G. Thombare",
    },
    "BTECPE603": {
        "abbr":    "PEC-3",
        "name":    "Professional Elective Course – 3",
        "faculty": "Prof. A.V. Khake",
    },
    "BTECOE604": {
        "abbr":    "OEC-2",
        "name":    "Open Elective Course – 2",
        "faculty": "Prof. S.B. Dhumal",
    },
    "BTECHM605": {
        "abbr":    "HSSMEC",
        "name":    "Humanities & Social Sciences",
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
    Queries existing theory_marks + enrollment tables.
    Returns a structured dictionary ready for both Excel and PDF generators.
    No new DB tables used.
    """
    exam_type     = exam_type.upper()
    subject_codes = SEMESTER_SUBJECTS.get(semester_id, [])
    column_name   = EXAM_COLUMN_MAP.get(exam_type, "ct1")
    pass_mark     = PASS_THRESHOLD.get(exam_type, 4)

    subject_stats = []

    for code in subject_codes:
        fm = FACULTY_MAP.get(code, {
            "abbr":    code,
            "name":    code,
            "faculty": "N/A",
        })

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

        absent  = 0
        passed  = 0
        failed  = 0

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
        result_pct = (
            round((passed / appeared) * 100)
            if appeared > 0 else 0
        )

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
    average_class_result = (
        round(sum(pcts) / len(pcts)) if pcts else 0
    )

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
            "division":             "A",
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