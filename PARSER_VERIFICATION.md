# Parser verification

Verified on 27 October 2026 using Python 3.12 and SQLite in Linux. Windows installation is provided but was not executed on a Windows host.

## Supplied result PDFs

| Source layout | Pages | Students | Distinct subjects | Subject results | Validation errors | Review warnings |
|---|---:|---:|---:|---:|---:|---:|
| Semester 1, Summer 2026 Supply (NEP) | 21 | 63 | 12 | 756 | 0 | 1 |
| Semester 3, Winter 2024 Regular (office report; filename says APRIL_2024) | 19 | 75 | 8 | 600 | 0 | 1 |
| Semester 3, Summer 2025 Supply | 5 | 20 | 8 | 160 | 0 | 4 |
| Semester 4, Summer 2025 Regular | 23 | 75 | 10 | 675 | 0 | 78 |
| Semester 5, Winter 2025 Regular (filename says DECEMBER_2025) | 19 | 74 | 8 | 592 | 0 | 0 |

**Total: 87 pages, 307 students, 2,783 subject results.** Every sample reached REVIEW_REQUIRED with an extracted report and 100% of its page-specific expected result records. All acceptance checks passed.

Semester 4 contains nine printed subject columns per student and ten distinct subjects across the complete report, because the elective changes. Counting every student against ten subjects would invent missing results.

## Review notes retained from the sources

- Semester 1: one printed component-total discrepancy.
- Old Semester 3 office report: the internship prints a 50-mark maximum with no passing minimum.
- Semester 3 Supply: two component-total discrepancies, one unrecognized `--` special mark and one source status/grade inconsistency.
- Semester 4: 75 printed `|` grades, and printed maximum-credit/grade-point inconsistencies. Grade-dependent calculations remain unknown when grades are absent.
- Semester 5: no validation warnings or errors.

No marks were invented to remove these warnings. Printed totals, marks and source placeholders remain available for review and export.

## Automated checks

47 tests passed, including the original 23 regression tests and 24 additional parser/upload/storage checks. Tests use anonymized real-layout fixtures rendered into actual PDFs, plus generated layout variations.

Coverage: variable subject counts, short and wrapped codes, spatial catalogue reconstruction, multi-line credit declarations, optional subject definitions, page-specific electives, extra/missing assessment rows, distinct ESE rows, internal-only layouts, missing CREDIT/SGPA headings, blank marks and missing totals, optional summary fields, resized pages, carried-forward values, absence codes, cancellations, month-based attempts, source grade placeholders, duplicate-seat detection, actionable image-only-PDF rejection, successful UI upload, page-specific validation/coverage, review pages, Excel/CSV/JSON persistence, successful repeat extraction and rollback on extraction failure.

Original raw student PDFs and databases are excluded from the regression fixtures and update ZIP.

## Installer verification

The supplied installer was run against a clean checkout of the original GitHub main revision containing a seeded SQLite database and a sentinel student record. The upgrade preserved .env byte for byte, retained the sentinel and all original tables, kept app.py/models.py/config.py/calculations.py/final_result_utils.py unchanged, verified the SQLite backup contains the original records, and added only result_source_data. Login, dashboard and the result module rendered after upgrading. This check ran on Linux using the same cross-platform Python installer shipped for Windows.
