"""Shared helpers for Division / Batch filtering."""

DIVISION_OPTIONS = ["A", "B"]
BATCH_OPTIONS = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"]


def clean_filter(value):
    """Return a normalized filter string or empty string."""
    if value is None:
        return ""
    value = str(value).strip().upper()
    if value in {"", "ALL", "NONE", "NULL"}:
        return ""
    return value


def apply_student_batch_filters(query, StudentModel, division=None, batch=None):
    """Apply optional Student.division / Student.batch filters to a joined Student query."""
    division = clean_filter(division)
    batch = clean_filter(batch)

    if division:
        query = query.filter(StudentModel.division == division)
    if batch:
        query = query.filter(StudentModel.batch == batch)
    return query


def batch_label(division=None, batch=None):
    division = clean_filter(division)
    batch = clean_filter(batch)
    if division and batch:
        return f"Division {division} | Batch {batch}"
    if division:
        return f"Division {division}"
    if batch:
        return f"Batch {batch}"
    return "All Students"
