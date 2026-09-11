import os
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')


def _database_url():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        return 'sqlite:///' + os.path.join(INSTANCE_FOLDER, 'student_analysis.db')
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    INSTANCE_FOLDER = INSTANCE_FOLDER
    # Security
    # For local development this fallback is okay. For GitHub/production, set SECRET_KEY in environment.
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'dev-only-change-this-secret-key'
    )

    # Database
    # SQLite works without installing a database server. Set DATABASE_URL to
    # use MySQL or PostgreSQL in a shared/production environment.
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

    # Folders
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(BASE_DIR, 'uploads')
    )
    REPORTS_FOLDER = os.environ.get(
        'REPORTS_FOLDER',
        os.path.join(BASE_DIR, 'reports')
    )
    RESULT_DATA_UPLOAD_FOLDER = os.environ.get(
        'RESULT_DATA_UPLOAD_FOLDER',
        os.path.join(BASE_DIR, 'uploads', 'result_data')
    )

    # App Settings
    CURRENT_ACADEMIC_YEAR = os.environ.get('CURRENT_ACADEMIC_YEAR', '2025-26')
    CURRENT_SEMESTER = int(os.environ.get('CURRENT_SEMESTER', 6))
    MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '25'))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    WTF_CSRF_CHECK_DEFAULT = False

    # Report Signatories
    CLASS_TEACHER_NAME = os.environ.get('CLASS_TEACHER_NAME', 'Prof. A. V. Khake')
    HOD_NAME = os.environ.get('HOD_NAME', 'Dr. D. L. Bhuyar')
