# Test Report

## Test run

- Date: 11 September 2026
- Runtime: Python 3.12
- Test database: isolated temporary SQLite database
- Command: `python -m unittest discover -v`
- Result: **23 tests passed**

The test database and uploaded test files were isolated from the configured application database.

## Automated coverage

The 20 existing workflow tests passed for:

- Authentication and role protection
- Main admin page rendering
- Active-semester selection
- Subject create/update/delete safeguards
- Elective allocation
- Division and batch assignment
- Internal marks templates, validation, upload, locking, and reports
- External marks templates, upload, locking, statistics, and reports
- Lab/project marks templates, upload, and reports
- Attendance, timetable, templates, validation, and reports
- Analytics endpoints
- Result PDF upload, unsupported-file handling, review pages, database records, and exports
- JSON and supporting workflows

Three parser regression tests were added for:

- DBATU reports with one ESE display row
- Continued support for DBATU reports with two ESE display rows
- Long subject definitions wrapped over two PDF text lines

## Supplied Semester 5 PDF verification

The supplied text-based DBATU Semester 5 Winter 2025 report was tested both directly and through the real database extraction/validation service.

| Check | Result |
| --- | ---: |
| PDF pages | 19 |
| Printed and parsed students | 74 |
| Unique seat numbers | 74 |
| Subjects | 8 |
| Subject results | 592 |
| PASS results | 69 |
| FAIL results | 5 |
| Database validation errors | 0 |
| Database validation warnings | 0 |
| Final import state | Review required |

All printed seat numbers matched the parsed seat numbers. Every parsed student received eight subject-result records. The long Computer Networks/Cloud Computing/Competitive Programming lab name and its credit were retained as one subject.

The sample PDF itself is not bundled in the distributable project because it contains identifiable student records.

## Formula and data-safety checks

- No marks, SGPA, CGPA, percentage, grade, attendance, or promotion formula was changed.
- The parser stores reported source values separately from calculated validation values.
- Existing tests for the corrected project's calculations and report workflows still pass.
- Extraction is atomic: an unexpected parsing/storage error rolls back extracted records and marks the import as failed.
- The duplicate file-hash safeguard remains enabled.

## Known boundaries

- Parser version 1.1.0 is dynamic within the text-based DBATU Crystal Report family; scanned PDFs still require OCR.
- A materially different university report family needs a separate parser adapter and its own regression fixture.
- The larger academic-history redesign remains paused where faculty policy is still pending; see `FACULTY_DECISIONS.md`.
