from dataclasses import dataclass

from ..models import ImportJob


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    name: str
    passed: bool
    detail: str


def audit_import(job: ImportJob) -> list[AcceptanceCheck]:
    """Return non-mutating MVP integrity checks for one import."""
    report = job.report
    checks = [
        AcceptanceCheck(
            "Extracted report",
            report is not None,
            "Report data exists" if report else "No extracted report exists",
        )
    ]
    if report is None:
        return checks

    student_count = len(report.students)
    subject_count = len(report.subjects)
    result_count = report.result_count
    expected_result_count = report.expected_result_count
    summary_count = sum(student.summary is not None for student in report.students)
    unique_seat_count = len({student.seat_number for student in report.students})

    checks.extend(
        [
            AcceptanceCheck(
                "Students detected",
                student_count > 0,
                f"{student_count} student records",
            ),
            AcceptanceCheck(
                "Subjects detected",
                subject_count > 0,
                f"{subject_count} subject definitions",
            ),
            AcceptanceCheck(
                "Unique seat numbers",
                unique_seat_count == student_count,
                f"{unique_seat_count} unique of {student_count}",
            ),
            AcceptanceCheck(
                "Student summaries",
                summary_count == student_count,
                f"{summary_count} summaries for {student_count} students",
            ),
            AcceptanceCheck(
                "Result matrix",
                result_count == expected_result_count,
                f"{result_count} stored; {expected_result_count} expected",
            ),
            AcceptanceCheck(
                "Validation completed",
                report.validation_status != "NOT_VALIDATED",
                report.validation_status.replace("_", " ").title(),
            ),
            AcceptanceCheck(
                "No validation errors",
                report.validation_error_count == 0,
                f"{report.validation_error_count} errors, "
                f"{report.validation_warning_count} warnings",
            ),
            AcceptanceCheck(
                "Confirmation integrity",
                job.status != ImportJob.STATUS_READY or job.confirmed_at is not None,
                (
                    "Confirmed dataset"
                    if job.status == ImportJob.STATUS_READY and job.confirmed_at
                    else (
                        "READY status is missing its confirmation timestamp"
                        if job.status == ImportJob.STATUS_READY
                        else "Confirmation not required for current workflow status"
                    )
                ),
            ),
        ]
    )
    return checks
