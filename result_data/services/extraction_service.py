from pathlib import Path

from models import db
from ..models import (
    ExamReport,
    ImportJob,
    ReportStudent,
    ResultComponent,
    StudentSummary,
    Subject,
    SubjectAssessment,
    SubjectResult,
    ResultSourceData,
)
from ..parsers import DBATUCrystalReportParser, PDFExtractionError, UnsupportedPDFError
from .validation_service import validate_report


class ExtractionFailedError(RuntimeError):
    pass


def extract_import_job(
    job: ImportJob,
    upload_folder: str | Path,
    parser: DBATUCrystalReportParser | None = None,
) -> ExamReport:
    """Parse one uploaded PDF and atomically replace its extracted records."""
    pdf_path = Path(upload_folder) / job.stored_filename
    if not pdf_path.is_file():
        message = "The stored PDF could not be found on the server."
        _mark_failed(job.id, message)
        raise ExtractionFailedError(message)

    parser = parser or DBATUCrystalReportParser()
    job.status = ImportJob.STATUS_EXTRACTING
    job.error_message = None
    db.session.commit()

    try:
        parsed_report = parser.parse(pdf_path)
        current_job = db.session.get(ImportJob, job.id)
        if current_job is None:
            raise ExtractionFailedError("The import job no longer exists.")

        if current_job.report is not None:
            db.session.delete(current_job.report)
            db.session.flush()

        report = _build_report(current_job, parsed_report)
        current_job.page_count = parsed_report.page_count
        current_job.parser_version = parsed_report.parser_version
        current_job.status = ImportJob.STATUS_REVIEW_REQUIRED
        current_job.error_message = None
        current_job.confirmed_at = None
        current_job.confirmed_by_id = None
        current_job.confirmation_notes = None
        db.session.add(report)
        db.session.flush()
        validate_report(report)
        db.session.commit()
        return report
    except (PDFExtractionError, UnsupportedPDFError, ExtractionFailedError) as error:
        db.session.rollback()
        _mark_failed(job.id, str(error))
        raise ExtractionFailedError(str(error)) from error
    except Exception as error:
        db.session.rollback()
        message = "Extraction failed because the report structure could not be stored."
        _mark_failed(job.id, message)
        raise ExtractionFailedError(message) from error


def _mark_failed(job_id: int, message: str) -> None:
    failed_job = db.session.get(ImportJob, job_id)
    if failed_job is None:
        return
    failed_job.status = ImportJob.STATUS_FAILED
    failed_job.error_message = message[:2000]
    db.session.commit()


def _build_report(import_job: ImportJob, parsed) -> ExamReport:
    report = ExamReport(
        import_job=import_job,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        university=parsed.university,
        examination_title=parsed.examination_title,
        programme=parsed.programme,
        branch=parsed.branch,
        semester=parsed.semester,
        examination_session=parsed.examination_session,
        examination_type=parsed.examination_type,
        institute_code=parsed.institute_code,
        institute_name=parsed.institute_name,
        maximum_marks=parsed.maximum_marks,
        maximum_credits=parsed.maximum_credits,
        maximum_grade_points=parsed.maximum_grade_points,
        report_generated_at_raw=parsed.report_generated_at_raw,
    )
    if parsed.page_subject_codes:
        report.source_data = ResultSourceData(data={
            "page_subject_codes": {str(page): codes for page, codes in parsed.page_subject_codes.items()},
            "page_assessment_types": {str(page): subjects for page, subjects in parsed.page_assessment_types.items()},
            "additional_summaries": {
                student.seat_number: student.summary.additional_values
                for student in parsed.students if student.summary.additional_values
            },
        })

    subjects_by_code: dict[str, Subject] = {}
    assessments_by_subject: dict[str, dict[str, SubjectAssessment]] = {}
    for parsed_subject in parsed.subjects:
        subject = Subject(
            subject_code=parsed_subject.code,
            subject_name=parsed_subject.name,
            display_order=parsed_subject.display_order,
            credits=parsed_subject.credits,
            is_audit=parsed_subject.is_audit,
            total_maximum=parsed_subject.total_maximum,
            total_minimum=parsed_subject.total_minimum,
        )
        report.subjects.append(subject)
        subjects_by_code[parsed_subject.code] = subject
        assessment_map: dict[str, SubjectAssessment] = {}
        for parsed_assessment in parsed_subject.assessments:
            assessment = SubjectAssessment(
                component_type=parsed_assessment.component_type,
                display_name=parsed_assessment.display_name,
                source_row=parsed_assessment.source_row,
                maximum_marks=parsed_assessment.maximum_marks,
                minimum_marks=parsed_assessment.minimum_marks,
                display_order=parsed_assessment.display_order,
            )
            subject.assessments.append(assessment)
            assessment_map[parsed_assessment.component_type] = assessment
        assessments_by_subject[parsed_subject.code] = assessment_map

    for parsed_student in parsed.students:
        student = ReportStudent(
            seat_number=parsed_student.seat_number,
            name=parsed_student.name,
            gender_marker=parsed_student.gender_marker,
            center_code=parsed_student.center_code,
            registration_scope=parsed_student.registration_scope,
            institute_code=parsed_student.institute_code,
            institute_name=parsed_student.institute_name,
            source_page=parsed_student.source_page,
            result_status=parsed_student.result_status,
        )
        report.students.append(student)
        student.summary = StudentSummary(
            reported_sgpa=parsed_student.summary.reported_sgpa,
            reported_total_grade_points=(
                parsed_student.summary.reported_total_grade_points
            ),
            reported_earned_credits=parsed_student.summary.reported_earned_credits,
            reported_total_marks=parsed_student.summary.reported_total_marks,
            reported_status=parsed_student.summary.reported_status,
        )

        for parsed_result in parsed_student.subject_results:
            subject = subjects_by_code.get(parsed_result.subject_code)
            if subject is None:
                raise ExtractionFailedError(
                    f"Unknown subject {parsed_result.subject_code} in student result."
                )
            result = SubjectResult(
                subject=subject,
                source_page=parsed_result.source_page,
                total_raw=(parsed_result.total.raw_text if parsed_result.total else None),
                total_value=(
                    parsed_result.total.numeric_value if parsed_result.total else None
                ),
                total_is_carried_forward=(
                    parsed_result.total.is_carried_forward
                    if parsed_result.total
                    else False
                ),
                total_special_code=(
                    parsed_result.total.special_code if parsed_result.total else None
                ),
                grade_raw=parsed_result.grade_raw,
                grade=parsed_result.grade,
                grade_point=parsed_result.grade_point,
                credit_points=parsed_result.credit_points,
                grace_marks=parsed_result.grace_marks,
                audit_grade=parsed_result.audit_grade,
                attempt_session=parsed_result.attempt_session,
            )
            student.subject_results.append(result)

            for component_type, parsed_value in parsed_result.components:
                assessment = assessments_by_subject[parsed_result.subject_code].get(
                    component_type
                )
                if assessment is None:
                    raise ExtractionFailedError(
                        f"Unknown component {component_type} for "
                        f"{parsed_result.subject_code}."
                    )
                result.components.append(
                    ResultComponent(
                        assessment=assessment,
                        component_type=component_type,
                        raw_text=parsed_value.raw_text,
                        numeric_value=parsed_value.numeric_value,
                        is_carried_forward=parsed_value.is_carried_forward,
                        special_code=parsed_value.special_code,
                    )
                )

    return report
