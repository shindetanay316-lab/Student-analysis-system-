import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    # ── Security ────────────────────────────────────────────
    SECRET_KEY = 'ece-sms-dbatu-secret-2024-change-this'

    # ── Database ─────────────────────────────────────────────
    # Format: mysql+pymysql://username:password@host/database_name
    # XAMPP default: username=root, password=empty
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:root@localhost/ece_sms'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Folders ──────────────────────────────────────────────
    UPLOAD_FOLDER  = os.path.join(BASE_DIR, 'uploads')
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'reports')

    # ── App Settings ─────────────────────────────────────────
    CURRENT_ACADEMIC_YEAR   = '2024-25'
    CURRENT_SEMESTER        = 3
    MAX_CONTENT_LENGTH      = 16 * 1024 * 1024  # 16 MB max file upload