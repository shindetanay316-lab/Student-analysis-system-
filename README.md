# ECE Academic Records

This Flask application combines the corrected ECE Student Analysis System with the Result Data System from `shindetanay316-lab/result-data-system`.

## Included modules

- Student, semester, curriculum subject, elective, division, and batch management
- Internal, external, and lab/project marks workflows
- Attendance/timetable workflows
- Student and department analytics
- Excel/PDF academic reports
- University result PDF upload and extraction
- Validation, student-level review, correction audit, and confirmation
- Result PDF analysis dashboard
- Branded Excel plus CSV/JSON result exports

The modules share one professional interface, one login, and one configured database. Result PDF records are stored in dedicated `result_*` tables and source files are stored under `uploads/result_data`.

## Quick start

Use `setup_windows.bat` on Windows or `./setup_unix.sh` on macOS/Linux. Then run:

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

SQLite is used automatically when `DATABASE_URL` is not set, so MySQL/PostgreSQL installation is optional.

## Documentation

- Full installation, database, upgrade, production, and usage instructions: `SETUP_GUIDE.md`
- Complete integration and feature changes: `INTEGRATION_CHANGES.md`
- Confirmed faculty rules and decisions still required: `FACULTY_DECISIONS.md`
- Automated and sample-PDF verification results: `TEST_REPORT.md`
- Earlier corrected-project fixes: `FIXES.md`

## Tests

```bash
python -m unittest discover -v
```

The workflow suite uses a temporary SQLite database and does not modify the configured application database.

## Important parser note

Parser version 1.1.0 supports text-based DBATU Crystal Reports with the known one- or two-ESE-row layouts, optional internal rows, variable subject/student counts, and wrapped subject names. Scanned/image-only PDFs and materially different report families need OCR or an additional parser adapter.
