"""Small stability helpers for ECE SMS routes.

Purpose:
- Normalize risky request values before using them.
- Prevent one SGPA/CGPA recalculation failure from being silently ignored.
- Keep warning messages short and safe for flashing on the UI.
"""


def safe_int(value, default=None, minimum=None, maximum=None):
    """Convert a user/request value to int safely.

    Returns default when the value is blank, invalid, or outside the optional
    min/max limits. This prevents ValueError crashes from bad query/form/JSON
    inputs.
    """
    try:
        if value is None or str(value).strip() == "":
            return default
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default

    if minimum is not None and number < minimum:
        return default
    if maximum is not None and number > maximum:
        return default
    return number


def clean_exam_type(value, allowed, default="CT1"):
    """Return a supported exam type only."""
    exam_type = str(value or default).strip().upper()
    return exam_type if exam_type in allowed else default


def compact_error(message, limit=180):
    """Shorten long exception messages before flashing them."""
    text = str(message or "Unknown error").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def update_sgpa_cgpa_safe(prn, semester_id, academic_year, db, models):
    """Run SGPA/CGPA recalculation and return (success, message)."""
    try:
        from calculations import update_sgpa_cgpa_for_student

        update_sgpa_cgpa_for_student(
            prn=prn,
            semester_id=semester_id,
            academic_year=academic_year,
            db=db,
            models=models,
        )
        return True, None
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        return False, compact_error(exc)


def flash_sgpa_warnings(flash_func, warnings, max_items=8):
    """Show SGPA warnings in a readable way after an otherwise successful upload."""
    if not warnings:
        return

    shown = warnings[:max_items]
    extra = len(warnings) - len(shown)
    details = "<br>".join(shown)
    if extra > 0:
        details += f"<br>...and {extra} more warning(s)."

    flash_func(
        "Marks were saved, but SGPA/CGPA recalculation had warning(s):<br>" + details,
        "warning",
    )
