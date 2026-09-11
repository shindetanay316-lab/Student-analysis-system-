from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from models import db
from ..models import DataCorrection, ImportJob, ReportStudent, User
from ..parsers.value_normalizer import parse_mark
from .validation_service import ValidationSummary, validate_report


class ReviewError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CorrectionSummary:
    changed_fields: int
    validation: ValidationSummary


@dataclass(slots=True)
class _PendingChange:
    target: object
    attribute: str
    new_value: object
    entity_type: str
    entity_label: str
    student_id: int
    subject_result_id: int | None = None
    result_component_id: int | None = None


def apply_student_corrections(
    job: ImportJob,
    student: ReportStudent,
    form_data,
    changed_by: User,
) -> CorrectionSummary:
    report = job.report
    if report is None or student.report_id != report.id:
        raise ReviewError("The selected student does not belong to this import.")

    changes: list[_PendingChange] = []
    _collect_student_changes(student, form_data, changes)
    _collect_summary_changes(student, form_data, changes)
    _collect_result_changes(student, form_data, changes)

    if not changes:
        raise ReviewError("No changes were detected.")

    reason = (form_data.get("reason") or "").strip()
    if len(reason) < 5:
        raise ReviewError("Enter a correction reason containing at least 5 characters.")
    if len(reason) > 500:
        raise ReviewError("The correction reason cannot exceed 500 characters.")

    for change in changes:
        previous_value = getattr(change.target, change.attribute)
        correction = DataCorrection(
            report=report,
            student_id=change.student_id,
            subject_result_id=change.subject_result_id,
            result_component_id=change.result_component_id,
            changed_by_id=changed_by.user_id,
            entity_type=change.entity_type,
            entity_label=change.entity_label,
            field_name=change.attribute,
            original_value=_original_value(report.id, change, previous_value),
            previous_value=_as_text(previous_value),
            new_value=_as_text(change.new_value),
            reason=reason,
        )
        setattr(change.target, change.attribute, change.new_value)
        db.session.add(correction)

    job.status = ImportJob.STATUS_REVIEW_REQUIRED
    job.confirmed_at = None
    job.confirmed_by_id = None
    job.confirmation_notes = None
    validation = validate_report(report)
    return CorrectionSummary(len(changes), validation)


def confirm_import(
    job: ImportJob,
    confirmed_by: User,
    acknowledge_warnings: bool,
    notes: str | None = None,
) -> None:
    report = job.report
    if report is None:
        raise ReviewError("Extract the PDF before confirming the import.")
    if report.validation_status == "NOT_VALIDATED":
        raise ReviewError("Run validation before confirming the import.")
    if report.validation_error_count:
        raise ReviewError("Resolve all validation errors before confirming the import.")
    if report.validation_warning_count and not acknowledge_warnings:
        raise ReviewError("Acknowledge the remaining warnings before confirmation.")

    cleaned_notes = (notes or "").strip()
    if len(cleaned_notes) > 1000:
        raise ReviewError("Confirmation notes cannot exceed 1000 characters.")

    job.status = ImportJob.STATUS_READY
    job.confirmed_at = datetime.now(timezone.utc)
    job.confirmed_by_id = confirmed_by.user_id
    job.confirmation_notes = cleaned_notes or None


def _collect_student_changes(student, form_data, changes) -> None:
    name = (form_data.get("student_name") or "").strip()
    if not name:
        raise ReviewError("Student name is required.")
    if len(name) > 255:
        raise ReviewError("Student name cannot exceed 255 characters.")
    _append_change(
        changes,
        student,
        "name",
        name,
        "REPORT_STUDENT",
        student.seat_number,
        student.id,
    )

    result_status = (form_data.get("student_result_status") or "").strip().upper()
    if result_status not in {"PASS", "FAIL", "CANCEL"}:
        raise ReviewError("Student result status must be PASS, FAIL, or CANCEL.")
    _append_change(
        changes,
        student,
        "result_status",
        result_status,
        "REPORT_STUDENT",
        student.seat_number,
        student.id,
    )
    if student.summary is not None:
        _append_change(
            changes,
            student.summary,
            "reported_status",
            result_status,
            "STUDENT_SUMMARY",
            student.seat_number,
            student.id,
        )


def _collect_summary_changes(student, form_data, changes) -> None:
    summary = student.summary
    if summary is None:
        return
    fields = {
        "reported_sgpa": "SGPA",
        "reported_total_grade_points": "total grade points",
        "reported_earned_credits": "earned credits",
        "reported_total_marks": "total marks",
    }
    for attribute, label in fields.items():
        new_value = _parse_decimal(
            form_data.get(f"summary_{attribute}"),
            f"Reported {label}",
        )
        _append_change(
            changes,
            summary,
            attribute,
            new_value,
            "STUDENT_SUMMARY",
            student.seat_number,
            student.id,
        )


def _collect_result_changes(student, form_data, changes) -> None:
    for result in student.subject_results:
        label = result.subject.subject_code
        if result.subject.is_audit:
            audit_grade = _optional_upper(
                form_data.get(f"result_audit_grade_{result.id}"), 30
            )
            _append_change(
                changes,
                result,
                "audit_grade",
                audit_grade,
                "SUBJECT_RESULT",
                label,
                student.id,
                result.id,
            )
            continue

        total_value, total_special, parsed_carried = _parse_mark_input(
            form_data.get(f"result_total_{result.id}")
        )
        total_carried = (
            form_data.get(f"result_total_carried_{result.id}") == "1"
            or parsed_carried
        )
        _append_result_change(
            changes, result, "total_value", total_value, student.id, label
        )
        _append_result_change(
            changes,
            result,
            "total_special_code",
            total_special,
            student.id,
            label,
        )
        _append_result_change(
            changes,
            result,
            "total_is_carried_forward",
            total_carried,
            student.id,
            label,
        )

        text_fields = {
            "grade": (20, True),
            "audit_grade": (30, True),
        }
        for attribute, (maximum, uppercase) in text_fields.items():
            value = form_data.get(f"result_{attribute}_{result.id}")
            parsed = (
                _optional_upper(value, maximum)
                if uppercase
                else _optional_text(value, maximum)
            )
            _append_result_change(
                changes, result, attribute, parsed, student.id, label
            )

        decimal_fields = {
            "grade_point": "grade point",
            "credit_points": "credit points",
            "grace_marks": "grace marks",
        }
        for attribute, field_label in decimal_fields.items():
            value = _parse_decimal(
                form_data.get(f"result_{attribute}_{result.id}"),
                f"{label} {field_label}",
            )
            _append_result_change(
                changes, result, attribute, value, student.id, label
            )

        for component in result.components:
            numeric_value, special_code, parsed_carried = _parse_mark_input(
                form_data.get(f"component_value_{component.id}")
            )
            carried = (
                form_data.get(f"component_carried_{component.id}") == "1"
                or parsed_carried
            )
            component_label = f"{label} / {component.component_type}"
            _append_component_change(
                changes,
                component,
                "numeric_value",
                numeric_value,
                student.id,
                result.id,
                component_label,
            )
            _append_component_change(
                changes,
                component,
                "special_code",
                special_code,
                student.id,
                result.id,
                component_label,
            )
            _append_component_change(
                changes,
                component,
                "is_carried_forward",
                carried,
                student.id,
                result.id,
                component_label,
            )


def _append_result_change(
    changes, result, attribute, new_value, student_id, label
) -> None:
    _append_change(
        changes,
        result,
        attribute,
        new_value,
        "SUBJECT_RESULT",
        label,
        student_id,
        result.id,
    )


def _append_component_change(
    changes,
    component,
    attribute,
    new_value,
    student_id,
    result_id,
    label,
) -> None:
    _append_change(
        changes,
        component,
        attribute,
        new_value,
        "RESULT_COMPONENT",
        label,
        student_id,
        result_id,
        component.id,
    )


def _append_change(
    changes,
    target,
    attribute,
    new_value,
    entity_type,
    entity_label,
    student_id,
    subject_result_id=None,
    result_component_id=None,
) -> None:
    if getattr(target, attribute) == new_value:
        return
    changes.append(
        _PendingChange(
            target=target,
            attribute=attribute,
            new_value=new_value,
            entity_type=entity_type,
            entity_label=entity_label,
            student_id=student_id,
            subject_result_id=subject_result_id,
            result_component_id=result_component_id,
        )
    )


def _original_value(report_id, change, fallback):
    statement = select(DataCorrection).where(
        DataCorrection.report_id == report_id,
        DataCorrection.entity_type == change.entity_type,
        DataCorrection.field_name == change.attribute,
    )
    if change.result_component_id is not None:
        statement = statement.where(
            DataCorrection.result_component_id == change.result_component_id
        )
    elif change.subject_result_id is not None:
        statement = statement.where(
            DataCorrection.subject_result_id == change.subject_result_id
        )
    else:
        statement = statement.where(DataCorrection.student_id == change.student_id)
    first = db.session.scalar(statement.order_by(DataCorrection.id.asc()).limit(1))
    return first.original_value if first is not None else _as_text(fallback)


def _parse_mark_input(value) -> tuple[Decimal | None, str | None, bool]:
    text = (value or "").strip()
    if not text:
        return None, None, False
    parsed = parse_mark(text)
    if parsed is None:
        return None, None, False
    return (
        parsed.numeric_value,
        parsed.special_code.upper() if parsed.special_code else None,
        parsed.is_carried_forward,
    )


def _parse_decimal(value, label) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as error:
        raise ReviewError(f"{label} must be a number or left blank.") from error
    if not parsed.is_finite():
        raise ReviewError(f"{label} must be a finite number.")
    return parsed


def _optional_upper(value, maximum) -> str | None:
    parsed = _optional_text(value, maximum)
    return parsed.upper() if parsed else None


def _optional_text(value, maximum) -> str | None:
    parsed = (value or "").strip()
    if not parsed:
        return None
    if len(parsed) > maximum:
        raise ReviewError(f"A corrected text value exceeds {maximum} characters.")
    return parsed


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)
