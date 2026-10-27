"""Add lab/ESE acceptance and correction history; preserve earlier data."""
from upgrade_teacher_access import backup_database


def main():
    from app import app
    from models import db
    with app.app_context():
        backup_database(db.engine,app.root_path)
        db.create_all()
    print('Lab/external preview and administrator-approved corrections are ready.')
    print('Existing marks, acceptances, student rosters, teacher assignments and university publications were preserved.')


if __name__=='__main__':main()
