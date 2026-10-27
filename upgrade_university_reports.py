"""Create the additive report-settings table; preserve existing data and .env."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def main():
    from app import app
    from models import db
    from sqlalchemy import inspect
    with app.app_context():
        engine=db.engine
        if engine.url.get_backend_name()=='sqlite':
            name=engine.url.database
            if name and name!=':memory:' and Path(name).is_file():
                directory=Path(app.root_path)/'backups'/'university_reports'
                directory.mkdir(parents=True,exist_ok=True)
                stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
                backup=directory/f'database_before_reports_{stamp}.db'
                with sqlite3.connect(name) as source,sqlite3.connect(backup) as target:source.backup(target)
                print(f'Database backup: {backup}')
        db.create_all()
        if 'result_report_settings' not in inspect(engine).get_table_names():
            raise RuntimeError('The report settings table could not be created.')
    print('University reports and dashboard update is ready. Existing records and parser were preserved.')


if __name__=='__main__':main()
