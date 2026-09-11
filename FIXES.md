# Repair summary

## Functional fixes

- Fixed department-summary Excel generation for semesters with fewer than five subjects.
- Fixed normal-subject attendance so it never falls back to unenrolled students.
- Fixed external Excel submissions so saved records are actually locked.
- Added division/batch-scoped internal submission locking, including absent marks.
- Fixed CT, external, and lab uploads to enforce enrollment and selected filter scope.
- Added template metadata validation, duplicate-PRN rejection, and missing-student detection.
- Fixed timetable re-upload so removed or moved slots do not remain active.
- Corrected afternoon timetable template times to 24-hour values.
- Added safe handling for corrupt timetable and attendance workbooks.
- Added attendance division/batch summary filters and exact academic-year selection.
- Fixed active-semester selection so an invalid semester/year combination cannot be submitted.
- Added validation for invalid subject values and elective parent relationships.
- Prevented `seed.py` from overwriting passwords on every run.

## Duplication and maintenance cleanup

- Removed the duplicate/dead department-summary JavaScript from the CT page.
- Removed duplicate same-name hidden controls from CT and lab selector forms.
- Removed the obsolete second external-upload page.
- Removed tracked Python bytecode and added repository ignore rules.
- Updated SQLAlchemy record lookups and timestamp defaults for current dependencies.
- Disabled Flask debug mode by default.
- Added a repeatable end-to-end workflow test suite.

## Calculation guarantee

`calculations.py` was not modified. Existing grading, internal, external,
lab, SGPA, and CGPA formulas remain unchanged.

