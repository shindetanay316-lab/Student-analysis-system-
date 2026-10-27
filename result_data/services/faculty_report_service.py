"""One faculty-facing projection for PDF and Excel, with reviewed source values."""
from datetime import datetime
from pathlib import Path
from functools import lru_cache
import json
from .grade_service import display_grade,manually_changed_grade
from zoneinfo import ZoneInfo
from flask import current_app
from .analysis_service import build_report_analysis, reported_sgpa

SIGNATURES = (
    ('coordinator','Result Analysis Coordinator'), ('hod','HOD'),
    ('dean','Dean Academics'), ('principal','Principal'),
)


@lru_cache(maxsize=1)
def template_defaults():
    path=Path(__file__).resolve().parents[2]/'static/result_data/templates/college_analysis_layout.json'
    return json.loads(path.read_text())


def report_options(job):
    saved = job.report_settings.data if job.report_settings else {}
    return {
        'report_date':saved.get('report_date') or datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),
        'faculty':{**template_defaults()['faculty_defaults'],**saved.get('faculty',{})},
        'signatures':{key:saved.get('signatures',{}).get(key,current_app.config.get({
            'coordinator':'RESULT_COORDINATOR_NAME','hod':'HOD_NAME',
            'dean':'DEAN_ACADEMICS_NAME','principal':'PRINCIPAL_NAME'}[key],template_defaults()['signature_defaults'].get(key,''))) for key,_ in SIGNATURES},
    }


def build_faculty_report(job):
    report = job.report
    analysis = build_report_analysis(report)
    options = report_options(job)
    students = sorted(report.students,key=lambda s:s.seat_number)
    subjects = sorted(report.subjects,key=lambda s:s.display_order)
    rows = []
    for number,student in enumerate(students,1):
        results = {r.subject.subject_code:r for r in student.subject_results}
        grades, failed = [], []
        for subject in subjects:
            result = results.get(subject.subject_code)
            if result is None:
                applicable=subject.subject_code in report.subject_codes_for_page(student.source_page)
                grades.append('MISSING' if applicable else 'N/A')
                continue
            grade = display_grade(result)
            grades.append(grade or ('REVIEW' if manually_changed_grade(result) else 'CANCELLED' if student.result_status=='CANCEL' else 'NOT PRINTED'))
            if grade == 'FF': failed.append(f'{subject.subject_name} ({subject.subject_code})')
        rows.append({'serial':number,'prn':student.seat_number,'name':student.name,
                     'grades':grades,'result':student.result_status,'sgpa':reported_sgpa(student),
                     'gender':student.gender_marker or '',
                     'failed_subjects':'; '.join(failed) or 'Not printed / review required'})
    counts = {key:sum(s.result_status==key for s in students) for key in ('PASS','FAIL','WITHHELD','CANCEL')}
    counts['OTHER'] = len(students)-sum(counts.values())
    stats = {row['code']:row for row in analysis['subject_performance']}
    subject_rows=[]
    for serial,subject in enumerate(subjects,1):
        stats_row=stats.get(subject.subject_code,{})
        subject_rows.append({'serial':serial,'code':subject.subject_code,'name':subject.subject_name,
            'faculty':options['faculty'].get(subject.subject_code,''),
            'appeared':stats_row.get('students',sum(s.result_status in {'PASS','FAIL'} and
                         any(r.subject.subject_code==subject.subject_code for r in s.subject_results) for s in students)),
            'passed':stats_row.get('passed') if not subject.is_audit else None,
            'failed':stats_row.get('failed') if not subject.is_audit else None,
            'pass_rate':stats_row.get('pass_rate') if not subject.is_audit else None,
            'audit':subject.is_audit})
    return {'job':job,'report':report,'analysis':analysis,'options':options,'subjects':subjects,
            'students':rows,'failed_students':[r for r in rows if r['result']=='FAIL'],
            'top_students':analysis['top_performers'],'counts':counts,'subject_rows':subject_rows,
            'status':'CONFIRMED' if job.status in {'READY','EXPORTED'} and job.confirmed_at else 'PROVISIONAL',
            'signatures':[(label,options['signatures'].get(key,'')) for key,label in SIGNATURES]}
