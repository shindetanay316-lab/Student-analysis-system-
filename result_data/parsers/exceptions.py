class PDFExtractionError(ValueError):
    """Raised when a recognized PDF cannot be extracted safely."""


class UnsupportedPDFError(PDFExtractionError):
    """Raised when no supported result-report template matches a PDF."""
