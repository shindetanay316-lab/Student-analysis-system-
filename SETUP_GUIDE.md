# Installation and Setup Guide

## 1. Requirements

- Windows 10/11, macOS, or Linux
- Python 3.11 or 3.12
- Internet access for the first dependency installation
- No separate database server is required for local use; SQLite is the default

## 2. Extract and open the project

Extract the ZIP, open a terminal inside the extracted project folder, and confirm:

```bash
python --version
```

On Windows, `py --version` may be used instead.

## 3. Automatic setup

### Windows

Double-click `setup_windows.bat`, or run:

```bat
setup_windows.bat
```

### macOS/Linux

```bash
chmod +x setup_unix.sh
./setup_unix.sh
```

The script creates `.venv`, installs dependencies, copies `.env.example` to `.env`, creates all database tables, and creates initial login accounts when they do not already exist.

## 4. Manual setup alternative

### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python seed.py
python app.py
```

If PowerShell blocks activation, either run `Set-ExecutionPolicy -Scope Process Bypass` for that terminal or call `.venv\Scripts\python.exe` directly.

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python seed.py
python app.py
```

## 5. Configure `.env`

For local testing, the copied file works with SQLite. Before sharing or deployment:

1. Replace `SECRET_KEY` with a long random value.
2. Replace `ADMIN_PASSWORD` and `TEACHER_PASSWORD` before the first `python seed.py` run.
3. Set the current academic year and semester.
4. Keep `FLASK_DEBUG=0` except during local debugging.

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The default SQLite file is created at `instance/student_analysis.db`.

## 6. Start and use the application

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

New local database credentials (unless changed before seeding):

- Admin: `admin` / `admin123`
- Teacher: `teacher` / `teacher123`

Change these defaults before real use. Running `seed.py` again does not overwrite the password of an existing user. To change an existing password securely, run:

```bash
python set_user_password.py admin
python set_user_password.py teacher
```

After login:

1. Confirm the active semester on **Overview**.
2. Use **Administration** to verify subjects, electives, divisions, and batches.
3. Record internal, external, lab, and attendance data from **Workspace**.
4. Open **PDF imports** under **University results**.
5. Select **Upload PDF** and upload one text-based DBATU result report for one branch and one semester. Parser 2.0 detects each page's subjects and assessments, including short/wrapped codes, alternate electives, office records and optional summary columns.
6. Extract the PDF, review validation findings, and correct any extracted value with a reason.
7. Re-run validation and confirm the dataset.
8. Open **Result analysis** or export Excel/CSV/JSON.

The interface displays the same left navigation, college crest, account, academic year, and semester context across the academic and university-result workflows.

## 7. Use MySQL instead of SQLite (optional)

Create a database, then set this in `.env`:

```dotenv
DATABASE_URL=mysql+pymysql://USER:PASSWORD@localhost/ece_sms
```

Then run:

```bash
python seed.py
```

For an older corrected-project database that has not received its included migration, also run:

```bash
mysql -u USER -p ece_sms < migrations/001_internal_marks_submissions.sql
```

Do not run that SQL twice if the table/columns already exist.

## 8. Use PostgreSQL (optional)

Set:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

Then run `python seed.py`. PostgreSQL is optional; it is not required for local use.

## 9. Existing database upgrade

Back up the database first, replace the application files, install the updated requirements, then run:

```bash
python seed.py
```

`db.create_all()` creates the new `result_*` tables without deleting existing marks, students, subjects, attendance, or users. Existing user passwords are preserved.

## 10. Production start

Set a strong `SECRET_KEY`, use MySQL/PostgreSQL or a backed-up persistent SQLite volume, keep debug disabled, and run:

```bash
gunicorn --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:8000 app:app
```

Uploaded result PDFs and the database must be stored on persistent storage. Back up both regularly.

## 11. Troubleshooting

- **`python` not found:** install Python 3.11/3.12 and enable “Add Python to PATH”.
- **Activation is blocked on Windows:** use `.venv\Scripts\python.exe app.py` directly.
- **Database connection refused:** remove `DATABASE_URL` to use SQLite, or verify the MySQL/PostgreSQL service and credentials.
- **PDF extraction failed:** confirm the PDF contains selectable text and is a DBATU Crystal Report. The parser detects variable subject/assessment columns and retains optional summary fields. Scanned PDFs require OCR and a different report family may require another adapter.
- **Duplicate PDF:** the source hash already exists; open the existing import from Import History.
- **File too large:** increase `MAX_UPLOAD_MB` in `.env` and restart the server.
- **Port 5000 is busy:** run `flask --app app run --port 5001` and open the new port.
