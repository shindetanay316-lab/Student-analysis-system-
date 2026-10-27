# University result parser 2.0 update

This updates the existing Student Analysis System based on GitHub main commit
28de4419375ede7b489a8f4f02c5c87b00acd9bf. It does not create a second project.

## Apply the supplied update ZIP on Windows

1. Stop the application with Ctrl+C in its PowerShell window.
2. Extract Acadpulse_Parser_Update.zip into its own folder.
3. Open PowerShell inside the extracted folder that contains install_parser_update.py.
4. Run this command (change the project path if you installed elsewhere):

```powershell
& "$env:USERPROFILE\Projects\StudentAnalysis\.venv\Scripts\python.exe" .\install_parser_update.py --project "$env:USERPROFILE\Projects\StudentAnalysis"
```

The installer verifies the update files, backs up the existing affected files,
backs up an existing SQLite database with SQLite's backup API, copies only the
changed files, and creates the new result_source_data metadata table. It does
not run seed.py, change .env or reset accounts, academic settings or marks.
For MySQL/PostgreSQL, it creates missing tables using the configured connection;
the automatic database backup described above is specific to SQLite.
If an update command fails, original application files are restored.

5. Start the existing project again:

```powershell
cd "$env:USERPROFILE\Projects\StudentAnalysis"
.\.venv\Scripts\python.exe app.py
```

6. Visit http://127.0.0.1:5000 and open University results > PDF imports.
7. Upload a result PDF. For a previously failed upload, open Import history and
   click Extract result data; no duplicate upload is necessary.
8. Review the reported values, validation notes and exports before confirming.

An already extracted report keeps its prior data. Installing an update does not
automatically re-extract or remove corrections from existing imports. A deliberate
re-extraction replaces that import's generated dataset and correction history;
export records you want to retain before doing that.

## What changed

- Automatic extraction now reads the same private folder used by the upload step.
- Exam and EXAMINATION headings, Office Record and Institute Record are accepted.
- Catalogue reconstruction handles short codes, NEP wrapped codes, multi-line
  names and credits split across lines/columns.
- Each page supplies its own subject columns and assessment rows. Alternate
  electives on later pages no longer get forced into the first page's order.
- Optional/new assessments are retained, including distinct repeated ESE rows.
  Omitting an assessment row no longer shifts totals or grades into its place.
- Mark/grade baselines are calibrated from each student block, with the known
  Crystal Reports geometry used only as a fallback for empty/cancelled blocks.
- Plain maximum-only headers are accepted without inventing a passing minimum.
- SGPA, grade points, earned credits and marks are mapped separately from extra
  printed totals/percentages. Optional summary fields survive storage and
  Excel/CSV/JSON export and appear on the student review page.
- Raw carried-forward parentheses, absences, grace values, audit grades,
  cancellations and attempt month/session text are retained.
- Expected result coverage uses the printed columns on each student's page.
- A source | grade stays unknown with a review warning. It is not converted
  into a made-up grade or presented as an extraction failure.

## Limits and data review

The parser is a deterministic layout reader, not a trained machine-learning
model. The supplied PDFs are regression examples, and synthetic variations
exercise additional/missing columns and rows. New PDFs in this DBATU report
family do not require hard-coding their exact subject count or names.

Scanned/image-only PDFs need OCR first. A different university/report family,
vertical pages that split the same student's subjects across several pages, or
an unrecognizable table needs a separate adapter. The parser does not silently
turn unreadable PDFs into successful empty imports or invent missing marks.

Warnings for discrepancies printed in the source remain visible. Semester 4
prints | grades for BTUHV34 and inconsistent printed credit/grade-point maxima;
the actual marks and printed summaries are retained. Calculated values that
need absent grades remain unknown. The old office report does not print a
passing minimum for the 50-mark internship; no threshold is guessed.

## Verification

See PARSER_VERIFICATION.md. Regression fixtures replace student identities;
original student PDFs, databases, uploaded files, passwords and .env are not
included in the update package.

Run all included tests after installation if desired:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
