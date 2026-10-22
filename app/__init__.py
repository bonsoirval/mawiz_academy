"""Application factory, configuration, request lifecycle, and security headers."""

import os
import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template, session, request, g
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config
from .extensions import db, csrf, limiter


def _configure_logging(app):
    """Configure rotating application logs without duplicating handlers in tests/reloads."""
    level_name = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_path = Path(app.config.get("LOG_FILE") or (Path(app.instance_path) / "logs" / "mawiz.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    app.logger.setLevel(level)
    app.logger.propagate = False
    # Remove only handlers installed by this helper, not Flask's default handler.
    for handler in list(app.logger.handlers):
        if getattr(handler, "_mawiz_log_handler", False):
            app.logger.removeHandler(handler)
            handler.close()
    file_handler = RotatingFileHandler(
        log_path, maxBytes=max(65536, int(app.config.get("LOG_MAX_BYTES", 1048576))),
        backupCount=max(1, int(app.config.get("LOG_BACKUP_COUNT", 5))), encoding="utf-8"
    )
    file_handler._mawiz_log_handler = True
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    if app.debug or app.testing:
        stream_handler = logging.StreamHandler()
        stream_handler._mawiz_log_handler = True
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        app.logger.addHandler(stream_handler)


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if not app.debug and app.config["SECRET_KEY"] == "dev-only-change-me-please":
        raise RuntimeError("A strong SECRET_KEY must be configured outside development.")
    if app.config.get("TRUSTED_HOSTS"):
        app.config["TRUSTED_HOSTS"] = app.config["TRUSTED_HOSTS"]
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    os.makedirs(app.instance_path, exist_ok=True)
    _configure_logging(app)
    db.init_app(app); csrf.init_app(app); limiter.init_app(app)

    with app.app_context():
        from .common.schema import ensure_schema
        ensure_schema()

    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .learner.routes import learner_bp
    from .learning.routes import learning_bp
    from .projects.routes import projects_bp
    from .simulations.routes import simulations_bp
    from .portfolio.routes import portfolio_bp
    from .admin.routes import admin_bp
    for bp in (auth_bp, main_bp, learner_bp, learning_bp, projects_bp, simulations_bp, portfolio_bp, admin_bp):
        app.register_blueprint(bp)

    from .models import User
    from .common.settings import get_bool, get_setting
    from .common.security import can
    @app.context_processor
    def inject_user():
        uid = session.get("user_id")
        return {"current_user": db.session.get(User, uid) if uid else None, "can": can, "site_settings": {
            "site_name": get_setting("site_name"),
            "site_tagline": get_setting("site_tagline"),
            "seo_title": get_setting("seo_title"),
            "seo_description": get_setting("seo_description"),
            "seo_keywords": get_setting("seo_keywords"),
            "seo_robots": get_setting("seo_robots"),
            "canonical_base_url": get_setting("canonical_base_url"),
            "maintenance_mode": get_bool("maintenance_mode"),
        }}

    @app.before_request
    def begin_request_logging():
        supplied = request.headers.get("X-Request-ID", "").strip()
        # Accept only short, printable correlation IDs; otherwise create our own.
        g.request_id = supplied[:80] if supplied and all(32 <= ord(ch) < 127 for ch in supplied) else uuid.uuid4().hex
        g.request_started_at = time.monotonic()

    @app.after_request
    def log_request(response):
        elapsed_ms = round((time.monotonic() - getattr(g, "request_started_at", time.monotonic())) * 1000, 2)
        response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
        # Do not log query strings, form bodies, cookies, authorization headers, or user email.
        logger = app.logger.warning if response.status_code >= 400 else app.logger.info
        logger("request_id=%s method=%s endpoint=%s status=%s duration_ms=%s",
               getattr(g, "request_id", "-"), request.method,
               request.endpoint or "unmatched", response.status_code, elapsed_ms)
        return response

    @app.before_request
    def maintenance_gate():
        if request.endpoint in {"static", "auth.login", "auth.verify_email", "auth.verify_2fa", "main.maintenance", "main.robots", "main.sitemap"}:
            return None
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        if get_bool("maintenance_mode") and (not user or user.role != "admin"):
            return render_template("main/maintenance.html"), 503
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-src https://www.youtube-nocookie.com https://www.google.com https://maps.google.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if not app.debug:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(Exception)
    def unhandled_error(exc):
        # Preserve Flask HTTP exceptions and log only unexpected server errors.
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("request_id=%s unhandled application exception", getattr(g, "request_id", "-"))
        return render_template("main/error.html", code=500, message="Something went wrong. Please try again."), 500

    @app.errorhandler(403)
    def forbidden(_): return render_template("main/error.html", code=403, message="You do not have permission to access this area."), 403
    @app.errorhandler(404)
    def not_found(_): return render_template("main/error.html", code=404, message="That page could not be found."), 404
    @app.errorhandler(413)
    def too_large(_): return render_template("main/error.html", code=413, message="The uploaded file is too large."), 413
    return app
