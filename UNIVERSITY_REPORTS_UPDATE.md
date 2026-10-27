# University reports and dashboard update

This patch updates the existing StudentAnalysis installation after the Parser
2.0 update. It does not create another project or replace the working parser.

## Install on Windows

1. Stop the running application with Ctrl+C.
2. Extract Acadpulse_Reports_Dashboard_Update.zip into a separate new folder.
3. Open PowerShell inside the extracted folder containing install_reports_update.py.
4. Run (adjust --project if you installed the application elsewhere):

```powershell
& "$env:USERPROFILE\Projects\StudentAnalysis\.venv\Scripts\python.exe" .\install_reports_update.py --project "$env:USERPROFILE\Projects\StudentAnalysis"
```

The installer verifies the update files, backs up the affected original files,
backs up the SQLite database, copies the update and creates one additive table
for report settings. It does not seed data, recalculate stored marks, change
.env, reset accounts or re-extract existing imports. MySQL/PostgreSQL use the
configured connection; the automatic database backup is specific to SQLite.

5. Start your existing project:

```powershell
cd "$env:USERPROFILE\Projects\StudentAnalysis"
.\.venv\Scripts\python.exe app.py
```

6. Refresh the browser with Ctrl+F5 to load the updated chart script.
7. Open University results > Result analysis for an existing imported PDF.

## Report and Excel downloads

Use PDF report or Export Excel on the analysis page. The import details page
also has these download buttons. Open Report settings to edit the report date,
subject faculty names and the four signatory names for this import. Empty
names remain blank. Settings are retained when the same import is re-extracted.

The report contains Overall Result, Subject-wise Result, Top 10 Students,
Failed Students, and All Students Results, with the existing college logos,
semester/session/type, date, signature spaces and page numbers.

The main Excel workbook contains Result Summary, Student Results, Subject
Analysis, Top 10, Failed Students, and Charts. The all-students grade sheet is
included in the workbook.

All student tables begin Sr. No., PRN, Student Name. Subject matrix cells hold
grades only; names appear above codes in the headers. Failed rows are red.
Unprinted grades appear as a dash; electives not printed for a student are
blank. PRNs are stored as literal text, preserving every digit and leading zero.
Student sheets have filters, frozen identifying columns/headings and print
settings. PDF matrix pages use landscape A3 for wide curricula, A4 otherwise;
more than twelve subjects are split into panels with student identities and
result columns repeated. Other PDF sections use landscape A4.

A separate Detailed data workbook keeps the original marks/components,
validation findings, optional source summary values and correction history.
The existing CSV and JSON data exports remain available.

## Dashboard and chart filters

- Top performers displays up to ten passed students with reported SGPA.
- Equal SGPA shares a rank. Display order within a tie uses reported total
  marks, then PRN. Exactly ten students are shown when at least ten qualify.
- Highest SGPA shows all students tied for the highest eligible reported SGPA.
- Students requiring attention has been removed.
- Subject performance uses full subject names.
- Click a result status, SGPA range, grade, validation status, subject bar or
  assessment component to open its matching records.
- Subject pass-rate bars open passed records. Average-mark bars open records
  with numeric marks that contributed to that average.
- Filters have matching counts, a search field, pagination and Clear filter.
  Subject filters also allow All/Passed/Failed. Student names open their review.
- More chart filters provides keyboard-accessible dropdowns for every chart.
- Grade/component charts count student-subject records. A student may therefore
  appear several times; the list separately shows the distinct student count.
- Chart.js is bundled locally, so chart rendering does not require its CDN.

## Meaning of the numbers

Faculty reports and analysis use reviewed university values, not a recalculated
grade or SGPA that disagrees with the university record. Calculations and
validation warnings remain separately available for review.

Overall pass percentage is Passed / (Passed + Failed) x 100. Withheld,
cancelled and other undeclared outcomes are separate. Subject aggregates use
records of students whose declared result is PASS or FAIL. Unknown/audit
grades do not become inferred passes or failures. A zero denominator stays
unavailable, rather than displaying a misleading zero-percent pass rate.

Unconfirmed imports can be inspected/exported but are visibly marked
PROVISIONAL. A confirmed dataset is marked CONFIRMED. Installing this update
never changes an existing confirmation or correction.

## Verification

See REPORTS_VERIFICATION.md. The previews folder contains an anonymized layout
example, not real student data or a database. Application dependencies remain
those already installed in requirements.txt.

Optional Python test command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
