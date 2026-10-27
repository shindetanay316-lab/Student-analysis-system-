"""Add the parser's source-metadata table without seeding academic records.

Run while the local application is stopped. Existing SQLite databases are
backed up through SQLite's backup API (including committed WAL content).
"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def main():
    from app import app
    from models import db
    from result_data.parsers import DBATUCrystalReportParser
    from sqlalchemy import inspect

    with app.app_context():
        engine = db.engine
        if engine.url.get_backend_name() == 'sqlite':
            name = engine.url.database
            if name and name != ':memory:' and Path(name).is_file():
                target = Path(app.root_path) / 'backups' / 'parser_update'
                target.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
                backup = target / f'database_before_parser_{stamp}.db'
                with sqlite3.connect(name) as source, sqlite3.connect(backup) as destination:
                    source.backup(destination)
                print(f'Database backup: {backup}')
        db.create_all()
        if 'result_source_data' not in inspect(engine).get_table_names():
            raise RuntimeError('The parser metadata table could not be created.')
    print(f'Parser {DBATUCrystalReportParser.VERSION} is ready. Existing academic records were preserved.')


if __name__ == '__main__':
    main()
