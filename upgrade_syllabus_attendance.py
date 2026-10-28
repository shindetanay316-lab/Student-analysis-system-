"""Add syllabus versions and attendance calendars/history without rewriting records."""
from upgrade_teacher_access import backup_database


def main():
    from app import app
    from models import db
    with app.app_context():
        backup_database(db.engine, app.root_path)
        db.create_all()
    print('Syllabus approval and attendance completion are ready.')
    print('Existing students, accounts, assignments, marks, attendance entries and university reports were preserved.')
    print('Admin: Syllabus and curriculum. Attendance: set term dates, holidays and timetable, then upload for review.')


if __name__ == '__main__':
    main()
