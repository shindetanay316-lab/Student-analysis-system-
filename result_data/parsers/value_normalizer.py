import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .canonical import ParsedValue


GRADE_PATTERN = re.compile(
    r"^(?P<grade_point>\d+(?:\.\d+)?)/"
    r"(?P<grade>[A-Z]{1,3})/"
    r"(?P<credit_points>\d+(?:\.\d+)?)"
    r"(?:\(G-(?P<grace>\d+(?:\.\d+)?)\))?$"
)


@dataclass(slots=True)
class ParsedGrade:
    raw_text: str
    grade_point: Decimal
    grade: str
    credit_points: Decimal
    grace_marks: Decimal | None


def to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def parse_mark(raw_text: str | None) -> ParsedValue | None:
    if raw_text is None:
        return None

    text = raw_text.strip()
    if not text or text == "|":
        return None

    carried_forward = text.startswith("(") and text.endswith(")")
    normalized = text[1:-1].strip() if carried_forward else text

    if normalized == "ZOO":
        return ParsedValue(
            raw_text=text,
            numeric_value=Decimal("0"),
            is_carried_forward=carried_forward,
            special_code="ZOO",
        )

    numeric_value = to_decimal(normalized)
    if numeric_value is not None:
        return ParsedValue(
            raw_text=text,
            numeric_value=numeric_value,
            is_carried_forward=carried_forward,
        )

    return ParsedValue(
        raw_text=text,
        numeric_value=None,
        is_carried_forward=carried_forward,
        special_code=normalized,
    )


def parse_grade(raw_text: str | None) -> ParsedGrade | None:
    if raw_text is None:
        return None

    text = re.sub(r"\s+", "", raw_text.strip().upper())
    match = GRADE_PATTERN.fullmatch(text)
    if not match:
        return None

    return ParsedGrade(
        raw_text=text,
        grade_point=Decimal(match.group("grade_point")),
        grade=match.group("grade"),
        credit_points=Decimal(match.group("credit_points")),
        grace_marks=(
            Decimal(match.group("grace")) if match.group("grace") else None
        ),
    )


def normalize_attempt(raw_text: str | None) -> str | None:
    if raw_text is None:
        return None
    text = re.sub(r"\s+", " ", raw_text.strip())
    text = re.sub(r"\s*-\s*", " - ", text)
    return text or None


PRINTED_GRADES = {"EX","AA","AB","BB","BC","CC","CD","DD","DE","EE","FF","AU","S","US","PP","NP"}

def grade_label(raw_text: str | None) -> str | None:
    if not raw_text:return None
    text=re.sub(r"\s+", "", raw_text.strip().upper())
    parsed=parse_grade(text)
    if parsed:return parsed.grade
    if text in PRINTED_GRADES:return text
    if text.startswith("(") and text.endswith(")") and text[1:-1] in PRINTED_GRADES:
        return text[1:-1]
    return None
