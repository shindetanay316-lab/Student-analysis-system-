# Reports and dashboard verification

Verified in Linux using Python 3.12 and SQLite. The Windows installer uses the
existing project's Python environment and adds no new Python dependencies.

## Automated checks

59 Python tests passed: the earlier 47 parser/workflow regressions and 12 report,
workbook, settings, ranking and drill-down tests. The updated optional-summary
regression verifies its original fields in the separate detailed data workbook.

Checks cover all six filter populations against chart counts, search and
pagination, invalid filters, source grades/SGPA taking precedence over expected
calculation values, PASS-only ranking, highest-SGPA ties, SGPA boundaries,
missing SGPA, grade-only matrix order, PRNs stored as literal strings, missing
versus inapplicable grades, failed-row conditional formatting, the six workbook
sheets and four charts, editable faculty/signatures in both exports, CSRF,
all download routes and wide PDF panels without discarded subjects.

The chart JavaScript was executed in Node with a controlled DOM/Chart harness.
Actual registered callbacks were invoked for all six charts, subject average
and pass-rate datasets, and result/validation legends. Filter URLs, full subject
labels and clicks in empty areas were checked. Browser automation could not be
run because browser-binary downloads were unavailable in this environment;
this is not a claim of a native-browser click test.

## Five original PDF datasets

| Source layout | Students | Distinct subjects | Subject results | Top list |
|---|---:|---:|---:|---:|
| Semester 1, Summer 2026 Supply | 63 | 12 | 756 | 10 |
| Semester 3, Winter 2024 office report | 75 | 8 | 600 | 10 |
| Semester 3, Summer 2025 Supply | 20 | 8 | 160 | 6 |
| Semester 4, Summer 2025 Regular | 75 | 10 | 675 | 10 |
| Semester 5, Winter 2025 Regular | 74 | 8 | 592 | 10 |

All 307 students and 2,783 subject-result records were retained. Every source
produced the approved six-sheet workbook and a PDF. Every PRN was found in the
PDF; all student/subject grade cells in each saved workbook matched the shared
report projection exactly. Names were read from actual subject definitions.
Existing source validation warnings were retained; extraction had zero errors.

## Layout and file checks

PDFs were rendered and reviewed for logos, headings, pagination, repeated
headers, signatures, red failed rows, wide matrices and long subject names.
All six workbook sheets were rendered with Artifact Tool for visual review;
summary and subject percentage formulas recalculated without formula errors.
PRNs were independently checked in XLSX XML as inline strings, not floating
point numbers; leading zeros and every digit are retained. The renderer may
format numeric-looking strings differently from desktop Excel. Native Windows
Excel was not available for a desktop check.

Workbook files preserve filters, freeze panes, print settings, number formats,
conditional formatting, local logos and native Excel charts. Production
exports use the project's existing Python workbook dependency; no separate
Node authoring runtime is needed on the user's laptop.

## Installer preservation

The supplied installer was checked against a clean copy of the Parser 2.0
codebase and an existing populated SQLite database. Configuration bytes,
all original table records, the parser and academic calculation files remained
unchanged. One additive result_report_settings table was created, and the
SQLite backup was checked for the original records. Login, analysis and PDF/
Excel downloads were checked against the upgraded application.

The package contains only updated code, documentation, a locally bundled
Chart.js script and license, tests, and anonymized layout previews. It contains
no real student PDFs, database, .env, credentials or virtual environment.
