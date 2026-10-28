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


def apply_student_batch_filters(query, StudentModel, division=None, batch=None, semester_id=None, academic_year=None):
    """Use a semester placement when available, with legacy defaults for old callers."""
    division = clean_filter(division)
    batch = clean_filter(batch)

    if semester_id and academic_year:
        from models import db
        from completion_models import StudentTerm
        scope = (StudentTerm.prn==StudentModel.prn, StudentTerm.semester_id==semester_id, StudentTerm.academic_year==academic_year)
        exists = db.select(StudentTerm.id).where(*scope).correlate(StudentModel).exists()
        for key,value in [('division',division),('batch',batch)]:
            if value:
                column = db.select(getattr(StudentTerm,key)).where(*scope).correlate(StudentModel).scalar_subquery()
                query = query.filter(db.case((exists,column),else_=getattr(StudentModel,key))==value)
    else:
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


def term_filter_options(semester_id=None, academic_year=None):
    from completion_models import StudentTerm
    query=StudentTerm.query
    if semester_id and academic_year:
        query=query.filter_by(semester_id=semester_id,academic_year=academic_year)
    rows=query.with_entities(StudentTerm.division,StudentTerm.batch).distinct().all()
    return (sorted(set(DIVISION_OPTIONS)|{d for d,b in rows if d}),
        sorted(set(BATCH_OPTIONS)|{b for d,b in rows if b}))
