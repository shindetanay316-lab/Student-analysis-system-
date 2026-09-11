import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pymupdf

from .canonical import (
    ParsedAssessment,
    ParsedReport,
    ParsedStudent,
    ParsedSubject,
    ParsedSubjectResult,
    ParsedSummary,
    ParsedValue,
)
from .exceptions import PDFExtractionError, UnsupportedPDFError
from .value_normalizer import normalize_attempt, parse_grade, parse_mark, to_decimal


Word = tuple[float, float, float, float, str, int, int, int]


@dataclass(slots=True)
class SubjectColumn:
    subject: ParsedSubject
    center: float
    left: float
    right: float


@dataclass(slots=True)
class PageLayout:
    columns: list[SubjectColumn]
    header_rows: dict[str, list[float]]
    student_row_offsets: dict[str, float]


class DBATUCrystalReportParser:
    NAME = "DBATU Crystal Reports"
    VERSION = "1.1.0"

    REQUIRED_ANCHORS = (
        "Dr. Babasaheb Ambedkar Technological University",
        "EXAMINATION",
        "Seat No.",
        "CREDIT",
        "ESE TOTAL",
        "Total Marks",
    )

    SEAT_PATTERN = re.compile(r"^\d{12,20}$")
    SUBJECT_LINE_PATTERN = re.compile(
        r"^(?P<code>(?=[A-Z0-9]*\d)[A-Z0-9]{8,})\s*:\s*(?P<name>.+?)"
        r"(?:\s*\(Credit\s*:\s*(?P<credit>\d+(?:\.\d+)?)\s*\))?$",
        re.IGNORECASE,
    )
    GENDER_PATTERN = re.compile(r"^\((?P<gender>[A-Z])\)\s*")

    FIRST_STUDENT_VALUE_OFFSET = 10.54
    STUDENT_VALUE_ROW_STEP = 18.60
    GRADE_AFTER_TOTAL_OFFSET = 21.76
    ATTEMPT_AFTER_GRADE_OFFSET = 11.40

    def can_parse(self, pdf_path: str | Path) -> bool:
        try:
            with pymupdf.open(pdf_path) as document:
                if document.needs_pass or document.page_count == 0:
                    return False
                first_page_text = document[0].get_text("text")
        except (pymupdf.FileDataError, RuntimeError):
            return False

        return all(anchor in first_page_text for anchor in self.REQUIRED_ANCHORS)

    def parse(self, pdf_path: str | Path) -> ParsedReport:
        source_path = Path(pdf_path)
        try:
            document = pymupdf.open(source_path)
        except (pymupdf.FileDataError, RuntimeError) as error:
            raise UnsupportedPDFError("The uploaded file is not a readable PDF.") from error

        with document:
            if document.needs_pass:
                raise UnsupportedPDFError("Password-protected PDFs are not supported.")
            if document.page_count == 0:
                raise UnsupportedPDFError("The PDF contains no pages.")
            if not self.can_parse(source_path):
                raise UnsupportedPDFError(
                    "The PDF does not match the supported DBATU Crystal Reports format."
                )

            first_page = document[0]
            first_text = first_page.get_text("text")
            subject_catalog = self._parse_subject_catalog(first_text)
            first_layout = self._parse_page_layout(first_page, subject_catalog, True)
            subjects = [column.subject for column in first_layout.columns]

            students: list[ParsedStudent] = []
            seen_seat_numbers: set[str] = set()
            for page_number, page in enumerate(document, start=1):
                layout = self._parse_page_layout(page, subjects, False)
                page_students = self._parse_page_students(page, page_number, layout)
                for student in page_students:
                    if student.seat_number in seen_seat_numbers:
                        raise PDFExtractionError(
                            f"Duplicate seat number {student.seat_number} was detected."
                        )
                    seen_seat_numbers.add(student.seat_number)
                students.extend(page_students)

            if not students:
                raise PDFExtractionError("No student records were detected in the PDF.")

            metadata = self._parse_metadata(first_text, document[-1].get_text("text"))
            first_student = students[0]
            return ParsedReport(
                parser_name=self.NAME,
                parser_version=self.VERSION,
                source_filename=source_path.name,
                page_count=document.page_count,
                university=metadata["university"],
                examination_title=metadata["examination_title"],
                programme=metadata["programme"],
                branch=metadata["branch"],
                semester=metadata["semester"],
                examination_session=metadata["examination_session"],
                examination_type=metadata["examination_type"],
                institute_code=first_student.institute_code,
                institute_name=first_student.institute_name,
                maximum_marks=metadata["maximum_marks"],
                maximum_credits=metadata["maximum_credits"],
                maximum_grade_points=metadata["maximum_grade_points"],
                report_generated_at_raw=metadata["report_generated_at_raw"],
                subjects=subjects,
                students=students,
            )

    def _parse_subject_catalog(self, page_text: str) -> list[ParsedSubject]:
        subjects: list[ParsedSubject] = []
        pending_subject: ParsedSubject | None = None
        for line in page_text.splitlines():
            cleaned_line = line.strip()
            match = self.SUBJECT_LINE_PATTERN.fullmatch(cleaned_line)
            if not match:
                continuation = re.fullmatch(
                    r"(?P<name>.+?)\s*\(Credit\s*:\s*(?P<credit>\d+(?:\.\d+)?)\s*\)",
                    cleaned_line,
                    re.IGNORECASE,
                )
                if pending_subject is not None and continuation:
                    pending_subject.name = (
                        f"{pending_subject.name} {continuation.group('name').strip()}"
                    )
                    pending_subject.credits = to_decimal(continuation.group("credit"))
                    pending_subject = None
                continue
            name = match.group("name").strip()
            credit = to_decimal(match.group("credit"))
            subject = ParsedSubject(
                code=match.group("code").upper(),
                name=name,
                display_order=len(subjects) + 1,
                credits=credit,
                is_audit=False,
                total_maximum=None,
                total_minimum=None,
            )
            subjects.append(subject)
            pending_subject = subject if credit is None else None

        if not subjects:
            raise PDFExtractionError("No subject definitions were found on the first page.")
        return subjects

    def _parse_page_layout(
        self,
        page: pymupdf.Page,
        subjects: list[ParsedSubject],
        configure_subjects: bool,
    ) -> PageLayout:
        words = page.get_text("words")
        header_rows = self._header_rows(words)
        student_row_offsets = self._student_row_offsets(header_rows)
        credit_y = header_rows["CREDIT"][0]

        code_words = [
            word
            for word in words
            if 100 < word[0] < page.rect.width * 0.75
            and credit_y - 30 < word[1] < credit_y - 20
            and len(word[4]) >= 8
            and any(character.isalpha() for character in word[4])
            and any(character.isdigit() for character in word[4])
        ]
        code_words.sort(key=lambda word: word[0])
        if len(code_words) != len(subjects):
            raise PDFExtractionError(
                f"Expected {len(subjects)} subject columns but detected {len(code_words)}."
            )

        centers = [(word[0] + word[2]) / 2 for word in code_words]
        # The area left of x=100 contains row labels such as ``TOTAL``.  Keeping
        # it outside the first subject column prevents labels being merged with
        # the first student's/configuration value.
        boundaries = [100.0]
        boundaries.extend(
            (centers[index] + centers[index + 1]) / 2
            for index in range(len(centers) - 1)
        )
        boundaries.append(page.rect.width * 0.75)

        columns: list[SubjectColumn] = []
        for index, (subject, base_word, center) in enumerate(
            zip(subjects, code_words, centers, strict=True)
        ):
            continuation = self._cell_text(
                words,
                boundaries[index],
                boundaries[index + 1],
                credit_y - 14.82,
                tolerance=2.5,
            )
            displayed_code = f"{base_word[4]}{continuation or ''}".replace(" ", "")
            if displayed_code != subject.code:
                raise PDFExtractionError(
                    f"Subject column {index + 1} contains {displayed_code}, "
                    f"but the first-page definition contains {subject.code}."
                )

            if configure_subjects:
                self._configure_subject(
                    subject,
                    words,
                    boundaries[index],
                    boundaries[index + 1],
                    header_rows,
                )

            columns.append(
                SubjectColumn(
                    subject=subject,
                    center=center,
                    left=boundaries[index],
                    right=boundaries[index + 1],
                )
            )

        return PageLayout(
            columns=columns,
            header_rows=header_rows,
            student_row_offsets=student_row_offsets,
        )

    def _header_rows(self, words: list[Word]) -> dict[str, list[float]]:
        grouped: list[tuple[float, list[str]]] = []
        for word in sorted(
            (word for word in words if word[0] < 100 and 80 < word[1] < 270),
            key=lambda item: (item[1], item[0]),
        ):
            if not grouped or abs(grouped[-1][0] - word[1]) > 1.0:
                grouped.append((word[1], [word[4]]))
            else:
                grouped[-1][1].append(word[4])

        rows: dict[str, list[float]] = {}
        accepted = {"CREDIT", "ESE TOTAL", "CA INTERNAL", "MID INTERNAL", "INT TOTAL", "TOTAL"}
        for y_position, tokens in grouped:
            label = " ".join(tokens)
            if label in accepted:
                rows.setdefault(label, []).append(y_position)

        required = {"CREDIT", "ESE TOTAL", "TOTAL"}
        missing = required - rows.keys()
        if missing:
            raise PDFExtractionError(
                f"Missing required result header rows: {', '.join(sorted(missing))}."
            )
        return rows

    def _student_row_offsets(
        self, header_rows: dict[str, list[float]]
    ) -> dict[str, float]:
        """Map printed header rows to their corresponding student-value rows.

        DBATU Crystal Reports use the same vertical rhythm but may print one or
        two ESE rows and may omit an internal component. Deriving the offsets
        from the detected header prevents valid layouts from being interpreted
        using marks positions from a different semester.
        """
        ordered_sources: list[tuple[float, str]] = []
        ordered_sources.extend(
            (y_position, f"ESE_{index}")
            for index, y_position in enumerate(header_rows.get("ESE TOTAL", []))
        )
        for label, source_row in (
            ("CA INTERNAL", "CA"),
            ("MID INTERNAL", "MID"),
            ("INT TOTAL", "INTERNAL_TOTAL"),
        ):
            ordered_sources.extend(
                (y_position, source_row)
                for y_position in header_rows.get(label, [])
            )

        ordered_sources.sort(key=lambda item: item[0])
        if not ordered_sources:
            raise PDFExtractionError("No assessment rows were detected in the result header.")

        offsets = {
            source_row: self.FIRST_STUDENT_VALUE_OFFSET
            + index * self.STUDENT_VALUE_ROW_STEP
            for index, (_y_position, source_row) in enumerate(ordered_sources)
        }
        total_offset = (
            self.FIRST_STUDENT_VALUE_OFFSET
            + len(ordered_sources) * self.STUDENT_VALUE_ROW_STEP
        )
        offsets["TOTAL"] = total_offset
        offsets["GRADE"] = total_offset + self.GRADE_AFTER_TOTAL_OFFSET
        offsets["ATTEMPT"] = offsets["GRADE"] + self.ATTEMPT_AFTER_GRADE_OFFSET
        return offsets

    def _configure_subject(
        self,
        subject: ParsedSubject,
        words: list[Word],
        left: float,
        right: float,
        rows: dict[str, list[float]],
    ) -> None:
        credit_text = self._cell_text(words, left, right, rows["CREDIT"][0])
        header_credit = to_decimal(credit_text)
        if header_credit is not None:
            if subject.credits is not None and subject.credits != header_credit:
                raise PDFExtractionError(
                    f"Credit mismatch for {subject.code}: "
                    f"definition={subject.credits}, header={header_credit}."
                )
            subject.credits = header_credit

        display_order = 1
        for row_index, y_position in enumerate(rows["ESE TOTAL"]):
            value = self._cell_text(words, left, right, y_position)
            parsed = self._parse_maximum_minimum(value)
            if parsed:
                subject.assessments.append(
                    ParsedAssessment(
                        component_type="ESE",
                        display_name="ESE Total",
                        maximum_marks=parsed[0],
                        minimum_marks=parsed[1],
                        display_order=display_order,
                        source_row=f"ESE_{row_index}",
                    )
                )
                display_order += 1

        for label, component_type, display_name in (
            ("CA INTERNAL", "CA", "CA Internal"),
            ("MID INTERNAL", "MID", "MID Internal"),
            ("INT TOTAL", "INTERNAL_TOTAL", "Internal Total"),
        ):
            if label not in rows:
                continue
            value = self._cell_text(words, left, right, rows[label][0])
            maximum = to_decimal(value)
            if maximum is not None:
                subject.assessments.append(
                    ParsedAssessment(
                        component_type=component_type,
                        display_name=display_name,
                        maximum_marks=maximum,
                        minimum_marks=None,
                        display_order=display_order,
                        source_row=component_type,
                    )
                )
                display_order += 1

        total_text = self._cell_text(words, left, right, rows["TOTAL"][0])
        total_limits = self._parse_maximum_minimum(total_text)
        subject.is_audit = total_text == "GRADE"
        if subject.is_audit:
            subject.credits = subject.credits or Decimal("0")
        elif total_limits:
            subject.total_maximum, subject.total_minimum = total_limits
        else:
            raise PDFExtractionError(
                f"No total-mark configuration was found for {subject.code}."
            )

    def _parse_page_students(
        self, page: pymupdf.Page, page_number: int, layout: PageLayout
    ) -> list[ParsedStudent]:
        words = page.get_text("words")
        seat_words = sorted(
            [
                word
                for word in words
                if word[0] < 105 and self.SEAT_PATTERN.fullmatch(word[4])
            ],
            key=lambda word: word[1],
        )

        students: list[ParsedStudent] = []
        for index, seat_word in enumerate(seat_words):
            block_end = (
                seat_words[index + 1][1] - 1
                if index + 1 < len(seat_words)
                else page.rect.height - 55
            )
            students.append(
                self._parse_student(page, page_number, words, seat_word, block_end, layout)
            )
        return students

    def _parse_student(
        self,
        page: pymupdf.Page,
        page_number: int,
        words: list[Word],
        seat_word: Word,
        block_end: float,
        layout: PageLayout,
    ) -> ParsedStudent:
        start_y = seat_word[1]
        identity_words = sorted(
            [
                word
                for word in words
                if abs(word[1] - start_y) <= 2.2
                and word[0] > 100
                and word[0] < page.rect.width * 0.75
            ],
            key=lambda word: word[0],
        )
        institute_index = next(
            (
                index
                for index, word in enumerate(identity_words)
                if re.fullmatch(r"\d{5}", word[4])
            ),
            None,
        )
        if institute_index is None:
            raise PDFExtractionError(
                f"Could not separate name and institute for seat {seat_word[4]}."
            )

        printed_name = " ".join(word[4] for word in identity_words[:institute_index])
        gender_match = self.GENDER_PATTERN.match(printed_name)
        gender_marker = gender_match.group("gender") if gender_match else None
        name = self.GENDER_PATTERN.sub("", printed_name).strip()

        institute_code = identity_words[institute_index][4]
        institute_tokens = [word[4] for word in identity_words[institute_index + 1 :]]
        if institute_tokens and institute_tokens[0] == "-":
            institute_tokens = institute_tokens[1:]
        institute_name = " ".join(institute_tokens) or None

        status = self._status_at(words, start_y, page.rect.width)
        if status is None:
            raise PDFExtractionError(f"No result status was found for seat {seat_word[4]}.")

        center_code, registration_scope = self._center_details(words, start_y)
        summary = self._summary(words, start_y, page.rect.width, status)

        subject_results: list[ParsedSubjectResult] = []
        for column in layout.columns:
            components: list[tuple[str, ParsedValue]] = []
            for assessment in column.subject.assessments:
                target_y = start_y + layout.student_row_offsets[assessment.source_row]
                raw_value = self._cell_text(
                    words, column.left, column.right, target_y, tolerance=2.5
                )
                parsed_value = parse_mark(raw_value)
                if parsed_value is not None:
                    components.append((assessment.component_type, parsed_value))

            total_raw = self._cell_text(
                words,
                column.left,
                column.right,
                start_y + layout.student_row_offsets["TOTAL"],
                tolerance=2.5,
            )
            total = parse_mark(total_raw)
            grade_raw = self._cell_text(
                words,
                column.left,
                column.right,
                start_y + layout.student_row_offsets["GRADE"],
                tolerance=2.5,
            )
            parsed_grade = parse_grade(grade_raw)
            audit_grade = (
                grade_raw
                if column.subject.is_audit and grade_raw and grade_raw != "|"
                else None
            )
            attempt = self._attempt_for_column(
                words,
                column,
                start_y,
                block_end,
                status,
                layout.student_row_offsets,
            )

            subject_results.append(
                ParsedSubjectResult(
                    subject_code=column.subject.code,
                    source_page=page_number,
                    components=components,
                    total=total,
                    grade_raw=grade_raw if parsed_grade else None,
                    grade=parsed_grade.grade if parsed_grade else None,
                    grade_point=(parsed_grade.grade_point if parsed_grade else None),
                    credit_points=(
                        parsed_grade.credit_points if parsed_grade else None
                    ),
                    grace_marks=(parsed_grade.grace_marks if parsed_grade else None),
                    audit_grade=audit_grade,
                    attempt_session=attempt,
                )
            )

        return ParsedStudent(
            seat_number=seat_word[4],
            name=name,
            gender_marker=gender_marker,
            center_code=center_code,
            registration_scope=registration_scope,
            institute_code=institute_code,
            institute_name=institute_name,
            source_page=page_number,
            result_status=status,
            subject_results=subject_results,
            summary=summary,
        )

    def _attempt_for_column(
        self,
        words: list[Word],
        column: SubjectColumn,
        start_y: float,
        block_end: float,
        status: str,
        row_offsets: dict[str, float],
    ) -> str | None:
        target_y = start_y + row_offsets["ATTEMPT"]
        attempt = self._cell_text(
            words, column.left, column.right, target_y, tolerance=3.0
        )
        if attempt:
            return normalize_attempt(attempt)

        if status != "CANCEL":
            return None

        candidate_rows = sorted(
            {
                round(word[1], 1)
                for word in words
                if start_y < word[1] < block_end
                and column.left <= (word[0] + word[2]) / 2 < column.right
                and word[4] in {"Summer", "Winter"}
            }
        )
        if not candidate_rows:
            return None
        return normalize_attempt(
            self._cell_text(
                words,
                column.left,
                column.right,
                candidate_rows[-1],
                tolerance=3.0,
            )
        )

    def _status_at(
        self, words: list[Word], start_y: float, page_width: float
    ) -> str | None:
        statuses = {"PASS", "FAIL", "CANCEL", "WITHHELD", "RESERVED"}
        return next(
            (
                word[4]
                for word in words
                if word[0] > page_width * 0.88
                and abs(word[1] - start_y) <= 2.5
                and word[4].upper() in statuses
            ),
            None,
        )

    def _center_details(
        self, words: list[Word], start_y: float
    ) -> tuple[str | None, str | None]:
        center_words = sorted(
            [
                word
                for word in words
                if word[0] < 110 and start_y + 15 < word[1] < start_y + 40
            ],
            key=lambda word: (word[1], word[0]),
        )
        center_code = next(
            (word[4] for word in center_words if re.fullmatch(r"\d{5}", word[4])),
            None,
        )
        scope = next(
            (
                word[4].strip("()")
                for word in center_words
                if word[4].startswith("(") and word[4].endswith(")")
            ),
            None,
        )
        return center_code, scope

    def _summary(
        self, words: list[Word], start_y: float, page_width: float, status: str
    ) -> ParsedSummary:
        left_min = page_width * 0.84
        left_max = page_width * 0.93
        right_min = left_max

        def value_at(x_min: float, x_max: float, offset: float):
            text = self._cell_text(
                words, x_min, x_max, start_y + offset, tolerance=3.0
            )
            return to_decimal(text)

        sgpa = value_at(left_min, left_max, 12.99)
        total_grade_points = value_at(left_min, left_max, 27.44)
        earned_credits = value_at(right_min, page_width, 27.44)
        total_marks = value_at(right_min, page_width, 41.32)

        if status == "CANCEL" and total_marks is None:
            numeric_values = [
                to_decimal(word[4])
                for word in words
                if word[0] >= right_min and start_y < word[1] < start_y + 50
            ]
            total_marks = next(
                (value for value in reversed(numeric_values) if value is not None), None
            )

        return ParsedSummary(
            reported_sgpa=sgpa,
            reported_total_grade_points=total_grade_points,
            reported_earned_credits=earned_credits,
            reported_total_marks=total_marks,
            reported_status=status,
        )

    def _parse_metadata(self, first_text: str, last_text: str) -> dict:
        examination_match = re.search(r"EXAMINATION\s*:\s*(.+)", first_text)
        if not examination_match:
            raise PDFExtractionError("The examination title could not be extracted.")
        examination_title = examination_match.group(1).strip()

        semester_match = re.search(r"SEMESTER\s*-\s*([A-Z0-9]+)", examination_title)
        programme = examination_title.split("SEMESTER", 1)[0].strip()
        branch_match = re.search(r"\(([^()]+)\)\s*$", programme)
        session_match = re.search(r"\b(Summer|Winter)\s+(\d{4})\b", examination_title)
        type_match = re.search(r"\(\s*([A-Za-z]+)\.?\s*\)\s*$", examination_title)

        maximum_marks_match = re.search(r"Total Marks\((\d+(?:\.\d+)?)\)", first_text)
        maximum_credits_match = re.search(r"Cr\.(\d+(?:\.\d+)?)", first_text)
        maximum_grade_points_match = re.search(
            r"Tot\.GrP\.-(\d+(?:\.\d+)?)", first_text
        )
        generated_match = re.search(
            r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}[AP]M\b",
            f"{first_text}\n{last_text}",
        )

        first_line = next((line.strip() for line in first_text.splitlines() if line.strip()), "")
        return {
            "university": first_line,
            "examination_title": examination_title,
            "programme": programme,
            "branch": branch_match.group(1) if branch_match else None,
            "semester": semester_match.group(1) if semester_match else None,
            "examination_session": (
                f"{session_match.group(1)} {session_match.group(2)}"
                if session_match
                else None
            ),
            "examination_type": type_match.group(1).upper() if type_match else None,
            "maximum_marks": (
                Decimal(maximum_marks_match.group(1)) if maximum_marks_match else None
            ),
            "maximum_credits": (
                Decimal(maximum_credits_match.group(1))
                if maximum_credits_match
                else None
            ),
            "maximum_grade_points": (
                Decimal(maximum_grade_points_match.group(1))
                if maximum_grade_points_match
                else None
            ),
            "report_generated_at_raw": generated_match.group(0) if generated_match else None,
        }

    @staticmethod
    def _parse_maximum_minimum(
        raw_text: str | None,
    ) -> tuple[Decimal, Decimal] | None:
        if not raw_text or "/" not in raw_text:
            return None
        maximum, minimum = raw_text.split("/", 1)
        maximum_value = to_decimal(maximum)
        minimum_value = to_decimal(minimum)
        if maximum_value is None or minimum_value is None:
            return None
        return maximum_value, minimum_value

    @staticmethod
    def _cell_text(
        words: list[Word],
        left: float,
        right: float,
        target_y: float,
        tolerance: float = 2.2,
    ) -> str | None:
        matches = [
            word
            for word in words
            if left <= (word[0] + word[2]) / 2 < right
            and abs(word[1] - target_y) <= tolerance
        ]
        if not matches:
            return None
        return " ".join(word[4] for word in sorted(matches, key=lambda word: word[0]))
