"""Add approved university links and student portfolios without rewriting records."""
from upgrade_teacher_access import backup_database


def main():
    from app import app
    from models import db
    with app.app_context():
        required = {'academic.linking', 'academic.student_list', 'curriculum.index', 'attendance.attendance_page'}
        if not required.issubset(app.view_functions):
            raise RuntimeError('The application did not load the required updated routes. No database migration was applied.')
        backup_database(db.engine, app.root_path)
        db.create_all()
    print('University linking and student history are ready.')
    print('Existing accounts, student identities, marks, attendance, curricula and university reports were preserved.')
    print('Admin: Link university results. Staff: Student history and profiles.')


if __name__ == '__main__':
    main()
