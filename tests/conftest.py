"""Shared isolated fixtures for the Mawiz Academy test suite."""

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.seed import seed
from app.common.settings import set_setting
from app.models import User


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    WTF_CSRF_CHECK_DEFAULT = False
    RATELIMIT_ENABLED = False
    SECRET_KEY = "test-secret-key-not-for-production"
    REQUIRE_EMAIL_VERIFICATION = True
    REQUIRE_EMAIL_2FA = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    MAIL_BACKEND = "console"
    LOG_LEVEL = "CRITICAL"


@pytest.fixture()
def app(tmp_path):
    """Create a fresh in-memory app and database for each test."""
    app = create_app(TestConfig)
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        WTF_CSRF_CHECK_DEFAULT=False,
        RATELIMIT_ENABLED=False,
        MAIL_SINK_PATH=str(tmp_path / "mail.log"),
        LOG_FILE=str(tmp_path / "test.log"),
    )
    with app.app_context():
        db.create_all()
        seed()
        # Explicitly set database-backed switches so a local .env or stale
        # setting cannot change the intended behavior of an auth test.
        set_setting("registration_enabled", "1")
        set_setting("email_verification_required", "1")
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_id(app):
    with app.app_context():
        admin = User.query.filter_by(email="admin@mawiz.local").first()
        assert admin is not None
        return admin.id


@pytest.fixture()
def learner_id(app):
    with app.app_context():
        learner = User.query.filter_by(email="learner@mawiz.local").first()
        assert learner is not None
        return learner.id


@pytest.fixture()
def login_as(client):
    """Return a helper that authenticates a seeded user in the test session."""
    def _login(user_id):
        with client.session_transaction() as session:
            session["user_id"] = user_id
    return _login
