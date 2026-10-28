"""Back up the configured database and add the remaining academic workflows."""
from upgrade_teacher_access import backup_database


def main():
    from app import app
    from models import db, Student, Semester, Enrollment
    from completion_models import StudentTerm
    with app.app_context():
        required={'completion.term_records','completion.assessment_list','completion.progression_page','completion.master_export',
            'academic.student_list','curriculum.index','attendance.attendance_page'}
        if not required.issubset(app.view_functions):
            raise RuntimeError('Required updated routes did not load. No database migration was applied.')
        backup_database(db.engine,app.root_path)
        db.create_all()
        added=0
        rows=db.session.query(Enrollment.prn,Enrollment.semester_id,Enrollment.academic_year).join(Student).join(
            Semester,db.and_(Semester.semester_id==Enrollment.semester_id,Semester.academic_year==Enrollment.academic_year)).distinct().all()
        existing={(r.prn,r.semester_id,r.academic_year) for r in StudentTerm.query.all()}
        for prn,semester,year in rows:
            if (prn,semester,year) in existing:
                continue
            student=db.session.get(Student,prn)
            db.session.add(StudentTerm(prn=prn,semester_id=semester,academic_year=year,division=student.division,batch=student.batch,origin='LEGACY_SNAPSHOT'))
            added+=1
        db.session.commit()
        print(f'Created {added} missing term placements from existing enrollment/defaults, labelled Legacy snapshot for administrator review.')
    print('ACADPULSE complete academic workflows are ready.')
    print('Existing accounts, identities, marks, attendance, curricula, source documents and university reports were preserved.')
    print('New menus: Semester student records; Admissions awaiting PRN; Assessment rules and marks; Backlogs and progression; Department master workbook.')


if __name__=='__main__':
    main()
