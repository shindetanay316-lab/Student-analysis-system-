"""Back up the current database and add scoped teacher access without replacing academic records."""
from datetime import datetime,timezone
from pathlib import Path
import os
import shutil
import sqlite3
import subprocess


def backup_database(engine,root):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    folder=Path(root)/'backups'/'teacher_access';folder.mkdir(parents=True,exist_ok=True)
    backend=engine.url.get_backend_name()
    if backend=='sqlite':
        name=engine.url.database
        if name and name!=':memory:' and Path(name).is_file():
            path=folder/f'database_before_teacher_access_{stamp}.db'
            with sqlite3.connect(name) as source,sqlite3.connect(path) as target:source.backup(target)
            print('Database backup:',path)
    elif backend=='postgresql':
        executable=shutil.which('pg_dump')
        if not executable and os.name=='nt':
            candidates=sorted((Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'PostgreSQL').glob('*/bin/pg_dump.exe'),reverse=True)
            executable=str(candidates[0]) if candidates else None
        if not executable:raise RuntimeError('PostgreSQL backup requires pg_dump. Add the PostgreSQL bin folder to PATH, then run this installer again.')
        env=os.environ.copy();url=engine.url
        for key,value in [('PGHOST',url.host),('PGPORT',url.port),('PGUSER',url.username),('PGPASSWORD',url.password),('PGDATABASE',url.database)]:
            if value is not None:env[key]=str(value)
        path=folder/f'database_before_teacher_access_{stamp}.dump'
        subprocess.run([executable,'--format=custom','--no-password','--file',str(path)],env=env,check=True)
        print('Database backup:',path)
    else:
        raise RuntimeError('This update supports SQLite and PostgreSQL. No database changes were applied.')


def migrate_legacy_assignments():
    from models import db,User,Subject,Semester
    from teaching_models import TeachingAssignment,StaffAccessAudit
    count=0;unresolved=[]
    for teacher in User.query.filter_by(role='TEACHER').all():
        for code in sorted(set(teacher.get_assigned_subjects())):
            subject=db.session.get(Subject,code)
            if not subject or not subject.is_active or (subject.is_elective and not subject.parent_subject_code):
                unresolved.append((teacher.username,code));continue
            term=Semester.query.filter_by(semester_id=subject.semester_id,is_active=True).first()
            if term is None:term=Semester.query.filter_by(semester_id=subject.semester_id).order_by(Semester.academic_year.desc()).first()
            if term is None:
                unresolved.append((teacher.username,code));continue
            fields={'teacher_id':teacher.user_id,'subject_code':code,'semester_id':term.semester_id,'academic_year':term.academic_year}
            if TeachingAssignment.query.filter_by(**fields).first():continue
            db.session.add(TeachingAssignment(**fields))
            db.session.add(StaffAccessAudit(user_id=teacher.user_id,action='LEGACY_ASSIGNMENT_MIGRATED',
                details={'subject_code':code,'semester_id':term.semester_id,'academic_year':term.academic_year}))
            count+=1
    db.session.commit()
    return count,unresolved


def main():
    from app import app
    from models import db
    with app.app_context():
        backup_database(db.engine,app.root_path)
        db.create_all()
        count,unresolved=migrate_legacy_assignments()
        print(f'Migrated {count} legacy subject assignments to the active or latest matching academic term.')
        for username,code in unresolved:print(f'Admin review needed: teacher {username}, subject {code}. No assignment was granted.')
    print('Teacher access update ready. Existing accounts, passwords, students, marks, attendance and university reports were preserved.')
    print('Admin: open Teachers and assignments. Teachers: sign in to My Subjects.')


if __name__=='__main__':main()
