"""University analysis uses the reviewed, reported values consistently."""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

SGPA_BANDS = (
    (Decimal('0'), Decimal('5'), 'Below 5'),
    (Decimal('5'), Decimal('6'), '5–5.99'),
    (Decimal('6'), Decimal('7'), '6–6.99'),
    (Decimal('7'), Decimal('8'), '7–7.99'),
    (Decimal('8'), Decimal('9'), '8–8.99'),
    (Decimal('9'), Decimal('10.01'), '9–10'),
)
GRADE_ORDER = ('EX', 'AA', 'AB', 'BB', 'BC', 'CC', 'CD', 'DD', 'DE', 'EE', 'FF')


def reported_sgpa(student):
    value = student.summary.reported_sgpa if student.summary else None
    return value if value is not None and Decimal('0') <= value <= Decimal('10') else None


def scored_grade(result):
    return result.grade if not result.subject.is_audit and result.grade in GRADE_ORDER else None


def declared(student):
    return student.result_status in {'PASS', 'FAIL'}


def scored_results(report):
    for student in report.students:
        if declared(student):
            for result in student.subject_results:
                if not result.subject.is_audit:
                    yield student, result


def numeric_total(result):
    maximum = result.subject.total_maximum
    return result.total_value is not None and maximum is not None and maximum > 0


def ranked_students(report):
    rows = [(student, reported_sgpa(student)) for student in report.students
            if student.result_status == 'PASS' and reported_sgpa(student) is not None]
    def key(item):
        student, sgpa = item
        total = student.summary.reported_total_marks
        return (-sgpa, -(total if total is not None else Decimal('-1')), student.seat_number)
    return sorted(rows, key=key)


def student_row(student):
    return {
        'id': student.id, 'seat_number': student.seat_number, 'name': student.name,
        'sgpa': _float_or_none(reported_sgpa(student)),
        'total_marks': _float_or_none(student.summary.reported_total_marks if student.summary else None),
        'result_status': student.result_status, 'validation_status': student.validation_status,
    }


def build_report_analysis(report):
    students, subjects = list(report.students), list(report.subjects)
    statuses = Counter(s.result_status or 'UNKNOWN' for s in students)
    validations = Counter(s.validation_status or 'NOT_VALIDATED' for s in students)
    sgpas = [(s, reported_sgpa(s)) for s in students if declared(s) and reported_sgpa(s) is not None]
    sgpa_values = [value for _, value in sgpas]
    ranked = ranked_students(report)
    highest = ranked[0][1] if ranked else None
    highest_students = [student_row(s) for s, value in ranked if value == highest]
    top = []
    last, rank = None, 0
    for index, (student, value) in enumerate(ranked[:10], 1):
        if value != last:
            rank, last = index, value
        top.append({**student_row(student), 'rank': rank})
    by_subject, grades, components = defaultdict(list), Counter(), defaultdict(list)
    for student, result in scored_results(report):
        by_subject[result.subject.subject_code].append(result)
        grade = scored_grade(result)
        if grade:
            grades[grade] += 1
        for component in result.components:
            maximum = component.assessment.maximum_marks
            if component.numeric_value is not None and maximum and maximum > 0:
                components[component.component_type].append(component.numeric_value * 100 / maximum)
    performance = []
    for subject in subjects:
        if subject.is_audit:
            continue
        results = by_subject[subject.subject_code]
        valid_grades = [scored_grade(r) for r in results if scored_grade(r)]
        passed = sum(g != 'FF' for g in valid_grades)
        percentages = [r.total_value * 100 / subject.total_maximum for r in results if numeric_total(r)]
        performance.append({
            'code': subject.subject_code, 'name': subject.subject_name,
            'average_percentage': _float_or_none(_average(percentages)),
            'pass_rate': _percentage(passed, len(valid_grades)),
            'students': len(results), 'passed': passed, 'failed': valid_grades.count('FF'),
            'ungraded': len(results) - len(valid_grades),
        })
    return {
        'summary': {
            'students': len(students), 'subjects': len(subjects), 'subject_results': report.result_count,
            'completion_rate': _percentage(report.result_count, report.expected_result_count),
            'pass_rate': _percentage(statuses['PASS'], statuses['PASS'] + statuses['FAIL']),
            'average_sgpa': _float_or_none(_average(sgpa_values)),
            'highest_sgpa': _float_or_none(highest), 'highest_students': highest_students,
            'highest_student_names': ', '.join(s['name'] for s in highest_students),
            'lowest_sgpa': _float_or_none(min(sgpa_values, default=None)),
            'corrections': len(report.corrections),
            'summaries': sum(s.summary is not None for s in students),
        },
        'result_status': _ordered_counts(statuses, ('PASS','FAIL','CANCEL','WITHHELD','RESERVED')),
        'validation_status': _ordered_counts(validations, ('VALID','WARNING','ERROR','SKIPPED','NOT_VALIDATED')),
        'sgpa_distribution': [{'label': label, 'key': str(i),
            'count': sum(low <= value < high for value in sgpa_values)}
            for i,(low,high,label) in enumerate(SGPA_BANDS)],
        'grade_distribution': [{'grade': grade, 'count': grades[grade]} for grade in GRADE_ORDER if grades[grade]],
        'subject_performance': performance,
        'component_performance': [{'key': key, 'component': key.replace('_',' ').title(),
            'average_percentage': _float_or_none(_average(values)), 'records': len(values)}
            for key,values in sorted(components.items())],
        'top_performers': top,
    }


def _average(values):
    return (sum(values, Decimal('0')) / len(values)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if values else None


def _percentage(numerator, denominator):
    return float((Decimal(numerator)*100/denominator).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if denominator else None


def _float_or_none(value):
    return float(value) if value is not None else None


def _ordered_counts(counter, order):
    keys = list(order) + sorted(set(counter)-set(order))
    return [{'key':key, 'label':key.replace('_',' ').title(), 'count':counter[key]} for key in keys if counter[key]]
