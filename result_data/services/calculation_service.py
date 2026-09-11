from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


CALCULATION_RULE_VERSION = "DBATU-CR-2026-v1"
SUPPORTED_PARSER_NAME = "DBATU Crystal Reports"


@dataclass(frozen=True, slots=True)
class GradeOutcome:
    grade: str
    grade_point: Decimal


# These bands are transcribed from the footer of the supplied DBATU report.
# Comparisons intentionally preserve the printed decimal boundaries.
GRADE_BANDS = (
    (Decimal("90.00"), GradeOutcome("EX", Decimal("10"))),
    (Decimal("85.00"), GradeOutcome("AA", Decimal("9"))),
    (Decimal("80.00"), GradeOutcome("AB", Decimal("8.5"))),
    (Decimal("75.00"), GradeOutcome("BB", Decimal("8"))),
    (Decimal("70.00"), GradeOutcome("BC", Decimal("7.5"))),
    (Decimal("65.00"), GradeOutcome("CC", Decimal("7"))),
    (Decimal("60.00"), GradeOutcome("CD", Decimal("6.5"))),
    (Decimal("55.00"), GradeOutcome("DD", Decimal("6"))),
    (Decimal("50.00"), GradeOutcome("DE", Decimal("5.5"))),
)
PASSING_GRADE = GradeOutcome("EE", Decimal("5"))
FAILING_GRADE = GradeOutcome("FF", Decimal("0"))


def calculate_component_sum(
    component_values: Iterable[Decimal | None],
) -> Decimal | None:
    values = list(component_values)
    if not values or any(value is None for value in values):
        return None
    return sum(values, Decimal("0"))


def calculate_grade(
    total: Decimal | None,
    total_minimum: Decimal | None,
    component_minima_met: bool,
) -> GradeOutcome | None:
    if total is None or total_minimum is None:
        return None
    if not component_minima_met or total < total_minimum:
        return FAILING_GRADE
    for lower_boundary, outcome in GRADE_BANDS:
        if total > lower_boundary:
            return outcome
    return PASSING_GRADE


def calculate_credit_points(
    credits: Decimal | None, grade_point: Decimal | None
) -> Decimal | None:
    if credits is None or grade_point is None:
        return None
    return credits * grade_point


def calculate_sgpa(
    total_grade_points: Decimal | None, maximum_credits: Decimal | None
) -> Decimal | None:
    if total_grade_points is None or maximum_credits is None or maximum_credits <= 0:
        return None
    return (total_grade_points / maximum_credits).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
