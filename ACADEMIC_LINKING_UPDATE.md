# University linking and student history update

This cumulative update includes the syllabus/curriculum approval and attendance completion update, reviewed university-result linking, and student history with portfolios and Excel/PDF exports. It installs into your existing project.

## Install on Windows

1. Stop the running application with Ctrl+C.
2. Extract `Acadpulse_University_Link_Student_History_Update.zip` into a separate Downloads folder. Extraction alone does not update the project.
3. Open PowerShell in the extracted folder containing `install_academic_update.py`. Paste only these commands, without the `PS C:\...>` prompt:

```powershell
& "$env:USERPROFILE\Projects\StudentAnalysis\.venv\Scripts\python.exe" .\install_academic_update.py --project "$env:USERPROFILE\Projects\StudentAnalysis"
cd "$env:USERPROFILE\Projects\StudentAnalysis"
& .\.venv\Scripts\python.exe .\app.py
```

4. Log in as an administrator and press Ctrl+F5. The sidebar should show **Syllabus and curriculum**, **Link university results**, and **Student history and profiles**. Attendance includes term calendars, timetable management and reviewed uploads.

The installer accepts the latest GitHub build or the previous syllabus/attendance update. It checks package integrity and local file versions before changing files, backs up replaced files, and backs up the configured database before creating missing tables. No new dependencies are required. It preserves `.env`, accounts, uploaded documents and existing records. Unknown local edits cause installation to stop before replacement; compare the named file before retrying. Backups are under the project's `backups` folder.

If menus do not appear, verify that the server was stopped and restarted from the project above. Check:

```powershell
Test-Path .\routes_academic_history.py
Select-String -Path .\app.py -Pattern "register_blueprint\(academic_bp\)"
```

## Link a university result

1. Import a university PDF using **University results > PDF imports**. Review extraction, resolve errors and confirm it. Existing confirmed imports can also be used.
2. Open **Link university results** or **Link to academic records** on the confirmed import.
3. Select the actual teaching academic year for that semester. The examination date does not determine this year, especially for supplementary results.
4. Review the source-to-local subject mappings. A different code or subject name needs a specific mapping reason. Preview the rows.
5. Check PRN, name, teaching year, enrollment, subject and credits. Only matching, valid rows can be selected. Unmatched rows show their reason; configure the real roster or resolve the source/mapping and create a fresh preview. The process does not create guessed student identities, enrollments or subjects.
6. Choose the rows to publish into student history. **Copy ESE** is optional and starts unchecked. Verify the details and confirm. You can publish matching rows now and link the remaining rows later.

Source grades, raw components, totals, printed SGPA, result status, examination session and original PDF are retained with the approval. A manually cleared grade displays REVIEW; missing printed grades display NOT PRINTED. No grade is invented from marks. Repeating confirmation does not duplicate evidence. Later corrections to an extraction can be linked as another evidence version; earlier versions remain visible.

Optional ESE copying fills only an empty compatible local theory ESE for a regular whole examination, with an unambiguous numeric score on the existing 60-mark scale, 20-mark minimum, 100-mark subject total and matching credits. Special, carried-forward, different-attempt, supplementary, lab and grade-only results stay as university history. Existing local ESE values, locked absences and accepted marks are preserved. Copied ESE is locked and uses the existing reviewed correction workflow and calculations. Local internal component marks are preserved. The original accepted PDF remains downloadable in the subject evidence screen.

## Student history and portfolios

Open **Student history and profiles**, search by PRN/name or filter by actual admission year, then open a student. It combines local semester results, local calculated SGPA/CGPA, approved university evidence, attendance, approved curriculum enrollment and correction history. Printed university SGPA is shown separately from local calculated results. Missing results remain Pending, and attendance does not treat pending sessions as absences.

Administrators can record interests, skills, projects, certifications, achievements and goals. These are recorded portfolio notes, not verified credentials. Changes are audited and stale edits are rejected. Teachers can view/export only students and exact subject/semester/year contexts covered by their active assignments; whole-programme CGPA and full-class source PDFs are withheld from teacher views.

**Download Excel** includes six sheets: Student Profile, Local Results, University Evidence, Attendance, Curriculum and Corrections. Student data tables start with **Sr. No., PRN, Student Name**. **Download PDF** provides a printable summary; Excel contains detailed printed components and source metadata. The existing university result analysis PDF template and its workbook remain available in University results.

## Acceptance test and feedback

1. Installation: all three new/previous menus appear after restart.
2. Previous features: open an approved curriculum, an attendance summary and an existing marks/report screen. Existing records should be present.
3. Confirm a representative university import, select its real teaching year and preview linking. Verify matching and unmatched reasons against the PDF and enrollment roster.
4. Publish one matching row with Copy ESE unchecked. The student's university history should gain evidence; local ESE should stay unchanged.
5. If you have a compatible empty theory ESE, preview again and explicitly copy one eligible result. Check the locked ESE, original PDF and existing internal component values. Try an existing-mark row; copying should be unavailable.
6. Reopen and confirm the same approval. Evidence must not duplicate. Change a source or target after another preview; confirming that stale preview should require a fresh preview.
7. Check one grade-only/supplementary result, one special or missing grade and a reported SGPA. Compare screen and Excel with the source PDF.
8. Open student history; export Excel and PDF. Check sheet names, first three table columns, grades, pending values and attendance counts.
9. Save portfolio notes and verify they remain after reload. Log in as a teacher: only assigned contexts should be visible, with no admin linking or portfolio editing.

Report each numbered check as PASS/FAIL. For a failure, provide the role, screen/URL, PRN or anonymized example, selected teaching year/semester/subject, expected versus actual result, and the terminal traceback if one appears. Redact passwords and personal data before sharing.

Release verification: 174 automated Python tests and both JavaScript behavior checks passed. Disposable installation tests covered the GitHub base and the prior syllabus/attendance build, repeated installation, Windows line endings, local-edit rejection, preservation of all existing database rows, and installed route/export workflows. The student PDF was rendered and visually checked. Browser click-through acceptance on your Windows device remains the numbered workflow above.

## Scope still remaining

This update does not implement term-specific roll/division/batch history or late-PRN identities, a configurable assessment-rule engine, approved promotion/best-attempt/backlog rules, or a department-wide master workbook. University evidence is not used to infer promotion or silently replace local calculated results. The existing syllabus/attendance guide, `SYLLABUS_ATTENDANCE_UPDATE.md`, describes that included phase and its workflow.
