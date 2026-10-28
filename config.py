import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Centralized configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-refind-campus-secret-key-2026")
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"
    PORT = int(os.getenv("FLASK_PORT", "5000"))

    # MySQL 8+ / 26.7 Configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3307"))
    DB_USER = os.getenv("DB_USER", "refind_app")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "refind_db")

    # Root credentials used strictly for initial schema & user provisioning
    DB_ROOT_USER = os.getenv("DB_ROOT_USER", "root")
    DB_ROOT_PASSWORD = os.getenv("DB_ROOT_PASSWORD", "")

    # Upload Configuration
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
