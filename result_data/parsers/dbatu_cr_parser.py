"""Layout-driven reader for text-based DBATU Crystal Reports.

Subject identities, assessment rows and summary columns are detected on each
page. A report's subject list is the union of its printed columns, not the
catalogue (which can include several mutually exclusive electives).
"""
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from statistics import median

import pymupdf

from .canonical import (
    ParsedAssessment, ParsedReport, ParsedStudent, ParsedSubject,
    ParsedSubjectResult, ParsedSummary, ParsedValue,
)
from .exceptions import PDFExtractionError, UnsupportedPDFError
from .value_normalizer import normalize_attempt, parse_grade, parse_mark, to_decimal, grade_label

Word = tuple[float, float, float, float, str, int, int, int]


@dataclass(slots=True)
class SubjectColumn:
    subject: ParsedSubject
    center: float
    left: float
    right: float


@dataclass(slots=True)
class SummaryColumn:
    key: str
    label: str
    center: float
    row: int


@dataclass(slots=True)
class PageLayout:
    columns: list[SubjectColumn]
    header_rows: dict[str, list[float]]
    student_row_offsets: dict[str, float]
    summary_columns: list[SummaryColumn] = field(default_factory=list)


class DBATUCrystalReportParser:
    NAME = "DBATU Crystal Reports"
    VERSION = "2.0.1"
    # The coordinate system is normalized, so scaled copies have the same
    # tolerances. Actual column boundaries and data rows still come from text.
    WIDTH = 1587.0
    HEIGHT = 842.0
    SEAT_PATTERN = re.compile(r"^\d{12,20}$")
    SUBJECT_LINE_PATTERN = re.compile(
        r"^(?P<code>(?=[A-Z0-9._/-]*[A-Z])(?=[A-Z0-9._/-]*\d)"
        r"[A-Z0-9][A-Z0-9._/-]{4,79})\s*:\s*(?P<name>.+)$", re.I
    )
    GENDER_PATTERN = re.compile(r"^\((?P<gender>[A-Z])\)\s*")
    CREDIT_PATTERN = re.compile(r"\(\s*Credits?\s*:\s*(\d+(?:\.\d+)?)\s*\)", re.I)
    ATTEMPT_PATTERN = re.compile(
        r"(?:Summer|Winter|January|February|March|April|May|June|July|August|"
        r"September|October|November|December|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
        r"\s*-?\s*\d{4}", re.I
    )
    STATUSES = {"PASS", "FAIL", "CANCEL", "CANCELLED", "WITHHELD", "RESERVED"}
    FIRST_STUDENT_VALUE_OFFSET = 10.54
    STUDENT_VALUE_ROW_STEP = 18.60
    GRADE_AFTER_TOTAL_OFFSET = 21.76
    ATTEMPT_AFTER_GRADE_OFFSET = 11.40
    ROW_ALIASES = {
        "CREDITS": "CREDIT", "END SEMESTER": "ESE TOTAL", "ESE": "ESE TOTAL",
        "CA": "CA INTERNAL", "CONTINUOUS ASSESSMENT": "CA INTERNAL",
        "MID": "MID INTERNAL", "MIDSEM": "MID INTERNAL", "MID SEM": "MID INTERNAL",
        "INTERNAL TOTAL": "INT TOTAL", "TOTAL INTERNAL": "INT TOTAL",
        "TOTAL MARKS": "TOTAL", "GRAND TOTAL": "TOTAL",
    }

    def _words(self, page: pymupdf.Page) -> list[Word]:
        sx, sy = self.WIDTH / page.rect.width, self.HEIGHT / page.rect.height
        return [(w[0]*sx, w[1]*sy, w[2]*sx, w[3]*sy, *w[4:])
                for w in page.get_text("words")]

    @staticmethod
    def _rows(words: list[Word], tolerance: float = 1.2):
        grouped = []
        for word in sorted(words, key=lambda w: (w[1], w[0])):
            if not grouped or abs(grouped[-1][0] - word[1]) > tolerance:
                grouped.append((word[1], [word]))
            else:
                grouped[-1][1].append(word)
        return [(y, sorted(row, key=lambda w: w[0])) for y, row in grouped]

    def can_parse(self, pdf_path: str | Path) -> bool:
        try:
            with pymupdf.open(pdf_path) as document:
                if document.needs_pass or not len(document):
                    return False
                text = "\n".join(document[i].get_text() for i in range(min(3,len(document))))
        except (pymupdf.FileDataError, RuntimeError, OSError):
            return False
        return bool(re.search(r"Babasaheb\s+Ambedkar\s+Technological\s+University", text, re.I)
                    and re.search(r"(?:EXAMINATION|EXAM)\s*:", text, re.I)
                    and re.search(r"Seat\s+No\.?", text, re.I))

    def parse(self, pdf_path: str | Path) -> ParsedReport:
        source_path = Path(pdf_path)
        try:
            document = pymupdf.open(source_path)
        except (pymupdf.FileDataError, RuntimeError, OSError) as error:
            raise UnsupportedPDFError("The uploaded file is not a readable PDF.") from error
        with document:
            if document.needs_pass:
                raise UnsupportedPDFError("Unlock the password-protected PDF before uploading it.")
            if not len(document):
                raise UnsupportedPDFError("The PDF contains no pages.")
            if not any(p.get_text().strip() for p in document):
                raise UnsupportedPDFError("This PDF contains images without readable text. OCR is required before extraction.")
            if not self.can_parse(source_path):
                raise UnsupportedPDFError("A readable DBATU result report with an examination heading and seat numbers is required.")
            catalog = {}
            # Catalogues may continue on another page. Unused electives are not
            # added to the result matrix, but their definitions remain available.
            for page in document:
                for subject in self._catalog_from_page(page):
                    catalog.setdefault(subject.code, subject)
            subjects = {}
            students = []
            seen = set()
            page_subject_codes = {}
            page_assessment_types = {}
            for page_number, page in enumerate(document, 1):
                words = self._words(page)
                if not self._seat_words(words):
                    continue  # title/legend-only pages are not student records
                layout = self._parse_page_layout(page, list(catalog.values()), True)
                page_subject_codes[page_number] = [c.subject.code for c in layout.columns]
                page_assessment_types[page_number] = {
                    c.subject.code: [a.component_type for a in c.subject.assessments]
                    for c in layout.columns
                }
                for column in layout.columns:
                    subject = column.subject
                    if subject.code not in subjects:
                        subject.display_order = len(subjects) + 1
                        # Page columns retain their own row configuration.
                        subjects[subject.code] = replace(subject, assessments=list(subject.assessments))
                    else:
                        existing = subjects[subject.code]
                        known = {a.component_type for a in existing.assessments}
                        for assessment in subject.assessments:
                            if assessment.component_type not in known:
                                existing.assessments.append(replace(assessment, display_order=len(existing.assessments)+1))
                                known.add(assessment.component_type)
                for student in self._parse_page_students(page, page_number, layout):
                    if student.seat_number in seen:
                        raise PDFExtractionError(f"Duplicate seat number {student.seat_number} on page {page_number}; review the source pages.")
                    seen.add(student.seat_number)
                    students.append(student)
            if not students:
                raise PDFExtractionError("No student records were detected in the PDF.")
            metadata = self._parse_metadata(document[0].get_text(), document[-1].get_text())
            return ParsedReport(
                parser_name=self.NAME, parser_version=self.VERSION,
                source_filename=source_path.name, page_count=len(document),
                **metadata, institute_code=students[0].institute_code,
                institute_name=students[0].institute_name,
                subjects=list(subjects.values()), students=students,
                page_subject_codes=page_subject_codes,
                page_assessment_types=page_assessment_types,
            )

    def _catalog_from_page(self, page):
        """Reconstruct catalogue lines spatially, even if PDF text order splits
        each word or interleaves three catalogue columns.
        """
        words = self._words(page)
        seat_headers = [w[1] for w in words if w[4].upper() == "SEAT" and w[0] < 100]
        bottom = min(seat_headers, default=0)
        anchors = []
        for w in words:
            code = w[4].rstrip(":")
            if w[1] >= bottom or not re.fullmatch(r"(?=.*[A-Z])(?=.*[0-9])[A-Z0-9._/-]{5,80}", code):
                continue
            if w[4].endswith(":") or any(v[4] == ":" and abs(v[1]-w[1]) < 1.5
                                        and 0 <= v[0]-w[2] < 20 for v in words):
                anchors.append(w)
        if not anchors:
            return self._parse_subject_catalog(page.get_text(), required=False)
        lefts = []
        for x in sorted(w[0] for w in anchors):
            if not lefts or x-lefts[-1] > 20:
                lefts.append(x)
        subjects = []
        for anchor in anchors:
            column = min(range(len(lefts)), key=lambda i: abs(lefts[i]-anchor[0]))
            right = lefts[column+1]-5 if column+1 < len(lefts) else self.WIDTH
            next_y = min((w[1] for w in anchors if abs(w[0]-anchor[0]) < 20
                          and w[1] > anchor[1]+2), default=bottom)
            region = [w for w in words if lefts[column]-2 <= w[0] < right
                      and anchor[1]-1 <= w[1] < next_y-1]
            text = "\n".join(" ".join(w[4] for w in row) for _y,row in self._rows(region))
            subjects.extend(self._parse_subject_catalog(text, required=False))
        return subjects

    def _parse_subject_catalog(self, page_text: str, required: bool = True) -> list[ParsedSubject]:
        subjects = []
        code, parts = None, []

        def finish():
            if code is None:
                return
            name = " ".join(parts)
            credit_match = self.CREDIT_PATTERN.search(name)
            credit = to_decimal(credit_match.group(1)) if credit_match else None
            name = self.CREDIT_PATTERN.sub("", name).strip()
            subjects.append(ParsedSubject(code, name, len(subjects)+1, credit, False, None, None))

        for line in page_text.splitlines():
            line = line.strip()
            match = self.SUBJECT_LINE_PATTERN.fullmatch(line)
            if match:
                finish()
                code, parts = match.group("code").upper(), [match.group("name")]
            elif re.match(r"(?:EXAMINATION|EXAM)\s*:|Seat\s+No\.?|CORE$", line, re.I):
                finish()
                code, parts = None, []
                if line == "CORE" or re.match(r"Seat\s+No", line, re.I):
                    break
            elif code is not None and line and line not in {"Institute Record", "Office Record"}:
                # Continuations can span several lines, including a standalone
                # ':2 )' after '(Credit' on the preceding line.
                parts.append(line)
        finish()
        if required and not subjects:
            raise PDFExtractionError("No subject definitions were found in the report.")
        return subjects

    def _seat_words(self, words):
        return sorted((w for w in words if w[0] < 110 and self.SEAT_PATTERN.fullmatch(w[4])), key=lambda w: w[1])

    def _header_rows(self, words: list[Word]) -> dict[str, list[float]]:
        seats = self._seat_words(words)
        bottom = seats[0][1] if seats else self.HEIGHT * .6
        candidates = self._rows([w for w in words if w[0] < 100 and 50 < w[1] < bottom])
        labels = []
        for y, row in candidates:
            label = " ".join(w[4] for w in row).strip().upper()
            label = self.ROW_ALIASES.get(label, label)
            if re.fullmatch(r"[A-Z][A-Z0-9 /&()._-]*", label) and label not in {"CORE", "RESULT", "GRADE", "SEAT NO.", "CENTER CODE (WHOLE/PART)"}:
                labels.append((y, label))
        starts = [y for y, label in labels if label == "CREDIT"]
        totals = [y for y, label in labels if label == "TOTAL"]
        if not totals:
            raise PDFExtractionError("The subject total row could not be located; check that this page contains a complete result table.")
        end = totals[-1]
        if starts:
            start = starts[-1]
        else:
            # CREDIT is optional; only rows with printed mark limits belong to
            # the assessment header (not the catalogue above it).
            marked = [y for y, label in labels if y < end and any(
                w[0] >= 100 and abs(w[1]-y) < 2.2 and
                (to_decimal(w[4]) is not None or self._parse_maximum_minimum(w[4])) for w in words)]
            start = min(marked, default=end)
        rows = {}
        for y, label in labels:
            if start <= y <= end:
                rows.setdefault(label, []).append(y)
        return rows

    def _source_rows(self, rows):
        ordered = sorted((y, label) for label, values in rows.items()
                         if label not in {"CREDIT", "TOTAL"} for y in values)
        counts = {}
        result = []
        for y, label in ordered:
            base = {"ESE TOTAL": "ESE", "CA INTERNAL": "CA", "MID INTERNAL": "MID", "INT TOTAL": "INTERNAL_TOTAL"}.get(label)
            base = base or re.sub(r"[^A-Z0-9]+", "_", label).strip("_")[:40]
            index = counts.get(base, 0)
            counts[base] = index+1
            source = f"ESE_{index}" if base == "ESE" else base if index == 0 else f"{base}_{index+1}"
            result.append((y, label, source, base))
        return result

    def _student_row_offsets(self, header_rows):
        sources = self._source_rows(header_rows)
        offsets = {source: self.FIRST_STUDENT_VALUE_OFFSET+i*self.STUDENT_VALUE_ROW_STEP
                   for i, (_y, _label, source, _base) in enumerate(sources)}
        offsets["TOTAL"] = self.FIRST_STUDENT_VALUE_OFFSET+len(sources)*self.STUDENT_VALUE_ROW_STEP
        offsets["GRADE"] = offsets["TOTAL"]+self.GRADE_AFTER_TOTAL_OFFSET
        offsets["ATTEMPT"] = offsets["GRADE"]+self.ATTEMPT_AFTER_GRADE_OFFSET
        return offsets

    def _parse_page_layout(self, page, subjects, configure_subjects=True):
        words = self._words(page)
        rows = self._header_rows(words)
        first_row = min(y for ys in rows.values() for y in ys)
        by_code = {s.code: s for s in subjects}
        candidates = [w for w in words if 100 < w[0] < self.WIDTH*.84
                      and first_row-65 < w[1] < first_row-3
                      and re.fullmatch(r"[A-Za-z0-9._/-]{5,80}", w[4])
                      and any(c.isdigit() for c in w[4]) and any(c.isalpha() for c in w[4])]
        groups = self._rows(candidates)
        if not groups:
            raise PDFExtractionError("Subject codes could not be located above this page's result table.")
        code_y, code_words = max(groups, key=lambda item: (len(item[1]), item[0]))
        centers = [(w[0]+w[2])/2 for w in code_words]
        typical_gap = median([b-a for a,b in zip(centers,centers[1:])]) if len(centers)>1 else max(70, code_words[0][2]-code_words[0][0]+20)
        boundaries = [max(98., centers[0]-typical_gap/2)]
        boundaries += [(a+b)/2 for a,b in zip(centers,centers[1:])]
        boundaries.append(min(self.WIDTH*.86, centers[-1]+typical_gap/2))
        columns = []
        for i, center in enumerate(centers):
            fragments = [w for w in words if boundaries[i] <= (w[0]+w[2])/2 < boundaries[i+1]
                         and code_y-1.2 <= w[1] < first_row-3]
            fragment_rows = self._rows(fragments)
            code = "".join(w[4] for w in fragment_rows[0][1]).upper()
            last_y = fragment_rows[0][0]
            for fragment_y, fragment_words in fragment_rows[1:]:
                if code in by_code:
                    break
                suffix = "".join(w[4] for w in fragment_words).upper()
                candidate = code + suffix
                if any(known.startswith(candidate) for known in by_code):
                    code = candidate
                elif fragment_y-last_y <= 12.5 and re.fullmatch(r"[A-Z0-9]{1,5}", suffix):
                    code = candidate
                else:
                    break
                last_y = fragment_y
            # Most codes fit on one line; longer NEP codes wrap into suffixes.
            definition = by_code.get(code)
            if definition is None:
                if not re.fullmatch(r"(?=.*[A-Z])(?=.*[0-9])[A-Z0-9._/-]{5,80}", code):
                    raise PDFExtractionError(f"A subject code is unreadable near column {i+1} on this page.")
                definition = ParsedSubject(code, code, i+1, None, False, None, None)
            subject = replace(definition, assessments=[])
            if configure_subjects:
                self._configure_subject(subject, words, boundaries[i], boundaries[i+1], rows)
            columns.append(SubjectColumn(subject, center, boundaries[i], boundaries[i+1]))
        layout = PageLayout(columns, rows, self._student_row_offsets(rows))
        layout.summary_columns = self._summary_columns(words, rows, boundaries[-1])
        return layout

    def _configure_subject(self, subject, words, left, right, rows):
        if "CREDIT" in rows:
            credit = to_decimal(self._cell_text(words, left, right, rows["CREDIT"][0]))
            if credit is not None:
                subject.credits = credit
        configured = []
        for y, label, source, base in self._source_rows(rows):
            text = self._cell_text(words, left, right, y)
            limits = self._parse_maximum_minimum(text)
            maximum = limits[0] if limits else to_decimal(text)
            if maximum is not None:
                # Distinct rows must not collide in the database when a subject
                # genuinely has more than one ESE/practical assessment.
                component = base if base not in {a.component_type for a in configured} else source
                configured.append(ParsedAssessment(component, label.title(), maximum,
                    limits[1] if limits else None, len(configured)+1, source))
        subject.assessments = configured
        text = self._cell_text(words, left, right, rows["TOTAL"][-1])
        subject.is_audit = bool(text and text.upper() in {"GRADE", "AUDIT", "AU"})
        limits = self._parse_maximum_minimum(text)
        if subject.is_audit:
            subject.credits = subject.credits or Decimal("0")
        elif limits:
            subject.total_maximum, subject.total_minimum = limits
        else:
            # Some office records print only a maximum, not max/min. Missing
            # minima stay unknown; no pass rule is invented by the parser.
            subject.total_maximum = to_decimal(text)
            subject.total_minimum = None

    def _value_offsets(self, words, seat, block_end, layout):
        """Calibrate each block using observed mark/grade baselines.

        Blank assessment rows keep their position. We never compact a block's
        non-empty cells, which would shift marks after an omitted component.
        """
        start = seat[1]
        block = [w for w in words if layout.columns[0].left <= (w[0]+w[2])/2 < layout.columns[-1].right
                 and start+3 < w[1] < block_end]
        grade_rows = []
        for y, row in self._rows(block):
            for col in layout.columns:
                text = self._cell_text(row, col.left, col.right, y)
                if parse_grade(text):
                    grade_rows.append(y)
                    break
        if not grade_rows:
            return layout.student_row_offsets.copy()
        grade_y = median(grade_rows)
        mark_rows = []
        for y,row in self._rows([w for w in block if w[1] < grade_y-3]):
            if any(to_decimal(w[4].strip("()")) is not None or w[4] in {"|", "AOO", "ZOO", "AB", "ABSENT"} for w in row):
                mark_rows.append(y)
        gaps = [b-a for a,b in zip(mark_rows,mark_rows[1:]) if b-a > 5]
        step = median(sorted(gaps)[:max(1, (len(gaps)+1)//2)]) if gaps else self.STUDENT_VALUE_ROW_STEP
        total_y = grade_y - step*(self.GRADE_AFTER_TOTAL_OFFSET/self.STUDENT_VALUE_ROW_STEP)
        if mark_rows and .7*step < grade_y-mark_rows[-1] < 1.7*step:
            total_y = mark_rows[-1]
        sources = self._source_rows(layout.header_rows)
        if mark_rows and abs(mark_rows[0] - (start+self.FIRST_STUDENT_VALUE_OFFSET)) < .55*step:
            # Anchor to the first printed mark when possible. This also keeps
            # empty totals empty if grade and mark fonts have different sizes.
            total_y = mark_rows[0] + len(sources)*step
        first_y = total_y - len(sources)*step
        offsets = {source: first_y+i*step-start for i, (_y,_label,source,_base) in enumerate(sources)}
        offsets.update(TOTAL=total_y-start, GRADE=grade_y-start,
                       ATTEMPT=grade_y-start+self.ATTEMPT_AFTER_GRADE_OFFSET)
        return offsets

    def _parse_page_students(self, page, page_number, layout):
        words = self._words(page)
        seats = self._seat_words(words)
        students = []
        for i,seat in enumerate(seats):
            end = seats[i+1][1]-1 if i+1<len(seats) else self.HEIGHT-55
            students.append(self._parse_student(words, page_number, seat, end, layout))
        return students

    def _parse_student(self, words, page_number, seat, block_end, layout):
        start = seat[1]
        identity = sorted([w for w in words if abs(w[1]-start)<=2.2 and w[0]>seat[2]
                           and w[0]<self.WIDTH*.84], key=lambda w:w[0])
        institute_index = next((i for i,w in enumerate(identity) if re.fullmatch(r"\d{4,6}",w[4])
                                and i+1<len(identity) and identity[i+1][4]=="-"), None)
        name_words = identity[:institute_index] if institute_index is not None else identity
        printed_name = " ".join(w[4] for w in name_words)
        gender = self.GENDER_PATTERN.match(printed_name)
        name = self.GENDER_PATTERN.sub("", printed_name).strip()
        if not name:
            raise PDFExtractionError(f"The student name is unreadable for seat {seat[4]} on page {page_number}.")
        institute_code = identity[institute_index][4] if institute_index is not None else None
        institute_name = " ".join(w[4] for w in identity[institute_index+2:]) if institute_index is not None else None
        status = next((w[4].upper() for w in words if w[0]>self.WIDTH*.84
                       and abs(w[1]-start)<3 and w[4].upper() in self.STATUSES), "UNKNOWN")
        status = "CANCEL" if status == "CANCELLED" else status
        center_words = [w for w in words if w[0]<110 and start+15 < w[1] < min(start+50,block_end)]
        center = next((w[4] for w in center_words if re.fullmatch(r"\d{4,6}",w[4])), None)
        scope = next((w[4].strip("()") for w in center_words if re.fullmatch(r"\(Whole\)|\(Part\)",w[4],re.I)),None)
        offsets = self._value_offsets(words, seat, block_end, layout)
        values = [w for w in words if start+2 < w[1] < block_end]
        results = []
        for col in layout.columns:
            components = []
            for assessment in col.subject.assessments:
                raw = self._cell_text(values,col.left,col.right,start+offsets[assessment.source_row],2.5)
                value = parse_mark(raw)
                if value is not None:
                    components.append((assessment.component_type,value))
            total = parse_mark(self._cell_text(values,col.left,col.right,start+offsets["TOTAL"],2.5))
            grade_raw = self._cell_text(values,col.left,col.right,start+offsets["GRADE"],2.5)
            grade = parse_grade(grade_raw)
            if grade is None and not grade_label(grade_raw):
                # A single column can have a shifted baseline. Search only this
                # student's own subject cell band, never a neighbouring column.
                candidates=[]
                for candidate_y,candidate_words in self._rows(values):
                    text=self._cell_text(candidate_words,col.left,col.right,candidate_y)
                    if parse_grade(text):candidates.append(text)
                if len(candidates)==1:
                    grade_raw=candidates[0];grade=parse_grade(grade_raw)
            attempts = []
            for y,row in self._rows(values):
                text = self._cell_text(row,col.left,col.right,y)
                if text and self.ATTEMPT_PATTERN.fullmatch(text):
                    attempts.append(text)
            results.append(ParsedSubjectResult(
                subject_code=col.subject.code, source_page=page_number, components=components,
                total=total, grade_raw=grade_raw,
                grade=grade.grade if grade else (grade_label(grade_raw) if not col.subject.is_audit else None),
                grade_point=grade.grade_point if grade else None,
                credit_points=grade.credit_points if grade else None,
                grace_marks=grade.grace_marks if grade else None,
                audit_grade=(grade_label(grade_raw) if col.subject.is_audit else None),
                attempt_session=normalize_attempt(attempts[-1]) if attempts else None,
            ))
        summary = self._summary(words,start,block_end,status,layout)
        return ParsedStudent(seat[4],name,gender.group("gender") if gender else None,
            center,scope,institute_code,institute_name,page_number,status,results,summary)

    def _summary_columns(self, words, rows, subject_right):
        first = min(y for values in rows.values() for y in values)
        heading_y = max((w[1] for w in words if w[4].upper() == "RESULT"
                         and w[0] > self.WIDTH*.80 and w[1] < first), default=50)
        header = [w for w in words if w[0]>max(subject_right,self.WIDTH*.80) and heading_y+2<w[1]<first]
        detected = []
        for y,row in self._rows(header):
            i=0
            while i<len(row):
                w=row[i]; token=w[4]; label=token; key=None; end=w[2]
                upper=token.upper()
                if upper in {"RESULT", "RECORD", "INSTITUTE", "OFFICE"}:
                    i+=1; continue
                if upper=="SGPA": key="reported_sgpa"
                elif upper.startswith("TOT.GRP"): key="reported_total_grade_points"
                elif upper == "CR." or re.match(r"^Cr\.\s*\d",token,re.I): key="reported_earned_credits"
                elif upper in {"EXT","INT","TOTAL"} and i+1<len(row) and re.match(r"(?:TOTAL|MARKS)(?:\(|$)",row[i+1][4],re.I):
                    label += " "+row[i+1][4];end=row[i+1][2];i+=1
                    if i+1 < len(row) and re.fullmatch(r"\([0-9.]+\)",row[i+1][4]):
                        label += " " + row[i+1][4];end=row[i+1][2];i+=1
                    key={"EXT":"external_total","INT":"internal_total","TOTAL":"reported_total_marks"}[upper]
                elif re.fullmatch(r"[A-Za-z][A-Za-z.%-]*(?:\([0-9.]+\))?",token):
                    key=re.sub(r"[^a-z0-9]+","_",token.lower()).strip("_")
                if key:
                    detected.append((y,key,label,(w[0]+end)/2))
                i+=1
        # Summary headers form horizontal lines (SGPA/percentage/external, then
        # grade points/credits/internal, then total marks). Extra headings stay.
        known_rows = {"reported_sgpa":0, "percentage":0, "external_total":0,
                      "reported_total_grade_points":1, "reported_earned_credits":1,
                      "internal_total":1, "reported_total_marks":2}
        anchors = [(y,known_rows[key]) for y,key,_label,_center in detected if key in known_rows]
        steps = [(b_y-a_y)/(b_row-a_row) for a_y,a_row in anchors for b_y,b_row in anchors
                 if b_row>a_row and b_y>a_y]
        header_step = median(steps) if steps else 10.0
        origin = median([y-row*header_step for y,row in anchors]) if anchors else heading_y+10
        return [SummaryColumn(key,label,center, max(0,round((y-origin)/header_step)))
                for y,key,label,center in detected]

    def _summary(self, words, start, block_end, status, layout):
        values = {}
        extras = {}
        for row in sorted({c.row for c in layout.summary_columns}):
            columns=sorted([c for c in layout.summary_columns if c.row==row],key=lambda c:c.center)
            target=start+12.99+row*14.45
            tokens=sorted([w for w in words if w[0]>self.WIDTH*.80 and abs(w[1]-target)<=3
                           and start+2<w[1]<block_end and to_decimal(w[4]) is not None],key=lambda w:w[0])
            # Match ordered values to headings, allowing blank columns. Choosing
            # the nearest available heading preserves old office-record extras.
            remaining=list(columns)
            for w in tokens:
                if not remaining: break
                col=min(remaining,key=lambda c:abs(c.center-(w[0]+w[2])/2))
                remaining.remove(col)
                value=parse_mark(w[4])
                if col.key.startswith("reported_"):
                    values[col.key]=value.numeric_value
                else:
                    extras[col.key]={"label":col.label,"raw_text":value.raw_text,"numeric_value":str(value.numeric_value)}
        return ParsedSummary(**values,reported_status=status,additional_values=extras)

    def _parse_metadata(self, first_text: str, last_text: str) -> dict:
        examination_match = re.search(r"(?:EXAMINATION|EXAM)\s*:\s*(.+)", first_text, re.IGNORECASE)
        if not examination_match:
            raise PDFExtractionError("The examination title could not be extracted.")
        examination_title = examination_match.group(1).strip()

        semester_match = re.search(r"SEMESTER\s*-\s*([A-Z0-9]+)", examination_title)
        programme = examination_title.split("SEMESTER", 1)[0].strip()
        branch_match = re.search(r"\(([^()]+)\)\s*$", programme)
        session_match = re.search(r"\b(Summer|Winter)\s+(\d{4})\b", examination_title)
        type_match = re.search(r"\(\s*([A-Za-z]+)\.?\s*\)\s*$", examination_title)

        maximum_marks_match = re.search(r"Total\s+Marks\s*\(\s*(\d+(?:\.\d+)?)\s*\)", first_text)
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
