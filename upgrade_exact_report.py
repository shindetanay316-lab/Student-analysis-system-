"""Back up the database and recover only grades printed in retained sources."""
from datetime import datetime,timezone
from pathlib import Path
import sqlite3


def main():
    from app import app
    from models import db
    from result_data.models import ImportJob
    from result_data.services.grade_repair_service import repair_missing_grades
    with app.app_context():
        engine=db.engine
        if engine.url.get_backend_name()=='sqlite' and engine.url.database and Path(engine.url.database).is_file():
            folder=Path(app.root_path)/'backups'/'exact_report';folder.mkdir(parents=True,exist_ok=True)
            backup=folder/('database_before_exact_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.db')
            with sqlite3.connect(engine.url.database) as source,sqlite3.connect(backup) as target:source.backup(target)
            print('Database backup:',backup)
        db.create_all()
        total=0;skipped=0
        for job in db.session.scalars(db.select(ImportJob).where(ImportJob.report.has())).all():
            try:
                recovered=repair_missing_grades(job,app.config['RESULT_DATA_UPLOAD_FOLDER'])
                db.session.commit();total+=recovered
            except Exception:
                db.session.rollback();skipped+=1
        print(f'Recovered {total} printed grades. Skipped imports requiring manual review: {skipped}.')
        print('Corrected imports return to review; existing manual corrections are preserved.')
        print('Exact college report format and explicit Excel grade statuses are ready.')


if __name__=='__main__':main()
