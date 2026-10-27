"""Back up and add review/acceptance tables without rewriting academic records."""
from upgrade_teacher_access import backup_database


def main():
    from app import app
    from models import db
    with app.app_context():
        backup_database(db.engine,app.root_path)
        db.create_all()
    print('Roster review and internal marks preview are ready. Existing accounts, assignments, student records and marks were preserved.')
    print('Admin: Student rosters. Teacher: My Subjects > Marks or Analysis.')


if __name__=='__main__':main()
