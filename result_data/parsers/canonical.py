from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class ParsedValue:
    raw_text: str
    numeric_value: Decimal | None
    is_carried_forward: bool = False
    special_code: str | None = None


@dataclass(slots=True)
class ParsedAssessment:
    component_type: str
    display_name: str
    maximum_marks: Decimal
    minimum_marks: Decimal | None
    display_order: int
    source_row: str


@dataclass(slots=True)
class ParsedSubject:
    code: str
    name: str
    display_order: int
    credits: Decimal | None
    is_audit: bool
    total_maximum: Decimal | None
    total_minimum: Decimal | None
    assessments: list[ParsedAssessment] = field(default_factory=list)


@dataclass(slots=True)
class ParsedSubjectResult:
    subject_code: str
    source_page: int
    components: list[tuple[str, ParsedValue]] = field(default_factory=list)
    total: ParsedValue | None = None
    grade_raw: str | None = None
    grade: str | None = None
    grade_point: Decimal | None = None
    credit_points: Decimal | None = None
    grace_marks: Decimal | None = None
    audit_grade: str | None = None
    attempt_session: str | None = None


@dataclass(slots=True)
class ParsedSummary:
    reported_sgpa: Decimal | None = None
    reported_total_grade_points: Decimal | None = None
    reported_earned_credits: Decimal | None = None
    reported_total_marks: Decimal | None = None
    reported_status: str | None = None
    additional_values: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParsedStudent:
    seat_number: str
    name: str
    gender_marker: str | None
    center_code: str | None
    registration_scope: str | None
    institute_code: str | None
    institute_name: str | None
    source_page: int
    result_status: str
    subject_results: list[ParsedSubjectResult]
    summary: ParsedSummary


@dataclass(slots=True)
class ParsedReport:
    parser_name: str
    parser_version: str
    source_filename: str
    page_count: int
    university: str
    examination_title: str
    programme: str
    branch: str | None
    semester: str | None
    examination_session: str | None
    examination_type: str | None
    institute_code: str | None
    institute_name: str | None
    maximum_marks: Decimal | None
    maximum_credits: Decimal | None
    maximum_grade_points: Decimal | None
    report_generated_at_raw: str | None
    subjects: list[ParsedSubject]
    students: list[ParsedStudent]
    page_subject_codes: dict[int, list[str]] = field(default_factory=dict)
    page_assessment_types: dict[int, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def subject_result_count(self) -> int:
        return sum(len(student.subject_results) for student in self.students)
