"""Environment-backed Flask configuration and database URL resolution."""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _database_uri():
    """Return a stable database URI. Relative SQLite paths are rooted at BASE_DIR."""
    configured = os.getenv("DATABASE_URL")
    default_path = BASE_DIR / "instance" / "mawiz.db"
    if not configured:
        default_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{default_path}"
    if configured.startswith("sqlite:///") and not configured.startswith("sqlite:////"):
        raw_path = configured[len("sqlite:///"):]
        if raw_path != ":memory:" and not Path(raw_path).is_absolute():
            path = (BASE_DIR / raw_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path}"
    return configured


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-only-change-me-please"
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_CHECK_DEFAULT = True
    SESSION_COOKIE_NAME = "mawiz_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = 3600
    SESSION_REFRESH_EACH_REQUEST = True
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "10485760"))
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "txt", "zip"}
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"
    MAIL_SINK_PATH = os.getenv("MAIL_SINK_PATH", str(BASE_DIR / "instance" / "dev-mail.log"))
    MAIL_BACKEND = os.getenv("MAIL_BACKEND", "console")
    MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@mawiz.local")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    PASSWORD_RESET_MAX_AGE = int(os.getenv("PASSWORD_RESET_MAX_AGE", "1800"))
    EMAIL_VERIFY_MAX_AGE = int(os.getenv("EMAIL_VERIFY_MAX_AGE", "86400"))
    REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"
    REQUIRE_EMAIL_2FA = os.getenv("REQUIRE_EMAIL_2FA", "false").lower() == "true"
    EMAIL_2FA_CODE_MAX_AGE = int(os.getenv("EMAIL_2FA_CODE_MAX_AGE", "600"))
    EMAIL_2FA_MAX_ATTEMPTS = int(os.getenv("EMAIL_2FA_MAX_ATTEMPTS", "5"))
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_API_BASE_URL = os.getenv("PAYSTACK_API_BASE_URL", "https://api.paystack.co")
    PAYSTACK_TIMEOUT_SECONDS = int(os.getenv("PAYSTACK_TIMEOUT_SECONDS", "15"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    _log_file_value = Path(os.getenv("LOG_FILE", "instance/logs/mawiz.log"))
    LOG_FILE = str((_log_file_value if _log_file_value.is_absolute() else BASE_DIR / _log_file_value).resolve())
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "1048576"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    TRUSTED_HOSTS = [h.strip() for h in os.getenv("TRUSTED_HOSTS", "").split(",") if h.strip()] or None
