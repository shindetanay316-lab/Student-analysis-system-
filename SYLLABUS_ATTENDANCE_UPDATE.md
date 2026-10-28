# Syllabus approval and attendance completion

Built on GitHub main `e9954d1`. This update extends the existing Flask project.
No new Python dependencies, database reset, seed command, or fresh project is needed.

## Install on Windows

1. Stop the running application with Ctrl+C.
2. Extract `Acadpulse_Syllabus_Attendance_Update.zip` into a new Downloads folder, outside the project.
3. Open PowerShell in the extracted folder containing `install_syllabus_attendance_update.py`.
4. Run only the command below; do not paste a `PS C:\...>` prompt.

```powershell
& "$env:USERPROFILE\Projects\StudentAnalysis\.venv\Scripts\python.exe" .\install_syllabus_attendance_update.py --project "$env:USERPROFILE\Projects\StudentAnalysis"
```

5. Restart the existing app and press Ctrl+F5 in the browser.

```powershell
cd "$env:USERPROFILE\Projects\StudentAnalysis"
& ".\.venv\Scripts\python.exe" app.py
```

The installer verifies its files, backs up replaced files, backs up the SQLite/PostgreSQL database, and creates six new tables. Existing database rows, `.env`, accounts, teacher assignments, subjects, student profiles, marks, attendance entries, original uploaded workbooks, university results and approved report templates are preserved. Running the installer again is safe. Unexpected local edits to a file being replaced stop installation before changes; check those edits rather than overwriting them blindly.

## Syllabus workflow

1. Sign in as admin. Open **Administration > Syllabus and curriculum**.
2. Enter a descriptive version title, branch/programme, scheme and effective academic year. NEP and MIS share the `NEP/MIS` label. Upload the original syllabus PDF.
3. Review extracted course rows, including semester, A/B/COMMON group, code, full name, course type, credits, L/T/P, printed assessment scheme and choices. Download the retained original for comparison.
4. Uncheck any course you are not ready to approve. Supply verified missing codes and their source/page evidence, or leave those rows excluded. Save the reviewed draft before approving.
5. Check the verification box and approve. Approval freezes the version and makes its new subjects available. Existing definitions are never silently overwritten. Conflicting existing codes stop approval; resolve or exclude those rows. A code cannot represent different semesters/credits/types in the existing global subject catalogue. New revisions keep the old approved version intact.
6. Bind the approved semester/group to the **regular cohort admission year** and **teaching academic year**. A teaching year is independent of the admission year. Binding creates a missing semester/year pair without changing the active semester.
7. Return to the curriculum list and click **Enroll students** beside the binding. Select real profiles and one option per choice group, preview, then confirm. Different choices require separate selections. Only missing enrollments are added.
8. DSE students can explicitly use the matching regular cohort curriculum from semester 3. Their actual admission year remains unchanged. This is curriculum linkage, not automatic promotion.
9. Assign the approved subjects to teachers through **Teachers and assignments**, using the matching teaching year and semester.

The supplied first-year syllabus has 54 extracted course/option rows across Group A and B. The Group B table leaves 27 codes blank; they are not invented or copied across semesters. Full names clipped at a printed table border are completed only when a unique fuller title is printed elsewhere in the same PDF. The second-year syllabus has 27 course/option rows. Open-elective, MDM and IKS buckets stay parent placeholders; actual options need verified definitions before enrollment. Unsupported or image-only syllabus tables remain drafts with manual entry available. Printed CA/MSE/ESE scheme values are retained for review and reference. Marks entry/calculation continues to use the existing approved theory/lab rules; this build does not introduce a configurable assessment-rule engine for different schemes. No OCR, inferred academic policy, or automatic curriculum activation is claimed.

Approved subjects cannot be edited or permanently deleted through the old subject form. Disabling remains available. New syllabus revisions may add compatible definitions; conflicting reuse of an existing global code is deliberately blocked to protect history.

## Attendance workflow

1. Ensure the subject's students are enrolled for the correct teaching term. Use reviewed curriculum enrollment or **Student rosters**. Attendance-only activities use students enrolled in that semester/year, never all cohorts in the database.
2. Open **Attendance**. Select semester, editable academic year and subject. Use `ALL`, a real division such as `A`, or a real practical batch such as `A1`.
3. Admin opens **Term calendar and weekly timetable**, sets term start/end dates and adds holidays/non-teaching days for ALL or a division. No holiday dates or percentage rules are inferred.
4. Download the timetable template. Its metadata reflects the selected term, and the **Subject Codes** sheet lists actual available subjects. Replace sample subject cells, set the real division, keep day/time headers, and upload. A visual timetable replaces the selected division's weekly slots. Other divisions and historical attendance are retained. Overlapping slots for the same group are rejected.
5. Teachers open Attendance from **My Subjects**. Login identifies the teacher; only assigned subject/year/semester contexts can be viewed or changed.
6. Select a date range inside the calendar, then download the attendance sheet. It excludes holidays and cancelled classes and includes separately scheduled makeup classes. Saved entries are prefilled; other-batch cells show N/A.
7. Fill `P` (present), `A` (absent), `L` (leave), or `O` (official duty). For each conducted class, fill every applicable student in the selected scope. Leave the entire future/unconducted column blank. Do not delete student rows or metadata, replace PRNs with numeric cells, or enter formulas in attendance cells.
8. Upload for review. Check PRNs, names, dates, times and changes, then **Confirm and save attendance**. No class/entry is saved during preview. A changed roster, calendar, timetable or saved attendance requires a fresh preview. Previews expire after two hours; replay cannot create duplicates. The original uploaded workbook is retained.
9. Use **Scheduled classes and cancellations** to cancel a class with a reason. Its entries remain for history, while totals refresh immediately. Use **Add makeup / extra class** for a replacement class. Scheduling it does not count attendance; fill and confirm attendance after the class finishes. Makeup classes cannot overlap another class for the same group.
10. Download summary Excel/PDF or the below-75% Excel/PDF. Excel includes **Attendance Summary** and **Session Register**. All student tables begin **Sr. No., PRN, Student Name**. Reports use the selected date range, division and batch.

Percentage preserves the existing calculation: `P / (P + A) * 100`. Leave and official duty are retained separately and excluded from this denominator. No counted classes means **Pending**, never a fake zero-percent defaulter. Future, blank and cancelled sessions do not count. Separate times on the same day are separate classes. Whole-class and batch uploads share the real slot identity. Historical duplicate copies are counted once; conflicting old copies remain pending until reviewed attendance resolves them. The raw copies stay in the session register. Entries with unresolved legacy conflicts are excluded from defaulter lists.

## Quick acceptance test and feedback

Use test students/data first. Send the failing step number, account role, semester/year/subject, division/batch, expected vs actual result, and the visible error or terminal traceback. For file-specific problems, include the original syllabus or generated/filled workbook involved. Do not send `.env`, passwords, or the database.

1. **Syllabus extraction:** upload both supplied syllabi; verify the 54 and 27 rows, A/B/COMMON groups, options, codes, names and credits. Group B missing codes must remain blank/excluded.
2. **Approval:** edit a draft, save, approve; check new subjects appear. Reopen the version: fields are frozen. Create a revision: original remains approved. A conflicting existing code must preserve the original subject and explain the conflict.
3. **Curriculum enrollment:** bind a semester and teaching year, select regular/DSE test profiles, preview, verify no enrollment before confirmation, then confirm. Check actual admission years stay the same. Repeat confirmation: no duplicates. Try another option in an already enrolled choice group: blocked.
4. **Teacher scope:** assign a subject for the teaching year, log in as that teacher, open Attendance from My Subjects. Another subject/year must be forbidden; teacher calendar/syllabus administration must be forbidden.
5. **Calendar/template:** set real term dates, a holiday and two same-day lecture times. Holiday columns must be absent and both real lecture times must be separate columns.
6. **Attendance review/counting:** enter P/A/L/O, leave the next whole column blank, preview, confirm. Check counts and percentages. A partially filled conducted column or future class must be rejected without partial saves. Download again: accepted values are prefilled.
7. **Cancellation/makeup:** cancel a counted lecture, check totals decrease and old entries remain; add a non-overlapping makeup class, verify it is pending, record it after its end time and check the summary.
8. **Reports:** compare screen, summary Excel/PDF and defaulters. Check pending students are not defaulters, row order is correct, and the Excel register shows source session details.
9. **Existing features:** check university PDF extraction, your exact university analysis report/workbook, internal/lab/external marks review, teacher assignments and mark correction decisions still work.

Automated checks exercise the original result/report/marks workflows and the new features. The cloud browser cannot reach the workspace's localhost, so local browser click-through is part of acceptance testing. The migration is checked against a disposable copy with populated existing data; no user database is included in the ZIP.

For a full test run from the project folder:

```powershell
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

## Release verification

- Full Python regression suite: 154 tests.
- Teacher assignment UI and all six result chart click handlers passed their Node checks.
- Both supplied syllabus table layouts checked against their course/option rows; no missing Group B codes invented.
- Installer run twice on a disposable populated copy of GitHub main, including Windows CRLF handling: all 2,216 pre-existing rows and workbook bytes, `.env` and original upload evidence preserved.
- Installed-package end-to-end checks passed for syllabus approval, cohort enrollment, attendance preview/confirmation/replay, cancellation, makeup and Excel/PDF exports.
- Attendance PDF rendered and visually inspected. Web routes and forms rendered in automated tests; browser click-through remains a local acceptance check.
- Existing university parser, exact PDF/workbook exporters, calculation modules and teacher assignment policy files are unchanged.
