import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # Security
    # For local development this fallback is okay. For GitHub/production, set SECRET_KEY in environment.
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'dev-only-change-this-secret-key'
    )

    # Database
    # If your MySQL password is empty, set DATABASE_URL=mysql+pymysql://root:@localhost/ece_sms
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'mysql+pymysql://root:root@localhost/ece_sms'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Folders
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(BASE_DIR, 'uploads')
    )
    REPORTS_FOLDER = os.environ.get(
        'REPORTS_FOLDER',
        os.path.join(BASE_DIR, 'reports')
    )

    # App Settings
    CURRENT_ACADEMIC_YEAR = os.environ.get('CURRENT_ACADEMIC_YEAR', '2025-26')
    CURRENT_SEMESTER = int(os.environ.get('CURRENT_SEMESTER', 6))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
