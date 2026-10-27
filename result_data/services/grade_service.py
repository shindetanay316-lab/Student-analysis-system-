"""Recover printed labels without inventing grades from marks or calculations."""
from ..parsers.value_normalizer import grade_label


def manually_changed_grade(result):
    student=getattr(result,'student',None)
    report=getattr(student,'report',None)
    if report is None:return False
    return any(c.subject_result_id==result.id and c.field_name in
               {'grade','audit_grade','grade_point','credit_points','grace_marks'}
               for c in report.corrections)


def display_grade(result):
    primary=result.audit_grade if result.subject.is_audit else result.grade
    if primary and primary.strip() not in {"|","-","N/A"}:
        return grade_label(primary) or primary.strip()
    # An intentionally cleared/corrected value must never be restored from raw text.
    if manually_changed_grade(result):return None
    return grade_label(result.grade_raw)
