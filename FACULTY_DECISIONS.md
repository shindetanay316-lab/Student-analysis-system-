# Faculty Decisions and Pending Rules

This file records the decisions supplied for the planned academic-history redesign. It prevents unconfirmed institutional rules from being hard-coded.

## Confirmed decisions

| Topic | Confirmed rule | Implementation interpretation |
| --- | --- | --- |
| NEP and MIS | They are the same scheme. | Use the user-facing name **NEP/MIS** and one curriculum-scheme record, not two parallel schemes. |
| Syllabus cycle | The syllabus normally changes every four years. | Create a new immutable curriculum version for each approved revision; never edit a version already used by students, marks, or reports. |
| DSE curriculum | Direct Second Year students follow the regular cohort curriculum from Semester 3. | Retain the student's actual later admission year, connect the student to the matching regular cohort, and create academic history beginning at Semester 3 only. |
| Roll numbers | Roll numbers change by engineering year. | Store roll number on the academic enrollment for that session/year. Do not make roll number globally unique and do not overwrite historical roll numbers. |
| Detained students | Promotion occurs after the failed subject is cleared. | Keep promotion manual until the exact year-wise eligibility rules are supplied. Preserve the failed attempt and store the cleared attempt separately. |
| PDF scope | One university-result PDF will contain only one branch and one semester. | Require one academic context per import. Reject or flag a report if its pages conflict with that context. |
| Previous Result Management data | Do not migrate it yet. | Keep the migration workflow disabled until migration is explicitly approved. No old result data should be deleted or rewritten. |

## Recommended curriculum revision identifier

The institution has not supplied an official revision identifier. Until it does, use a controlled internal code made from the scheme and effective cohort year, for example `NEP_MIS_2026`, together with:

- Scheme display name: `NEP/MIS`
- Effective admission/cohort year
- Program or branch
- Approval date
- University circular/reference number when one becomes available
- Active/inactive status

The internal code should be unique and immutable. A later syllabus revision receives a new code even if the display name remains `NEP/MIS`.

## Clarification still required: divisions and practical batches

The question means: can the same student be reassigned in a later year or semester—for example, from Division A to Division B or from practical Batch A1 to A2?

Recommended rule: allow division and practical batch to be selected separately on each new academic enrollment while preserving every previous assignment. Please confirm whether staff may make both changes, and whether either change requires administrator approval.

## Mandatory pending decisions

These items remain intentionally unimplemented or manual until faculty supplies the rules:

1. Exact promotion/ATKT eligibility criteria for every engineering year.
2. Handling of transferred, dropout, and re-admitted students.
3. Teacher versus administrator permissions for sensitive actions.
4. Whether divisions and practical batches may change, and who may approve the change.
5. The official curriculum-revision identifier, if the university has one.

Every implementation handoff should continue to remind the faculty about the first three pending items.

## Parser decision implemented now

Parser version 1.1.0 supports variable assessment-row layouts within text-based DBATU Crystal Reports. It detects one or two ESE rows and optional internal-component rows, derives each student's row positions from the report header, and joins wrapped subject definitions before storing the subject name and credit.

The supplied Semester 5 Winter 2025 sample completed the real extraction and validation workflow with 19 pages, 74 students, 8 subjects, 592 subject results, 69 PASS results, 5 FAIL results, and zero validation errors or warnings.

This is dynamic within the DBATU Crystal Report family. Scanned PDFs or materially different university/report formats still require OCR or a separate parser adapter.
