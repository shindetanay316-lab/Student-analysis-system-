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
python -m unittest discover -s tests -v
```

The workflow suite uses a temporary SQLite database and does not modify the configured application database.

## University result parser

Parser 2.0 detects subject columns, wrapped codes and assessment rows per page.
It supports the supplied DBATU office/institute reports, Regular/Supply results,
NEP codes, alternate electives, optional assessments and optional summary fields.
It retains raw marks, carried-forward flags, absences, grace annotations, audit
results and attempt sessions. Missing printed values stay unknown for review.

For an existing installation, stop the app and run:

```powershell
.\.venv\Scripts\python.exe upgrade_result_parser.py
```

This backs up an existing SQLite database and creates an additive source-metadata
table. It does not seed/reset subjects, accounts, marks or academic settings.
See `PARSER_UPDATE.md` for installation and verification details.

Scanned/image-only PDFs require OCR first. A different university/report family
may require a separate adapter; successful parsing does not guarantee the source
report's own marks and totals are consistent.

## Faculty reports and interactive result analysis

See `UNIVERSITY_REPORTS_UPDATE.md` for the approved PDF/Excel template, chart
drill-downs and installation. Existing installations should run
`python upgrade_university_reports.py` after copying updated source files.
This creates the additive report-settings table without resetting records.
