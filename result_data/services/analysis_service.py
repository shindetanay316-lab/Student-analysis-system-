from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

from ..models import ExamReport


SGPA_BANDS = (
    (Decimal("0"), Decimal("5"), "Below 5"),
    (Decimal("5"), Decimal("6"), "5–5.99"),
    (Decimal("6"), Decimal("7"), "6–6.99"),
    (Decimal("7"), Decimal("8"), "7–7.99"),
    (Decimal("8"), Decimal("9"), "8–8.99"),
    (Decimal("9"), Decimal("10.01"), "9–10"),
)
GRADE_ORDER = ("EX", "AA", "AB", "BB", "BC", "CC", "CD", "DD", "DE", "EE", "FF")


def build_report_analysis(report: ExamReport) -> dict:
    """Build presentation-ready aggregates from one validated report."""
    students = list(report.students)
    subjects = list(report.subjects)
    summaries = [student.summary for student in students if student.summary]
    sgpa_records = [
        (student, _effective_sgpa(student.summary))
        for student in students
        if student.summary and _effective_sgpa(student.summary) is not None
    ]

    result_statuses = Counter(student.result_status or "UNKNOWN" for student in students)
    validation_statuses = Counter(
        student.validation_status or "NOT_VALIDATED" for student in students
    )
    declared_results = result_statuses["PASS"] + result_statuses["FAIL"]
    expected_results = len(students) * len(subjects)
    completion_rate = _percentage(report.result_count, expected_results)

    sgpa_values = [sgpa for _student, sgpa in sgpa_records]
    average_sgpa = _average(sgpa_values)
    highest_sgpa = max(sgpa_values, default=None)
    lowest_sgpa = min(sgpa_values, default=None)

    grade_counts = Counter()
    component_percentages: dict[str, list[Decimal]] = defaultdict(list)
    results_by_subject = defaultdict(list)
    for student in students:
        for result in student.subject_results:
            results_by_subject[result.subject_id].append(result)
            if not result.subject.is_audit:
                grade = result.expected_grade or result.grade
                if grade:
                    grade_counts[grade] += 1
            for component in result.components:
                maximum = component.assessment.maximum_marks
                if component.numeric_value is not None and maximum and maximum > 0:
                    component_percentages[component.component_type].append(
                        component.numeric_value * Decimal("100") / maximum
                    )

    subject_performance = []
    for subject in subjects:
        if subject.is_audit:
            continue
        percentages = []
        declared_subject_results = []
        subject_results = results_by_subject[subject.id]
        for result in subject_results:
            if (
                result.total_value is not None
                and subject.total_maximum is not None
                and subject.total_maximum > 0
            ):
                percentages.append(
                    result.total_value * Decimal("100") / subject.total_maximum
                )
            grade = result.expected_grade or result.grade
            if grade:
                declared_subject_results.append(grade)
        passed = sum(grade != "FF" for grade in declared_subject_results)
        subject_performance.append(
            {
                "code": subject.subject_code,
                "name": subject.subject_name,
                "average_percentage": _float_or_none(_average(percentages)),
                "pass_rate": _percentage(passed, len(declared_subject_results)),
                "students": len(subject_results),
            }
        )

    component_performance = [
        {
            "component": component.replace("_", " ").title(),
            "average_percentage": _float_or_none(_average(values)),
            "records": len(values),
        }
        for component, values in component_percentages.items()
    ]

    ranked_students = sorted(
        sgpa_records,
        key=lambda item: (
            -item[1],
            -(_effective_total_marks(item[0].summary) or Decimal("-1")),
            item[0].name,
        ),
    )
    top_performers = [_student_row(student, sgpa) for student, sgpa in ranked_students[:5]]

    failed = [item for item in sgpa_records if item[0].result_status == "FAIL"]
    attention_pool = failed or sorted(sgpa_records, key=lambda item: (item[1], item[0].name))
    attention_reason = "Failed result" if failed else "Lowest SGPA records"
    attention_students = [
        {**_student_row(student, sgpa), "reason": attention_reason}
        for student, sgpa in attention_pool[:5]
    ]

    return {
        "summary": {
            "students": len(students),
            "subjects": len(subjects),
            "subject_results": report.result_count,
            "completion_rate": completion_rate,
            "pass_rate": _percentage(result_statuses["PASS"], declared_results),
            "average_sgpa": _float_or_none(average_sgpa),
            "highest_sgpa": _float_or_none(highest_sgpa),
            "lowest_sgpa": _float_or_none(lowest_sgpa),
            "corrections": len(report.corrections),
            "summaries": len(summaries),
        },
        "result_status": _ordered_counts(result_statuses, ("PASS", "FAIL", "CANCEL")),
        "validation_status": _ordered_counts(
            validation_statuses, ("VALID", "WARNING", "ERROR", "SKIPPED", "NOT_VALIDATED")
        ),
        "sgpa_distribution": [
            {
                "label": label,
                "count": sum(lower <= value < upper for value in sgpa_values),
            }
            for lower, upper, label in SGPA_BANDS
        ],
        "grade_distribution": [
            {"grade": grade, "count": grade_counts[grade]}
            for grade in GRADE_ORDER
            if grade_counts[grade]
        ],
        "subject_performance": subject_performance,
        "component_performance": component_performance,
        "top_performers": top_performers,
        "attention_students": attention_students,
    }


def _effective_sgpa(summary) -> Decimal | None:
    if summary.calculated_sgpa is not None:
        return summary.calculated_sgpa
    return summary.reported_sgpa


def _effective_total_marks(summary) -> Decimal | None:
    if summary.calculated_total_marks is not None:
        return summary.calculated_total_marks
    return summary.reported_total_marks


def _student_row(student, sgpa: Decimal) -> dict:
    return {
        "id": student.id,
        "seat_number": student.seat_number,
        "name": student.name,
        "sgpa": _float_or_none(sgpa),
        "total_marks": _float_or_none(_effective_total_marks(student.summary)),
        "result_status": student.result_status,
        "validation_status": student.validation_status,
    }


def _ordered_counts(counter: Counter, order: tuple[str, ...]) -> list[dict]:
    rows = [{"label": label.replace("_", " ").title(), "count": counter[label]} for label in order]
    known = set(order)
    rows.extend(
        {"label": label.replace("_", " ").title(), "count": count}
        for label, count in sorted(counter.items())
        if label not in known
    )
    return [row for row in rows if row["count"]]


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return (sum(values, Decimal("0")) / len(values)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return float(
        (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )


def _float_or_none(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
