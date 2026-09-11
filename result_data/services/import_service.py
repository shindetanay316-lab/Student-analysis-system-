import hashlib
from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from models import db
from ..models import ImportJob


class InvalidPDFError(ValueError):
    pass


class DuplicateImportError(ValueError):
    def __init__(self, import_job_id: int):
        super().__init__("This exact PDF has already been uploaded.")
        self.import_job_id = import_job_id


def delete_import_job(job: ImportJob, upload_folder: str | Path) -> bool:
    """Delete an import transactionally, then remove its private source PDF.

    Database deletion happens first so a database failure never leaves a job
    pointing at a missing source file. The return value reports whether the
    source file was absent or removed successfully.
    """
    upload_root = Path(upload_folder).resolve()
    source_path = (upload_root / job.stored_filename).resolve()
    if source_path.parent != upload_root:
        raise InvalidPDFError("The stored PDF path is outside the upload directory.")

    db.session.delete(job)
    db.session.commit()

    try:
        source_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _has_pdf_signature(file_storage: FileStorage) -> bool:
    file_storage.stream.seek(0)
    signature = file_storage.stream.read(5)
    file_storage.stream.seek(0)
    return signature == b"%PDF-"


def _sha256(file_storage: FileStorage) -> str:
    digest = hashlib.sha256()
    file_storage.stream.seek(0)
    while chunk := file_storage.stream.read(1024 * 1024):
        digest.update(chunk)
    file_storage.stream.seek(0)
    return digest.hexdigest()


def create_import_job(file_storage: FileStorage, upload_folder: str | Path) -> ImportJob:
    if not _has_pdf_signature(file_storage):
        raise InvalidPDFError("The selected file does not contain a valid PDF signature.")

    file_hash = _sha256(file_storage)
    existing = db.session.scalar(
        db.select(ImportJob).where(ImportJob.file_hash == file_hash)
    )
    if existing:
        raise DuplicateImportError(existing.id)

    original_filename = secure_filename(file_storage.filename or "result-report.pdf")
    if not original_filename:
        original_filename = "result-report.pdf"

    destination_directory = Path(upload_folder)
    destination_directory.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}.pdf"
    destination = destination_directory / stored_filename

    try:
        file_storage.stream.seek(0)
        file_storage.save(destination)
        job = ImportJob(
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_hash=file_hash,
            file_size_bytes=destination.stat().st_size,
            status=ImportJob.STATUS_UPLOADED,
        )
        db.session.add(job)
        db.session.commit()
    except Exception:
        db.session.rollback()
        destination.unlink(missing_ok=True)
        raise

    return job
