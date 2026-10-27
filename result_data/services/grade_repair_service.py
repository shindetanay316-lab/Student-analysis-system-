"""Repair only missing printed grades, preserving every manual correction."""
from pathlib import Path
from models import db
from ..models import DataCorrection, ImportJob
from ..parsers import DBATUCrystalReportParser
from ..parsers.value_normalizer import grade_label,parse_grade
from .grade_service import manually_changed_grade
from .validation_service import validate_report


def repair_missing_grades(job,upload_folder):
    if job.report is None:return 0
    report=job.report
    pending=[(s,r) for s in report.students if s.result_status!='CANCEL' for r in s.subject_results
             if not grade_label(r.audit_grade if r.subject.is_audit else r.grade)
             and not manually_changed_grade(r)]
    if not pending:return 0
    source={}
    if any(not grade_label(r.grade_raw) for _,r in pending):
        path=Path(upload_folder)/job.stored_filename
        if path.is_file():
            parsed=DBATUCrystalReportParser().parse(path)
            source={(s.seat_number,r.subject_code):r for s in parsed.students for r in s.subject_results}
    count=0
    for student,result in pending:
        parsed=source.get((student.seat_number,result.subject.subject_code))
        raw=result.grade_raw
        label=grade_label(raw)
        if not label and parsed is not None:
            raw=parsed.grade_raw;label=parsed.audit_grade if result.subject.is_audit else parsed.grade
            label=grade_label(label) or grade_label(raw)
        if not label:continue
        attribute='audit_grade' if result.subject.is_audit else 'grade'
        old=getattr(result,attribute)
        setattr(result,attribute,label)
        if raw:result.grade_raw=raw
        detail=parse_grade(raw)
        if detail:
            for key,value in [('grade_point',detail.grade_point),('credit_points',detail.credit_points),('grace_marks',detail.grace_marks)]:
                if getattr(result,key) is None:setattr(result,key,value)
        report.corrections.append(DataCorrection(student=student,subject_result=result,
            entity_type='SOURCE_GRADE_REPAIR',entity_label=result.subject.subject_code,
            field_name=attribute,original_value=old,previous_value=old,new_value=label,
            reason='Recovered the printed grade from the original PDF or retained raw grade text. No calculation rule was used.'))
        count+=1
    if count:
        validate_report(report)
        job.status=ImportJob.STATUS_REVIEW_REQUIRED
        job.confirmed_at=None;job.confirmed_by_id=None;job.confirmation_notes=None
    return count
