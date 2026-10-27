from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from ..models import ExamReport, ReportStudent, SubjectResult, ValidationIssue
from .calculation_service import (
    CALCULATION_RULE_VERSION,
    SUPPORTED_PARSER_NAME,
    calculate_component_sum,
    calculate_credit_points,
    calculate_grade,
    calculate_sgpa,
)


STATUS_NOT_VALIDATED = "NOT_VALIDATED"
STATUS_VALID = "VALID"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "ERROR"
STATUS_SKIPPED = "SKIPPED"

KNOWN_ABSENCE_CODES = {"AB", "AOO", "ABSENT"}


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    status: str
    error_count: int
    warning_count: int


def validate_report(report: ExamReport) -> ValidationSummary:
    """Recalculate and validate one extracted report without changing source values."""
    report.validation_issues.clear()

    _validate_report_configuration(report)
    if report.parser_name != SUPPORTED_PARSER_NAME:
        report.calculation_rule_version = None
        _add_issue(
            report,
            ValidationIssue.SEVERITY_ERROR,
            "REPORT",
            "UNSUPPORTED_CALCULATION_RULES",
            f"No calculation rules are registered for parser {report.parser_name}.",
        )
        for student in report.students:
            student.validation_status = STATUS_NOT_VALIDATED
        return _finish_report_validation(report)

    report.calculation_rule_version = CALCULATION_RULE_VERSION
    for student in report.students:
        _validate_student(report, student)

    return _finish_report_validation(report)


def _finish_report_validation(report: ExamReport) -> ValidationSummary:
    errors = sum(
        issue.severity == ValidationIssue.SEVERITY_ERROR
        for issue in report.validation_issues
    )
    warnings = sum(
        issue.severity == ValidationIssue.SEVERITY_WARNING
        for issue in report.validation_issues
    )
    report.validation_error_count = errors
    report.validation_warning_count = warnings
    report.validation_status = _status_for_counts(errors, warnings)
    report.validated_at = datetime.now(timezone.utc)
    return ValidationSummary(report.validation_status, errors, warnings)


def _validate_report_configuration(report: ExamReport) -> None:
    if not report.subjects:
        _add_issue(
            report,
            ValidationIssue.SEVERITY_ERROR,
            "REPORT",
            "NO_SUBJECTS",
            "No subjects were extracted from the report.",
        )
    if not report.students:
        _add_issue(
            report,
            ValidationIssue.SEVERITY_ERROR,
            "REPORT",
            "NO_STUDENTS",
            "No students were extracted from the report.",
        )

    credit_total = Decimal("0")
    marks_total = Decimal("0")
    for subject in report.subjects:
        if subject.credits is not None:
            if subject.credits < 0:
                _add_issue(
                    report,
                    ValidationIssue.SEVERITY_ERROR,
                    "SUBJECT",
                    "NEGATIVE_CREDITS",
                    f"{subject.subject_code} has negative credits.",
                    field_name="credits",
                    reported_value=subject.credits,
                )
            if not subject.is_audit and subject.credits > 0:
                credit_total += subject.credits

        if subject.is_audit:
            continue
        if subject.credits is None or subject.credits == 0:
            _add_issue(
                report,
                ValidationIssue.SEVERITY_ERROR,
                "SUBJECT",
                "INVALID_CREDITS",
                f"{subject.subject_code} has no valid positive credit value.",
                field_name="credits",
                reported_value=subject.credits,
            )
        if subject.total_maximum is None or subject.total_maximum <= 0:
            _add_issue(
                report,
                ValidationIssue.SEVERITY_ERROR,
                "SUBJECT",
                "INVALID_TOTAL_MAXIMUM",
                f"{subject.subject_code} has no valid total maximum.",
                field_name="total_maximum",
                reported_value=subject.total_maximum,
            )
        else:
            marks_total += subject.total_maximum
        if subject.total_minimum is None:
            _add_issue(report, ValidationIssue.SEVERITY_WARNING, "SUBJECT",
                       "MINIMUM_NOT_PRINTED",
                       f"{subject.subject_code}: the PDF does not print a total pass minimum; no grade rule was inferred.",
                       field_name="total_minimum")
        if (
            subject.total_minimum is not None
            and (subject.total_minimum < 0
            or (
                subject.total_maximum is not None
                and subject.total_minimum > subject.total_maximum
            ))
        ):
            _add_issue(
                report,
                ValidationIssue.SEVERITY_ERROR,
                "SUBJECT",
                "INVALID_TOTAL_MINIMUM",
                f"{subject.subject_code} has an invalid total minimum.",
                field_name="total_minimum",
                reported_value=subject.total_minimum,
            )

        if not subject.assessments:
            _add_issue(
                report,
                ValidationIssue.SEVERITY_ERROR,
                "SUBJECT",
                "NO_ASSESSMENTS",
                f"{subject.subject_code} has no assessment configuration.",
            )
        component_maximum = Decimal("0")
        for assessment in subject.assessments:
            component_maximum += assessment.maximum_marks
            if assessment.maximum_marks <= 0:
                _add_issue(
                    report,
                    ValidationIssue.SEVERITY_ERROR,
                    "SUBJECT",
                    "INVALID_COMPONENT_MAXIMUM",
                    f"{subject.subject_code} {assessment.display_name} has an invalid maximum.",
                    field_name=assessment.component_type,
                    reported_value=assessment.maximum_marks,
                )
            if (
                assessment.minimum_marks is not None
                and (
                    assessment.minimum_marks < 0
                    or assessment.minimum_marks > assessment.maximum_marks
                )
            ):
                _add_issue(
                    report,
                    ValidationIssue.SEVERITY_ERROR,
                    "SUBJECT",
                    "INVALID_COMPONENT_MINIMUM",
                    f"{subject.subject_code} {assessment.display_name} has an invalid minimum.",
                    field_name=assessment.component_type,
                    reported_value=assessment.minimum_marks,
                )
        if (
            subject.total_maximum is not None
            and subject.assessments
            and component_maximum != subject.total_maximum
        ):
            _add_issue(
                report,
                ValidationIssue.SEVERITY_WARNING,
                "SUBJECT",
                "COMPONENT_MAXIMA_MISMATCH",
                f"{subject.subject_code} component maxima do not equal its total maximum.",
                field_name="total_maximum",
                reported_value=subject.total_maximum,
                calculated_value=component_maximum,
            )

    schemas = {tuple(report.subject_codes_for_page(student.source_page)) for student in report.students}
    by_code = {subject.subject_code: subject for subject in report.subjects}
    for codes in sorted(schemas):
        page_subjects = [by_code[code] for code in codes if code in by_code and not by_code[code].is_audit]
        credit_total = sum((subject.credits or Decimal("0") for subject in page_subjects), Decimal("0"))
        marks_total = sum((subject.total_maximum or Decimal("0") for subject in page_subjects), Decimal("0"))
        if report.maximum_credits is not None and credit_total != report.maximum_credits:
            _add_issue(report, ValidationIssue.SEVERITY_WARNING, "REPORT", "MAXIMUM_CREDITS_MISMATCH",
                       "The printed page's subject credits differ from the printed maximum credits.",
                       field_name="maximum_credits", reported_value=report.maximum_credits, calculated_value=credit_total)
        if report.maximum_marks is not None and marks_total != report.maximum_marks:
            _add_issue(report, ValidationIssue.SEVERITY_WARNING, "REPORT", "MAXIMUM_MARKS_MISMATCH",
                       "The printed page's subject maxima differ from the printed maximum marks.",
                       field_name="maximum_marks", reported_value=report.maximum_marks, calculated_value=marks_total)
    if (
        report.maximum_grade_points is not None
        and report.maximum_credits is not None
        and report.maximum_grade_points != report.maximum_credits * Decimal("10")
    ):
        _add_issue(
            report,
            ValidationIssue.SEVERITY_WARNING,
            "REPORT",
            "MAXIMUM_GRADE_POINTS_MISMATCH",
            "Printed maximum grade points differ from maximum credits × 10.",
            field_name="maximum_grade_points",
            reported_value=report.maximum_grade_points,
            calculated_value=report.maximum_credits * Decimal("10"),
        )


def _validate_student(report: ExamReport, student: ReportStudent) -> None:
    issue_start = len(report.validation_issues)
    if student.result_status == "CANCEL":
        student.validation_status = STATUS_SKIPPED
        _clear_calculated_summary(student)
        return

    results_by_subject = {result.subject.subject_code: result for result in student.subject_results}
    expected_codes = report.subject_codes_for_page(student.source_page)
    for subject in report.subjects:
        if subject.subject_code in expected_codes and subject.subject_code not in results_by_subject:
            _add_issue(
                report,
                ValidationIssue.SEVERITY_ERROR,
                "STUDENT",
                "MISSING_SUBJECT_RESULT",
                f"No result was extracted for {subject.subject_code}.",
                student=student,
            )

    for result in student.subject_results:
        _validate_subject_result(report, student, result)
    _validate_student_summary(report, student)

    new_issues = report.validation_issues[issue_start:]
    student.validation_status = _status_for_issues(new_issues)


def _validate_subject_result(
    report: ExamReport, student: ReportStudent, result: SubjectResult
) -> None:
    issue_start = len(report.validation_issues)
    result.component_sum = None
    result.expected_grade = None
    result.expected_grade_point = None
    result.expected_credit_points = None

    if result.subject.is_audit:
        if not result.audit_grade:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "MISSING_AUDIT_GRADE",
                "The audit grade is missing.",
                "audit_grade",
            )
        elif result.audit_grade not in {"AU", "EX", "PASS", "S", "SATISFACTORY"}:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_WARNING,
                "UNKNOWN_AUDIT_GRADE",
                f"Audit grade {result.audit_grade} is not defined by this report template.",
                "audit_grade",
                result.audit_grade,
            )
        result.validation_status = _status_for_issues(
            report.validation_issues[issue_start:]
        )
        return

    expected_assessments = {
        assessment.component_type: assessment
        for assessment in result.subject.assessments
    }
    if report.source_data is not None:
        page_types = report.source_data.data.get("page_assessment_types", {}).get(str(result.source_page), {})
        if result.subject.subject_code in page_types:
            expected_assessments = {key: value for key, value in expected_assessments.items()
                                    if key in page_types[result.subject.subject_code]}
    components = {component.component_type: component for component in result.components}
    values: list[Decimal | None] = []
    components_complete = True
    component_minima_met = True

    for component_type, assessment in expected_assessments.items():
        component = components.get(component_type)
        if component is None:
            components_complete = False
            component_minima_met = False
            values.append(None)
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "MISSING_COMPONENT",
                f"{assessment.display_name} is missing.",
                component_type,
            )
            continue

        value = component.numeric_value
        values.append(value)
        special_code = (component.special_code or "").upper()
        if value is None:
            component_minima_met = False
            if special_code not in KNOWN_ABSENCE_CODES:
                components_complete = False
                _add_result_issue(
                    report,
                    student,
                    result,
                    ValidationIssue.SEVERITY_WARNING,
                    "UNKNOWN_SPECIAL_MARK",
                    f"Special mark code {component.raw_text} is not defined by this report.",
                    component_type,
                    component.raw_text,
                )
            continue

        if value < 0:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "NEGATIVE_MARK",
                f"{assessment.display_name} cannot be negative.",
                component_type,
                value,
            )
        if value > assessment.maximum_marks:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "MARK_ABOVE_MAXIMUM",
                f"{assessment.display_name} {value} exceeds maximum {assessment.maximum_marks}.",
                component_type,
                value,
                assessment.maximum_marks,
            )
        if assessment.minimum_marks is not None and value < assessment.minimum_marks:
            component_minima_met = False

    for component_type, component in components.items():
        if component_type not in expected_assessments:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_WARNING,
                "UNEXPECTED_COMPONENT",
                f"Unexpected component {component_type} was extracted.",
                component_type,
                component.raw_text,
            )

    result.component_sum = calculate_component_sum(values)
    if result.total_value is None:
        _add_result_issue(
            report,
            student,
            result,
            ValidationIssue.SEVERITY_ERROR,
            "MISSING_TOTAL",
            "The reported subject total is missing or non-numeric.",
            "total",
            result.total_raw,
        )
    else:
        if result.total_value < 0:
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "NEGATIVE_TOTAL",
                "The reported total cannot be negative.",
                "total",
                result.total_value,
            )
        if (
            result.subject.total_maximum is not None
            and result.total_value > result.subject.total_maximum
        ):
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_ERROR,
                "TOTAL_ABOVE_MAXIMUM",
                f"Total {result.total_value} exceeds maximum {result.subject.total_maximum}.",
                "total",
                result.total_value,
                result.subject.total_maximum,
            )
        if (
            result.component_sum is not None
            and result.component_sum != result.total_value
        ):
            _add_result_issue(
                report,
                student,
                result,
                ValidationIssue.SEVERITY_WARNING,
                "TOTAL_MISMATCH",
                "The component sum differs from the reported subject total.",
                "total",
                result.total_value,
                result.component_sum,
            )

    source_grade_blank = result.grade_raw == "|"
    if source_grade_blank:
        _add_result_issue(report, student, result, ValidationIssue.SEVERITY_WARNING,
                          "GRADE_NOT_PRINTED", "The source prints | instead of a grade; the marks were retained without inventing a grade.",
                          "grade", result.grade_raw)
    if not result.grade and not source_grade_blank:
        _add_result_issue(
            report,
            student,
            result,
            ValidationIssue.SEVERITY_ERROR,
            "MISSING_GRADE",
            "The subject grade is missing.",
            "grade",
        )
    if result.grade_point is None and not source_grade_blank:
        _add_result_issue(
            report,
            student,
            result,
            ValidationIssue.SEVERITY_ERROR,
            "MISSING_GRADE_POINT",
            "The subject grade point is missing.",
            "grade_point",
        )
    if result.credit_points is None and not source_grade_blank:
        _add_result_issue(
            report,
            student,
            result,
            ValidationIssue.SEVERITY_ERROR,
            "MISSING_CREDIT_POINTS",
            "The subject credit points are missing.",
            "credit_points",
        )

    if components_complete and result.total_value is not None and not source_grade_blank and result.grade != "AU":
        outcome = calculate_grade(
            result.total_value,
            result.subject.total_minimum,
            component_minima_met,
        )
        if outcome is not None:
            result.expected_grade = outcome.grade
            result.expected_grade_point = outcome.grade_point
            result.expected_credit_points = calculate_credit_points(
                result.subject.credits, outcome.grade_point
            )
            if result.grade is not None and result.grade != outcome.grade:
                _add_result_issue(
                    report,
                    student,
                    result,
                    ValidationIssue.SEVERITY_WARNING,
                    "GRADE_MISMATCH",
                    "The reported grade differs from the expected grade.",
                    "grade",
                    result.grade,
                    outcome.grade,
                )
            if (
                result.grade_point is not None
                and result.grade_point != outcome.grade_point
            ):
                _add_result_issue(
                    report,
                    student,
                    result,
                    ValidationIssue.SEVERITY_WARNING,
                    "GRADE_POINT_MISMATCH",
                    "The reported grade point differs from the expected grade point.",
                    "grade_point",
                    result.grade_point,
                    outcome.grade_point,
                )
            if (
                result.credit_points is not None
                and result.credit_points != result.expected_credit_points
            ):
                _add_result_issue(
                    report,
                    student,
                    result,
                    ValidationIssue.SEVERITY_WARNING,
                    "CREDIT_POINTS_MISMATCH",
                    "The reported credit points differ from credits × grade point.",
                    "credit_points",
                    result.credit_points,
                    result.expected_credit_points,
                )
    result.validation_status = _status_for_issues(
        report.validation_issues[issue_start:]
    )


def _validate_student_summary(report: ExamReport, student: ReportStudent) -> None:
    summary = student.summary
    if summary is None:
        _add_issue(
            report,
            ValidationIssue.SEVERITY_ERROR,
            "SUMMARY",
            "MISSING_SUMMARY",
            "The student summary is missing.",
            student=student,
        )
        return

    credit_results = [
        result for result in student.subject_results if not result.subject.is_audit
    ]
    totals = [result.total_value for result in credit_results]
    credit_points = [result.credit_points for result in credit_results]
    grades = [result.grade for result in credit_results]

    summary.calculated_total_marks = _sum_if_complete(totals)
    summary.calculated_total_grade_points = _sum_if_complete(credit_points)
    if all(grade is not None for grade in grades):
        summary.calculated_earned_credits = sum(
            (
                result.subject.credits or Decimal("0")
                for result in credit_results
                if result.grade != "FF"
            ),
            Decimal("0"),
        )
        summary.calculated_status = "FAIL" if "FF" in grades else "PASS"
    else:
        summary.calculated_earned_credits = None
        summary.calculated_status = None

    summary.calculated_sgpa = (
        calculate_sgpa(
            summary.calculated_total_grade_points, report.maximum_credits
        )
        if summary.calculated_status == "PASS"
        else None
    )

    _compare_summary_value(
        report,
        student,
        "TOTAL_MARKS_MISMATCH",
        "total marks",
        "reported_total_marks",
        summary.reported_total_marks,
        summary.calculated_total_marks,
    )
    _compare_summary_value(
        report,
        student,
        "TOTAL_GRADE_POINTS_MISMATCH",
        "total grade points",
        "reported_total_grade_points",
        summary.reported_total_grade_points,
        summary.calculated_total_grade_points,
    )
    _compare_summary_value(
        report,
        student,
        "EARNED_CREDITS_MISMATCH",
        "earned credits",
        "reported_earned_credits",
        summary.reported_earned_credits,
        summary.calculated_earned_credits,
    )
    if summary.calculated_status is not None and summary.calculated_status != student.result_status:
        _add_issue(
            report,
            ValidationIssue.SEVERITY_WARNING,
            "SUMMARY",
            "RESULT_STATUS_MISMATCH",
            "The reported result status differs from the subject-grade result.",
            student=student,
            field_name="result_status",
            reported_value=student.result_status,
            calculated_value=summary.calculated_status,
        )
    if summary.calculated_status == "PASS":
        _compare_summary_value(
            report,
            student,
            "SGPA_MISMATCH",
            "SGPA",
            "reported_sgpa",
            summary.reported_sgpa,
            summary.calculated_sgpa,
        )


def _compare_summary_value(
    report: ExamReport,
    student: ReportStudent,
    code: str,
    label: str,
    field_name: str,
    reported,
    calculated,
) -> None:
    if calculated is not None and reported != calculated:
        _add_issue(
            report,
            ValidationIssue.SEVERITY_WARNING,
            "SUMMARY",
            code,
            f"Reported {label} differs from the calculated value.",
            student=student,
            field_name=field_name,
            reported_value=reported,
            calculated_value=calculated,
        )


def _clear_calculated_summary(student: ReportStudent) -> None:
    if student.summary is None:
        return
    student.summary.calculated_sgpa = None
    student.summary.calculated_total_grade_points = None
    student.summary.calculated_earned_credits = None
    student.summary.calculated_total_marks = None
    student.summary.calculated_status = None
    for result in student.subject_results:
        result.component_sum = None
        result.expected_grade = None
        result.expected_grade_point = None
        result.expected_credit_points = None
        result.validation_status = STATUS_SKIPPED


def _sum_if_complete(values) -> Decimal | None:
    if not values or any(value is None for value in values):
        return None
    return sum(values, Decimal("0"))


def _add_result_issue(
    report,
    student,
    result,
    severity,
    code,
    message,
    field_name,
    reported_value=None,
    calculated_value=None,
) -> None:
    _add_issue(
        report,
        severity,
        "RESULT",
        code,
        f"{result.subject.subject_code}: {message}",
        student=student,
        subject_result=result,
        field_name=field_name,
        reported_value=reported_value,
        calculated_value=calculated_value,
    )


def _add_issue(
    report,
    severity,
    scope,
    code,
    message,
    student=None,
    subject_result=None,
    field_name=None,
    reported_value=None,
    calculated_value=None,
) -> None:
    report.validation_issues.append(
        ValidationIssue(
            severity=severity,
            scope=scope,
            code=code,
            message=message,
            student=student,
            subject_result=subject_result,
            field_name=field_name,
            reported_value=_as_text(reported_value),
            calculated_value=_as_text(calculated_value),
        )
    )


def _as_text(value) -> str | None:
    return None if value is None else str(value)


def _status_for_issues(issues) -> str:
    errors = sum(
        issue.severity == ValidationIssue.SEVERITY_ERROR for issue in issues
    )
    warnings = sum(
        issue.severity == ValidationIssue.SEVERITY_WARNING for issue in issues
    )
    return _status_for_counts(errors, warnings)


def _status_for_counts(errors: int, warnings: int) -> str:
    if errors:
        return STATUS_ERROR
    if warnings:
        return STATUS_WARNING
    return STATUS_VALID
