"""Drill-down populations share the exact predicates used by each chart."""
from .analysis_service import (
    SGPA_BANDS, GRADE_ORDER, declared, numeric_total, ranked_students,
    reported_sgpa, scored_grade, scored_results, student_row,
)


def filter_records(report, arguments):
    kind = arguments.get('kind', 'all')
    value = arguments.get('value', '')
    query = arguments.get('q', '').strip()[:200]
    outcome = arguments.get('outcome', '').upper()
    measure = arguments.get('measure', '')
    valid_kinds = {'all','result','sgpa','highest','subject','grade','validation','component'}
    if kind not in valid_kinds or outcome not in {'','PASS','FAIL'} or measure not in {'','average'}:
        raise ValueError('Invalid analysis filter.')
    results_view = kind in {'subject','grade','component'}
    label, records = 'All students', []
    if kind == 'result':
        allowed = {s.result_status for s in report.students}
        if value not in allowed: raise ValueError('Result category is not present in this report.')
        label = value.title() + ' students'
    elif kind == 'validation':
        if value not in {s.validation_status for s in report.students}: raise ValueError('Unknown validation category.')
        label = 'Validation: ' + value.replace('_',' ').title()
    elif kind == 'sgpa':
        if value not in {str(i) for i in range(len(SGPA_BANDS))}: raise ValueError('Unknown SGPA range.')
        low, high, band = SGPA_BANDS[int(value)]
        label = 'SGPA: ' + band
    elif kind == 'highest':
        ranked = ranked_students(report)
        highest = ranked[0][1] if ranked else None
        label = 'Highest SGPA students'
    elif kind == 'subject':
        subject = next((s for s in report.subjects if s.subject_code == value and not s.is_audit),None)
        if subject is None: raise ValueError('Subject is not present in this report.')
        label = subject.subject_name + (' - ' + outcome.title() if outcome else '')
        if measure == 'average': label += ' (marks contributing to average)'
    elif kind == 'grade':
        if value not in GRADE_ORDER: raise ValueError('Unknown grade.')
        label = 'Grade: ' + value
    elif kind == 'component':
        if value not in {c.component_type for _,r in scored_results(report) for c in r.components}:
            raise ValueError('Component is not present in this report.')
        label = 'Assessment: ' + value.replace('_',' ').title()
    if not results_view:
        for student in sorted(report.students, key=lambda s:s.seat_number):
            sgpa = reported_sgpa(student)
            match = (kind == 'all' or
                kind == 'result' and student.result_status == value or
                kind == 'validation' and student.validation_status == value or
                kind == 'sgpa' and declared(student) and sgpa is not None and low <= sgpa < high or
                kind == 'highest' and student.result_status == 'PASS' and highest is not None and sgpa == highest)
            if match: records.append(student_row(student))
    else:
        for student,result in scored_results(report):
            grade = scored_grade(result)
            if kind == 'subject':
                if result.subject.subject_code != value: continue
                if outcome == 'PASS' and (not grade or grade == 'FF'): continue
                if outcome == 'FAIL' and grade != 'FF': continue
                if measure == 'average' and not numeric_total(result): continue
            if kind == 'grade' and grade != value: continue
            components = [None]
            if kind == 'component':
                components = [c for c in result.components if c.component_type == value
                              and c.numeric_value is not None and c.assessment.maximum_marks > 0]
            for component in components:
                records.append({**student_row(student),
                    'subject_code':result.subject.subject_code, 'subject_name':result.subject.subject_name,
                    'grade':result.grade, 'marks':result.total_value,
                    'component':component.component_type if component else None,
                    'component_marks':component.numeric_value if component else None,
                    'component_maximum':component.assessment.maximum_marks if component else None,
                })
        records.sort(key=lambda r:(r['seat_number'],r['subject_code']))
    if query:
        needle = query.casefold()
        records = [r for r in records if needle in ' '.join(str(r.get(k) or '') for k in
                   ('seat_number','name','subject_name','subject_code')).casefold()]
    return {'label':label,'records':records,'results_view':results_view,
            'student_count':len({r['id'] for r in records}), 'count':len(records),
            'kind':kind,'value':value,'q':query,'outcome':outcome,'measure':measure}
