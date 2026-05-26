from models import db, Student, Subject, TheoryMarks, Enrollment


def build_internal_data(
    subject_code,
    semester_id,
    academic_year
):

    subj = Subject.query.get(subject_code)

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

    marks = TheoryMarks.query.filter_by(
        subject_code=subject_code,
        academic_year=academic_year
    ).all()

    lookup = {
        m.prn: m for m in marks
    }

    data = []

    for sr, stu in enumerate(students, 1):

        m = lookup.get(stu.prn)

        ct1 = float(m.ct1 or 0) if m else 0
        ct2 = float(m.ct2 or 0) if m else 0
        assignment = float(m.assignment or 0) if m else 0
        midsem = float(m.midsem or 0) if m else 0

        best_ct = max(ct1, ct2)
        ca = best_ct + assignment
        internal = ca + midsem

        data.append({
            'sr': sr,
            'prn': stu.prn,
            'name': stu.name,
            'ct1': ct1,
            'ct2': ct2,
            'best_ct': best_ct,
            'assignment': assignment,
            'ca': ca,
            'midsem': midsem,
            'internal': internal
        })

    meta = {
        'subject_code': subj.subject_code,
        'subject_name': subj.subject_name,
        'semester_id': semester_id,
        'academic_year': academic_year
    }

    return data, meta
