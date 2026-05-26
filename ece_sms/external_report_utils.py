from models import db, Student, Subject, TheoryMarks, Enrollment, ExternalMarks

def build_external_data(subject_code, semester_id, academic_year):
    subj = Subject.query.get(subject_code)
    if not subj:
        return [], {}

    students = (
        db.session.query(Student)
        .join(
            Enrollment,
            Enrollment.prn == Student.prn
        )
        .filter(
            Enrollment.subject_code == subject_code,
            Enrollment.semester_id == semester_id,
            Enrollment.academic_year == academic_year
        )
        .order_by(Student.prn)
        .all()
    )

    theory_marks = TheoryMarks.query.filter_by(
        subject_code=subject_code,
        academic_year=academic_year
    ).all()

    external_marks = ExternalMarks.query.filter_by(
        subject_code=subject_code,
        academic_year=academic_year
    ).all()

    tm_lookup = {tm.prn: tm for tm in theory_marks}
    ext_lookup = {ext.prn: ext for ext in external_marks}

    data = []

    for sr, stu in enumerate(students, 1):
        tm = tm_lookup.get(stu.prn)
        ext = ext_lookup.get(stu.prn)

        internal_val = float(tm.internal_total) if (tm and tm.internal_total is not None) else None
        
        external_val = None
        if tm and tm.external is not None:
            external_val = float(tm.external)
        elif ext and ext.external_marks is not None:
            external_val = float(ext.external_marks)

        total_val = float(tm.total_marks) if (tm and tm.total_marks is not None) else None
        grade_val = tm.grade if (tm and tm.grade) else None
        grade_point_val = float(tm.grade_point) if (tm and tm.grade_point is not None) else None
        
        # Determine status
        if external_val is None:
            status_val = "PENDING"
        else:
            status_val = "PASS" if (tm and tm.is_passed) else "FAIL"

        data.append({
            "sr": sr,
            "prn": stu.prn,
            "name": stu.name,
            "internal": internal_val,
            "external": external_val,
            "total": total_val,
            "grade": grade_val or "—",
            "grade_point": grade_point_val,
            "status": status_val
        })

    meta = {
        'subject_code': subj.subject_code,
        'subject_name': subj.subject_name,
        'semester_id': semester_id,
        'academic_year': academic_year,
        'credits': subj.credits
    }

    return data, meta
