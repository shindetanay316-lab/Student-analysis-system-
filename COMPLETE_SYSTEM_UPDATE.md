# ACADPULSE complete academic workflow update

This package brings the existing project up to date with term-specific student placement, admissions awaiting PRN, configurable assessments, reviewed attempts/backlogs/progression, and a department master Excel workbook. Earlier parser, university report, dashboard, teacher assignment, marks review/correction, syllabus, curriculum, attendance and student history updates are included.

## Installation on your laptop

1. Stop the running server with Ctrl+C.
2. Extract `Acadpulse_Complete_System_Update.zip` into a separate Downloads folder. Do not replace or delete your existing project folder. Extraction alone does not install the update.
3. Open PowerShell in the extracted folder containing `install_complete_update.py`. Paste these commands without a `PS C:\...>` prompt:

```powershell
& "$env:USERPROFILE\Projects\StudentAnalysis\.venv\Scripts\python.exe" .\install_complete_update.py --project "$env:USERPROFILE\Projects\StudentAnalysis"
cd "$env:USERPROFILE\Projects\StudentAnalysis"
& .\.venv\Scripts\python.exe .\app.py
```

4. Log in as ADMIN and press Ctrl+F5. New sidebar menus: **Semester student records**, **Admissions awaiting PRN**, **Assessment rules and marks**, **Backlogs and progression**, **Department master workbook**.

The installer accepts the GitHub build `e9954d1`, the syllabus/attendance update and the university-linking/student-history update. It verifies the package and recognized local file versions before replacement, backs up replaced files, backs up the configured database, then creates missing tables. Existing accounts, passwords, students, marks, attendance, source documents, university imports, curricula and `.env` are preserved. No additional dependencies are needed. Unknown edits stop installation before replacement so you can compare the named file. Backups are under the project's `backups` folder.

`codebase` contains the complete application source, without your database, `.env`, uploads, virtual environment or Git history. The installer applies the cumulative changed files to the existing project; it does not create a second working database. Use the installer for your current installation.

If a menu is missing after installation, stop the old server, restart from the exact project path above and refresh. Verify:

```powershell
Test-Path .\routes_completion.py
Select-String -Path .\app.py -Pattern "register_blueprint\(completion_bp\)"
```

## 1. Semester student records

Select an existing semester/year and optionally search a cohort, name or PRN. Edit each selected student's roll number, division and practical batch, preview, then confirm. For larger groups download/edit the placement CSV and upload it for review. PRNs and names must match real profiles. Roll numbers are unique within a division and teaching term; reviewed swaps are supported.

These changes affect only that semester/year. Admission year, identity, older placements and marks are preserved. Marks, attendance, department reports and assignment roster previews use the selected term's placement. Student history and its exports show placement history. The previous Divisions and batches URL now opens the term workflow.

On first installation, existing enrollment contexts receive a **Legacy snapshot** of the old global division/batch. This preserves the available information; it does not recover historical placements the old system never stored. Review those snapshots against the college roster. New subject enrollment creates a labelled default placement only when that term has no placement yet.

## 2. Admissions awaiting PRN

Record the college admission number, name, actual admission year and initial teaching placement. This admission remains separate from academic marks and can be corrected before activation. When the real university PRN arrives, enter it, preview and verify activation. The system rejects a PRN already used by another student; it never guesses a PRN or merges identities automatically. The admission retains its original admission year and activation evidence.

After activation, confirm the student's subject enrollment using **Student rosters** or the approved curriculum roster. Marks and attendance entry require activation and actual enrollment. This release supports pre-PRN admission registration, not assessment entry against a temporary PRN.

## 3. Configurable assessment rules and marks

Administrator setup:

1. Open **Assessment rules and marks > Create an assessment policy**.
2. Choose the actual subject, semester and teaching year. Enter a title and the approved syllabus/ordinance page or clause.
3. Edit the prefilled definition to match that source. Components have independent codes, labels, maxima, optional passing minima and optional `absence_fails` settings. Every component belongs to one group. Groups use SUM or BEST_N, have an output scale and optional minimum, and contribute to Internal or External. Grade thresholds are percentages of the total scale.
4. Save the draft. Review the human-readable component, group, passing and grade tables. Correct the draft if needed, then approve it.

Example BEST_N groups require equal raw component scales. Contributions are scaled using the selected raw maxima and rounded to two decimals before summing. Zero is a numeric mark. Blank means Pending. AB means recorded absence; the component's absence flag and passing minima determine failure. Failure is FF / 0. Grade bands are used only after all passing conditions are met. The prefilled example mirrors the existing local grade thresholds; it is a starting definition to verify against your institution's source, not an automatic interpretation of a syllabus.

An approved definition is immutable. A new policy cannot replace rules in a term that already has legacy marks. Existing marks continue using their existing calculations. Configure rules before marks are entered for a new subject/term. Approved curriculum/linked-result/policy subject definitions are protected from destructive edits.

Teacher workflow:

1. Log in with the assigned teacher account. Open the subject from **My Subjects** or **Assessment rules and marks**. Legacy marks links redirect to the configured entry screen for a configured subject.
2. Download the marks Excel workbook. PRN and student name follow Sr. No.; component columns match the approved policy. Its hidden metadata binds it to the exact policy/subject/semester/year. A CSV UTF-8 alternative is also available through the template URL's `?format=csv` option.
3. Enter numeric marks, AB, or leave a component pending. Preserve the identity and metadata. Upload the `.xlsx` workbook for review. Formulas, invalid values, wrong-context files, unknown PRNs and duplicate students are rejected.
4. Review and confirm the initial submission. It updates configured results, local SGPA calculations, history and analytics. Legacy component rows are not rewritten.
5. To change submitted scores, download the current workbook, edit the values and provide a specific reason. The preview becomes an administrator approval request. Teachers cannot approve their own submitted-score changes. The original files, earlier values, reason and approver remain in the history.

The original fixed-format internal/lab reports remain for legacy courses. Configured courses use their policy screen, history export and master workbook for their variable components. Department visual averages normalize configured course totals to percentages so different total scales are comparable.

## 4. Reviewed attempts, backlogs and progression

1. An administrator approves a progression policy using the institution's actual source clause. Specify the source semester, all semesters the rule requires reviewing, maximum backlog subjects/credits and minimum earned credit percentage. Required semesters must include the source semester. Missing required enrollment/evidence blocks progression.
2. Enter the student's PRN, select that policy and the source teaching year, then review attempts. Complete local results and eligible approved university evidence are offered separately. Printed cancelled/withheld/ambiguous grades are not converted into guessed outcomes. Superseded revisions of the same university source are excluded from new selections.
3. The highest passing grade-point result is suggested for each course. Reviewers can explicitly choose another eligible result with a recorded reason. The system does not combine different attempts' raw components or rewrite a university PDF.
4. Select the actual next teaching year, enter the review reason, then preview. Verify the student's complete course requirements and admission route as well as the selected attempts.
5. Confirm the proposed PROMOTED, HOLD or GRADUATED decision. Missing evidence remains Pending and cannot become a pass. Backlog counts and credits come from the explicitly selected attempts. A HOLD can be reviewed again after results are completed. Final progression approvals retain their snapshots and cannot be duplicated for the same source term.

Promotion creates a next-semester placement when needed, with its roll/division/batch left unassigned. Then assign that placement and confirm the next curriculum roster, including electives. It does not invent next-term enrollment or change admission year. Graduation requires zero backlog limits, 100% earned credits within the policy's reviewed scope, and explicit verification of audit/non-credit requirements and institutional clearances.

Approved course selections are distinct from local calculated SGPA/CGPA and printed university SGPA. All earlier attempts and approval snapshots remain available. Later score corrections do not erase an earlier progression approval; administrators can see the original evidence on which it was based.

## 5. Department master Excel workbook

Select a real teaching semester/year, optionally filter by actual admission cohort/division/practical batch, and download one workbook. Up to 5,000 matching enrolled students can be exported at once.

The 12 sheets are **Summary**, **Students**, **Local Results**, **University Evidence**, **Attendance**, **Curriculum**, **Corrections**, **Approved Outcomes**, **Progression**, **Assessment Rules**, **Assessment Components** and **Portfolios**. Student tables start with **Sr. No., PRN, Student Name**. Identity values remain text, zero remains numeric, printed grades retain source meaning, and pending/absent states stay explicit. Summary counts are Excel formulas that recalculate when opened. Attendance percentages use Present / (Present + Absent); pending, leave and official duty do not become absences. Long portfolio notes continue across numbered parts.

University evidence includes the source PDF name, hash and printed components. Configured components include the approved assessment scale, actual score/absence/pending state and revision. Approved outcomes and progression remain separately labelled. Teachers cannot download the department master workbook; assigned-subject history exports remain available to them.

## Acceptance test: send PASS/FAIL for each item

1. **Install/restart:** new menus appear; existing students, marks, approved curricula and attendance are still present.
2. **Historical placement:** change one student's division/batch in one term. Confirm that another term and actual admission year stay unchanged; verify the selected-term attendance/marks filters and student history.
3. **Roll numbers:** try a duplicate within one division/term; it should be rejected. Check the same roll in a different division or term is allowed.
4. **Pending admission:** record one admission, correct its details if necessary, preview real PRN activation and confirm. Ensure no academic student was created before confirmation; enroll after activation. Try an already used PRN; it should be blocked.
5. **Assessment policy:** use a new empty subject/term. Verify the draft against a real syllabus, correct it, approve it, and confirm approved rules cannot be changed. A term with existing legacy marks must reject new rules.
6. **Configured marks:** download Excel, test valid marks, numeric zero, AB and a blank component. Check totals, minima, grade and Pending/FAIL/PASS. Upload a template from another context; it must be rejected.
7. **Teacher permissions/corrections:** the assigned teacher can submit initial scores and request changes; an unassigned teacher cannot access them. Only an administrator approves a correction. Verify the original upload and earlier values remain downloadable/viewable.
8. **Progression HOLD:** use a student with incomplete required results or missing required semester enrollment. The preview should explain HOLD and create no next placement.
9. **Progression approval:** verify a complete student's attempts and institution policy. Confirm once, reopen, and verify there is one final decision and a separate next-semester placement. Set the next placement and confirm curriculum enrollment separately.
10. **Best attempt/backlog:** compare the selected source with the printed PDF/local result; verify backlog subjects and credits. Check all original attempts remain in history.
11. **Master workbook:** verify filters, 12 sheets, first three identity columns, grades, component scores, attendance denominator, source evidence and summary counts against the app. Check a teacher receives no department-wide export access.
12. **Regression:** check university extraction, exact university analysis PDF/workbook, chart filters/top 10, existing internal/lab/external marks, approved correction workflows, syllabus enrollment and datewise attendance.

For a failure, send the numbered item, role, screen/URL, selected semester/year/subject, expected vs actual result, and the terminal traceback if one appears. Use an anonymized student example and redact passwords/personal data.

Automated tests cover these flows and data-preservation checks; final acceptance with the actual Windows installation and institution-specific policies is still required. Earlier update guides in the source are historical release notes; this guide describes the current cumulative release.

Release checks: the 203-test Python suite passed, with targeted rechecks of the final report/filter changes and both JavaScript behavior checks. All 12 master sheets were rendered for inspection; summary formulas recalculated to the expected counts with no formula errors. The student PDF was rendered and checked. Upgrade tests covered all three supported earlier builds, two installations per build, preservation of existing tables/rows and original workbook/PDF bytes, Windows line endings, unchanged configuration/uploads, rejection of unknown local edits, and application-file rollback after a controlled migration failure. The installed-code integration test covered admission activation, roster approval, policy approval, teacher Excel submission, administrator correction, placement, progression replay, history/PDF and filtered master export.
