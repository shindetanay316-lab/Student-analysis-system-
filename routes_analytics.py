from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import and_, or_, func

from models import (
    db,
    Student,
    Subject,
    Enrollment,
    TheoryMarks,
    LabMarks,
    Attendance,
    SgpaCgpa,
)
from academic_utils import get_academic_year_for_semester
from final_result_utils import build_student_semester_result, calculate_cgpa_for_student
from calculations import is_gradable_subject

analytics_bp = Blueprint("analytics", __name__, url_prefix="")

FAIL_GRADES = {"FF", "EF", "F"}  # FF is official; EF/F kept only for old DB rows


# -----------------------------------------------------------------------------
# Common helpers
# -----------------------------------------------------------------------------
def _gradable_subject_filter():
    """SQL filter for subjects that should count in result/analytics.

    Elective parent rows such as BTECPE503 / BTECOE504 / BTECHM505 are only
    containers, so they must not appear as pending or failed subjects.
    """
    return and_(
        Subject.is_audit == False,
        Subject.is_active == True,
        Subject.is_attendance_only == False,
        Subject.credits > 0,
        or_(Subject.is_elective == False, Subject.parent_subject_code.isnot(None)),
    )


def _status_from_row(row):
    grade = (getattr(row, "grade", None) or "").upper()
    is_passed = getattr(row, "is_passed", None)
    total_marks = getattr(row, "total_marks", None)

    if is_passed is True or is_passed == 1:
        return "PASS"
    if is_passed is False or is_passed == 0 or grade in FAIL_GRADES:
        return "FAIL"
    if total_marks is None or not grade:
        return "PENDING"
    return "PASS"


def _result_payload(row, subject, student, semester_id=None, academic_year=None):
    from term_services import students_in_term
    student=students_in_term([student],semester_id or subject.semester_id,academic_year or getattr(row,'academic_year',''))[0]
    status = _status_from_row(row)
    return {
        "prn": student.prn,
        "student_name": student.name,
        "name": student.name,  # kept for old JS compatibility
        "division": student.division or "",
        "batch": student.batch or "",
        "semester_id": semester_id if semester_id is not None else subject.semester_id,
        "academic_year": academic_year or getattr(row, "academic_year", ""),
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "credits": int(subject.credits or 0),
        "total_marks": float(row.total_marks) if row.total_marks is not None else None,
        "grade": row.grade or "PENDING",
        "grade_point": float(row.grade_point) if row.grade_point is not None else None,
        "status": status,
    }


def _failure_condition(model):
    return or_(
        model.is_passed.is_(False),
        model.grade.in_(list(FAIL_GRADES)),
    )


# -----------------------------------------------------------------------------
# Page
# -----------------------------------------------------------------------------
@analytics_bp.route("/analytics")
@login_required
def analytics_page():
    semesters = (
        db.session.query(Enrollment.semester_id, Enrollment.academic_year)
        .join(Subject, Enrollment.subject_code == Subject.subject_code)
        .filter(_gradable_subject_filter())
        .distinct()
        .order_by(Enrollment.semester_id, Enrollment.academic_year)
        .all()
    )

    subjects = (
        db.session.query(Subject)
        .join(Enrollment, Enrollment.subject_code == Subject.subject_code)
        .filter(_gradable_subject_filter())
        .distinct()
        .order_by(Subject.semester_id, Subject.subject_code)
        .all()
    )

    students = Student.query.order_by(Student.prn).all()

    return render_template(
        "analytics.html",
        semesters=semesters,
        subjects=subjects,
        students=students,
    )


@analytics_bp.route("/api/analytics/subjects/<int:sem>")
@login_required
def get_analytics_subjects_for_semester(sem):
    """Return only gradable subjects for the selected semester.

    This keeps the Subject Failures dropdown and the analytics view aligned: when
    Semester 5 is selected, only Semester 5 subjects are shown.
    """
    academic_year = request.args.get("academic_year", "").strip()
    if not academic_year:
        academic_year = get_academic_year_for_semester(sem)

    subjects = (
        db.session.query(Subject)
        .join(Enrollment, Enrollment.subject_code == Subject.subject_code)
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.semester_id == sem,
            _gradable_subject_filter(),
        )
        .distinct()
        .order_by(Subject.subject_code)
        .all()
    )

    return jsonify({
        "semester_id": sem,
        "academic_year": academic_year,
        "subjects": [
            {
                "subject_code": sub.subject_code,
                "subject_name": sub.subject_name,
                "semester_id": sub.semester_id,
                "subject_type": sub.subject_type,
                "credits": int(sub.credits or 0),
            }
            for sub in subjects
        ],
    })


# -----------------------------------------------------------------------------
# Visual Analytics Dashboard API
# -----------------------------------------------------------------------------
def _completed_semester_rows(sem, academic_year):
    """Return completed theory + lab/project result rows for one semester.

    Every query goes through student_subject_enrollment, so elective parent rows are
    ignored and only the student's selected elective option is counted.
    """
    theory_rows = (
        db.session.query(Student, Subject, TheoryMarks)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .join(
            TheoryMarks,
            and_(
                TheoryMarks.prn == Enrollment.prn,
                TheoryMarks.subject_code == Enrollment.subject_code,
                TheoryMarks.semester_id == Enrollment.semester_id,
                TheoryMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type == "THEORY",
            _gradable_subject_filter(),
            TheoryMarks.total_marks.isnot(None),
        )
        .all()
    )

    lab_rows = (
        db.session.query(Student, Subject, LabMarks)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .join(
            LabMarks,
            and_(
                LabMarks.prn == Enrollment.prn,
                LabMarks.subject_code == Enrollment.subject_code,
                LabMarks.semester_id == Enrollment.semester_id,
                LabMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type.in_(["LAB", "PROJECT"]),
            _gradable_subject_filter(),
            LabMarks.total_marks.isnot(None),
        )
        .all()
    )

    from types import SimpleNamespace
    from completion_models import AssessmentPolicy, AssessmentScore
    from assessment_services import evaluate
    configured=[]
    for policy,score,student,subject in db.session.query(AssessmentPolicy,AssessmentScore,Student,Subject).join(
        AssessmentScore,AssessmentScore.policy_token==AssessmentPolicy.token).join(Student,Student.prn==AssessmentScore.prn).join(
        Subject,Subject.subject_code==AssessmentPolicy.subject_code).join(Enrollment,db.and_(Enrollment.prn==Student.prn,
        Enrollment.subject_code==Subject.subject_code,Enrollment.semester_id==sem,Enrollment.academic_year==academic_year)).filter(
        AssessmentPolicy.semester_id==sem,AssessmentPolicy.academic_year==academic_year,AssessmentPolicy.status=='APPROVED',_gradable_subject_filter()):
        result=evaluate(policy,score.values)
        if result['result']=='PENDING':
            continue
        maximum=sum(float(g['maximum']) for g in policy.rules['groups'])
        configured.append((student,subject,SimpleNamespace(total_marks=round(result['total']/maximum*100,2),
            grade=result['grade'],grade_point=result['grade_point'],is_passed=result['result']=='PASS',academic_year=academic_year)))
    return theory_rows + lab_rows + configured


def _pending_count_for_semester(sem, academic_year):
    theory_pending = (
        db.session.query(func.count(Enrollment.id))
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .outerjoin(
            TheoryMarks,
            and_(
                TheoryMarks.prn == Enrollment.prn,
                TheoryMarks.subject_code == Enrollment.subject_code,
                TheoryMarks.semester_id == Enrollment.semester_id,
                TheoryMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type == "THEORY",
            _gradable_subject_filter(),
            or_(TheoryMarks.id.is_(None), TheoryMarks.total_marks.is_(None), TheoryMarks.grade.is_(None)),
        )
        .scalar()
        or 0
    )

    lab_pending = (
        db.session.query(func.count(Enrollment.id))
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .outerjoin(
            LabMarks,
            and_(
                LabMarks.prn == Enrollment.prn,
                LabMarks.subject_code == Enrollment.subject_code,
                LabMarks.semester_id == Enrollment.semester_id,
                LabMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type.in_(["LAB", "PROJECT"]),
            _gradable_subject_filter(),
            or_(LabMarks.id.is_(None), LabMarks.total_marks.is_(None), LabMarks.grade.is_(None)),
        )
        .scalar()
        or 0
    )

    from completion_models import AssessmentPolicy
    codes={p.subject_code for p in AssessmentPolicy.query.filter_by(semester_id=sem,academic_year=academic_year,status='APPROVED')}
    complete_configured=sum(1 for _student,subject,_row in _completed_semester_rows(sem,academic_year) if subject.subject_code in codes)
    return max(0,int(theory_pending + lab_pending)-complete_configured)


@analytics_bp.route("/api/analytics/visual")
@login_required
def get_visual_analytics():
    sem = request.args.get("semester", type=int)
    academic_year = request.args.get("academic_year", "").strip()

    if not sem:
        latest = (
            db.session.query(Enrollment.semester_id, Enrollment.academic_year)
            .join(Subject, Enrollment.subject_code == Subject.subject_code)
            .filter(_gradable_subject_filter())
            .distinct()
            .order_by(Enrollment.semester_id.desc(), Enrollment.academic_year.desc())
            .first()
        )
        if latest:
            sem, academic_year = latest
        else:
            return jsonify({"error": "No enrolled semester data found."}), 404

    if not academic_year:
        academic_year = get_academic_year_for_semester(sem)

    rows = _completed_semester_rows(sem, academic_year)
    pending_count = _pending_count_for_semester(sem, academic_year)

    if not rows:
        return jsonify({
            "semester_id": sem,
            "academic_year": academic_year,
            "cards": {
                "top_scorer": {"value": "PENDING", "student_name": "No completed marks yet"},
                "class_average": None,
                "lowest_marks": None,
                "avg_attendance": None,
                "total_backlogs": 0,
                "backlog_students": 0,
                "pending_results": pending_count,
                "students_count": 0,
            },
            "subject_averages": [],
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "Fail": 0},
        })

    total_marks = [float(row.total_marks) for _student, _subject, row in rows if row.total_marks is not None]

    # Student averages and topper
    by_student = {}
    for student, _subject, row in rows:
        if row.total_marks is None:
            continue
        bucket = by_student.setdefault(student.prn, {"name": student.name, "marks": []})
        bucket["marks"].append(float(row.total_marks))

    top_scorer = {"value": None, "student_name": "-"}
    if by_student:
        prn, data = max(by_student.items(), key=lambda item: sum(item[1]["marks"]) / len(item[1]["marks"]))
        avg_score = round(sum(data["marks"]) / len(data["marks"]), 2)
        top_scorer = {"value": avg_score, "student_name": data["name"], "prn": prn}

    # Subject average marks
    by_subject = {}
    for _student, subject, row in rows:
        if row.total_marks is None:
            continue
        bucket = by_subject.setdefault(
            subject.subject_code,
            {"subject_code": subject.subject_code, "subject_name": subject.subject_name, "marks": []},
        )
        bucket["marks"].append(float(row.total_marks))

    subject_averages = []
    for item in by_subject.values():
        if not item["marks"]:
            continue
        subject_averages.append({
            "subject_code": item["subject_code"],
            "subject_name": item["subject_name"],
            "average": round(sum(item["marks"]) / len(item["marks"]), 2),
        })
    subject_averages.sort(key=lambda x: x["subject_code"])

    # Grade distribution by total marks bands shown in the reference UI.
    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "Fail": 0}
    backlog_students = set()
    total_backlogs = 0
    for student, _subject, row in rows:
        mark = float(row.total_marks)
        status = _status_from_row(row)
        if status == "FAIL":
            grade_distribution["Fail"] += 1
            total_backlogs += 1
            backlog_students.add(student.prn)
        elif mark >= 90:
            grade_distribution["A"] += 1
        elif mark >= 75:
            grade_distribution["B"] += 1
        elif mark >= 60:
            grade_distribution["C"] += 1
        else:
            grade_distribution["D"] += 1

    avg_attendance_row = (
        db.session.query(func.avg(Attendance.percentage))
        .filter(
            Attendance.semester_id == sem,
            Attendance.academic_year == academic_year,
        )
        .scalar()
    )
    avg_attendance = round(float(avg_attendance_row), 2) if avg_attendance_row is not None else None

    return jsonify({
        "semester_id": sem,
        "academic_year": academic_year,
        "cards": {
            "top_scorer": top_scorer,
            "class_average": round(sum(total_marks) / len(total_marks), 2) if total_marks else None,
            "lowest_marks": round(min(total_marks), 2) if total_marks else None,
            "avg_attendance": avg_attendance,
            "total_backlogs": total_backlogs,
            "backlog_students": len(backlog_students),
            "pending_results": pending_count,
            "students_count": len(by_student),
        },
        "subject_averages": subject_averages,
        "grade_distribution": grade_distribution,
    })


# -----------------------------------------------------------------------------
# Filter 1: Semester backlogs
# -----------------------------------------------------------------------------
@analytics_bp.route("/api/analytics/semester/<int:sem>")
@login_required
def get_semester_backlogs(sem):
    academic_year = request.args.get("academic_year", "").strip()
    if not academic_year:
        academic_year = get_academic_year_for_semester(sem)

    theory_rows = (
        db.session.query(Student, Subject, TheoryMarks)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .join(
            TheoryMarks,
            and_(
                TheoryMarks.prn == Enrollment.prn,
                TheoryMarks.subject_code == Enrollment.subject_code,
                TheoryMarks.semester_id == Enrollment.semester_id,
                TheoryMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type == "THEORY",
            _gradable_subject_filter(),
            _failure_condition(TheoryMarks),
        )
        .order_by(Subject.subject_code, Student.prn)
        .all()
    )

    lab_rows = (
        db.session.query(Student, Subject, LabMarks)
        .join(Enrollment, Enrollment.prn == Student.prn)
        .join(Subject, Subject.subject_code == Enrollment.subject_code)
        .join(
            LabMarks,
            and_(
                LabMarks.prn == Enrollment.prn,
                LabMarks.subject_code == Enrollment.subject_code,
                LabMarks.semester_id == Enrollment.semester_id,
                LabMarks.academic_year == Enrollment.academic_year,
            ),
        )
        .filter(
            Enrollment.semester_id == sem,
            Enrollment.academic_year == academic_year,
            Subject.subject_type.in_(["LAB", "PROJECT"]),
            _gradable_subject_filter(),
            _failure_condition(LabMarks),
        )
        .order_by(Subject.subject_code, Student.prn)
        .all()
    )

    data = [
        _result_payload(row, subject, student, sem, academic_year)
        for student, subject, row in theory_rows
    ] + [
        _result_payload(row, subject, student, sem, academic_year)
        for student, subject, row in lab_rows
    ]

    data.sort(key=lambda x: (x["subject_code"], x["prn"]))

    return jsonify({
        "semester_id": sem,
        "academic_year": academic_year,
        "count": len(data),
        "rows": data,
        # Compatibility: old frontend expected a plain list sometimes.
        "data": data,
    })


# -----------------------------------------------------------------------------
# Filter 2: Subject failures
# -----------------------------------------------------------------------------
@analytics_bp.route("/api/analytics/subject/<path:subject_code>")
@login_required
def get_subject_failures(subject_code):
    subject_code = (subject_code or "").strip()
    subject = Subject.query.filter_by(subject_code=subject_code).first()
    if not subject or not is_gradable_subject(subject):
        return jsonify({"error": "Subject not found or not gradable.", "rows": [], "data": []}), 404

    if subject.subject_type == "THEORY":
        rows = (
            db.session.query(Student, Subject, TheoryMarks)
            .join(Enrollment, Enrollment.prn == Student.prn)
            .join(Subject, Subject.subject_code == Enrollment.subject_code)
            .join(
                TheoryMarks,
                and_(
                    TheoryMarks.prn == Enrollment.prn,
                    TheoryMarks.subject_code == Enrollment.subject_code,
                    TheoryMarks.semester_id == Enrollment.semester_id,
                    TheoryMarks.academic_year == Enrollment.academic_year,
                ),
            )
            .filter(
                Enrollment.subject_code == subject_code,
                _gradable_subject_filter(),
                _failure_condition(TheoryMarks),
            )
            .order_by(Enrollment.academic_year, Enrollment.semester_id, Student.prn)
            .all()
        )
    else:
        rows = (
            db.session.query(Student, Subject, LabMarks)
            .join(Enrollment, Enrollment.prn == Student.prn)
            .join(Subject, Subject.subject_code == Enrollment.subject_code)
            .join(
                LabMarks,
                and_(
                    LabMarks.prn == Enrollment.prn,
                    LabMarks.subject_code == Enrollment.subject_code,
                    LabMarks.semester_id == Enrollment.semester_id,
                    LabMarks.academic_year == Enrollment.academic_year,
                ),
            )
            .filter(
                Enrollment.subject_code == subject_code,
                _gradable_subject_filter(),
                _failure_condition(LabMarks),
            )
            .order_by(Enrollment.academic_year, Enrollment.semester_id, Student.prn)
            .all()
        )

    data = [
        _result_payload(row, subj, student, row.semester_id, row.academic_year)
        for student, subj, row in rows
    ]

    return jsonify({
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "count": len(data),
        "rows": data,
        "data": data,
    })


# -----------------------------------------------------------------------------
# Filter 3: Student full academic history + eligibility
# -----------------------------------------------------------------------------
def _student_semesters(prn):
    return (
        db.session.query(Enrollment.semester_id, Enrollment.academic_year)
        .join(Subject, Enrollment.subject_code == Subject.subject_code)
        .filter(
            Enrollment.prn == prn,
            _gradable_subject_filter(),
        )
        .distinct()
        .order_by(Enrollment.semester_id, Enrollment.academic_year)
        .all()
    )


def _student_history(prn):
    history = []
    semester_summaries = []

    for sem_id, ay in _student_semesters(prn):
        sem_result = build_student_semester_result(prn, sem_id, ay)
        semester_summaries.append({
            "semester_id": sem_id,
            "academic_year": ay,
            "sgpa": sem_result.get("sgpa"),
            "total_credits": sem_result.get("total_credits", 0),
            "credits_earned": sem_result.get("credits_earned", 0),
            "is_complete": sem_result.get("is_complete", False),
            "result": sem_result.get("result", "PENDING"),
        })

        for subject_row in sem_result.get("subjects", []):
            status = subject_row.get("result") or "PENDING"
            history.append({
                "semester_id": sem_id,
                "sem": sem_id,  # old JS compatibility
                "academic_year": ay,
                "subject_code": subject_row.get("subject_code"),
                "subject_name": subject_row.get("subject_name"),
                "name": subject_row.get("subject_name"),  # old JS compatibility
                "credits": subject_row.get("credits", 0),
                "internal": float(subject_row["internal"]) if subject_row.get("internal") is not None else None,
                "external": float(subject_row["external"]) if subject_row.get("external") is not None else None,
                "total_marks": float(subject_row["total"]) if subject_row.get("total") is not None else None,
                "grade": subject_row.get("grade") or "PENDING",
                "grade_point": float(subject_row["grade_point"]) if subject_row.get("grade_point") is not None else None,
                "result": status,
            })

    return history, semester_summaries


def _latest_cgpa(prn, upto_semester_id=None):
    calculated = calculate_cgpa_for_student(prn, upto_semester_id=upto_semester_id)
    if calculated is not None:
        return calculated

    query = SgpaCgpa.query.filter_by(prn=prn)
    if upto_semester_id is not None:
        query = query.filter(SgpaCgpa.semester_id <= upto_semester_id)

    row = (
        query
        .filter(SgpaCgpa.cgpa.isnot(None))
        .order_by(SgpaCgpa.semester_id.desc(), SgpaCgpa.academic_year.desc())
        .first()
    )
    return float(row.cgpa) if row and row.cgpa is not None else None


@analytics_bp.route("/api/analytics/student/<path:prn>")
@login_required
def get_student_history(prn):
    prn = (prn or "").strip()
    student = Student.query.filter_by(prn=prn).first()
    if not student:
        return jsonify({"error": "Student not found.", "history": []}), 404

    from flask_login import current_user
    if current_user.role!='ADMIN':
        from student_history_services import history as permitted_history
        data=permitted_history(prn)
        visible=[dict(semester_id=r['semester_id'],academic_year=r['academic_year'],subject_code=r['subject_code'],subject_name=r['subject_name'],
            internal=float(r['internal']) if r['internal'] is not None else None,external=float(r['external']) if r['external'] is not None else None,
            total_marks=float(r['total']) if r['total'] is not None else None,grade=r['grade'],grade_point=float(r['grade_point']) if r['grade_point'] is not None else None,result=r['result']) for r in data['local']]
        return jsonify(dict(student=dict(prn=student.prn,name=student.name),history=visible,semester_summaries=[],
            total_backlogs=sum(r['result']=='FAIL' for r in visible),pending_subjects=sum(r['result']=='PENDING' for r in visible),
            latest_sgpa=None,cgpa='PENDING',eligibility='Progression is withheld in teacher scope.',eligibility_status='Withheld'))
    history, semester_summaries = _student_history(prn)
    total_backlogs = sum(1 for row in history if row.get("result") == "FAIL")
    pending_subjects = sum(1 for row in history if row.get("result") == "PENDING")

    upto_sem = max((s["semester_id"] for s in semester_summaries), default=None)
    cgpa = _latest_cgpa(prn, upto_semester_id=upto_sem)
    from completion_models import ProgressionDecision
    approved=ProgressionDecision.query.filter_by(prn=prn).order_by(ProgressionDecision.created_at.desc()).first()
    eligibility=dict(status=approved.decision if approved else 'Review pending',message=(
        f'Administrator-approved {approved.decision.lower()} for Semester {approved.semester_id}, {approved.academic_year}.'
        if approved else 'Progression requires a verified institution policy and administrator approval.'))

    latest_sgpa = None
    if semester_summaries:
        latest = sorted(semester_summaries, key=lambda x: x["semester_id"])[-1]
        latest_sgpa = latest.get("sgpa")

    return jsonify({
        "student": {
            "prn": student.prn,
            "name": student.name,
            "division": student.division or "",
            "batch": student.batch or "",
        },
        "history": history,
        "semester_summaries": semester_summaries,
        "total_backlogs": total_backlogs,
        "pending_subjects": pending_subjects,
        "latest_sgpa": latest_sgpa,
        "cgpa": cgpa if cgpa is not None else "PENDING",
        "eligibility": eligibility["message"],
        "eligibility_status": eligibility["status"],
    })
