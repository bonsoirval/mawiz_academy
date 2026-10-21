"""Registration and email-verification regression tests."""

import pytest

from app.common.settings import set_setting
from app.extensions import db
from app.models import User
from app.auth.routes import _token


def registration_form(**overrides):
    form = {
        "first_name": "Test",
        "last_name": "Learner",
        "username": "test-learner",
        "email": "test.learner@example.com",
        "password": "StrongPassword123",
    }
    form.update(overrides)
    return form


def test_registration_page_is_available(client):
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert b"Register" in response.data or b"Create account" in response.data


def test_registration_creates_unverified_learner_and_sends_verification_email(client, app):
    response = client.post("/auth/register", data=registration_form())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")

    with app.app_context():
        user = User.query.filter_by(email="test.learner@example.com").one()
        assert user.role == "learner"
        assert user.email_verified is False
        assert user.profile.first_name == "Test"
        assert user.profile.last_name == "Learner"
        assert user.profile.career_path is None
        assert user.check_password("StrongPassword123")
        assert (user.username == "test-learner")

    mail_file = app.config["MAIL_SINK_PATH"]
    with open(mail_file, encoding="utf-8") as handle:
        mail = handle.read()
    assert "test.learner@example.com" in mail
    assert "verify" in mail.lower()


def test_registration_does_not_require_or_store_career_path(client, app):
    response = client.post("/auth/register", data=registration_form(
        username="path-learner", email="path.learner@example.com"
    ))
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="path.learner@example.com").one()
        assert user.profile.career_path is None


def test_unverified_user_cannot_log_in(client):
    client.post("/auth/register", data=registration_form())
    response = client.post("/auth/login", data={
        "email": "test.learner@example.com",
        "password": "StrongPassword123",
    })
    assert response.status_code == 403


def test_valid_verification_token_allows_login(client, app):
    client.post("/auth/register", data=registration_form())
    with app.app_context():
        user = User.query.filter_by(email="test.learner@example.com").one()
        token = _token(user, "email_verify")
    verify_response = client.get(f"/auth/verify/{token}")
    assert verify_response.status_code == 302
    login_response = client.post("/auth/login", data={
        "email": "test.learner@example.com",
        "password": "StrongPassword123",
    })
    assert login_response.status_code == 302


def test_invalid_verification_token_does_not_verify_account(client, app):
    client.post("/auth/register", data=registration_form())
    response = client.get("/auth/verify/not-a-valid-token")
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="test.learner@example.com").one()
        assert user.email_verified is False


@pytest.mark.parametrize("email", ["", "not-an-email", "bad@"])
def test_invalid_email_is_rejected(client, email):
    response = client.post("/auth/register", data=registration_form(email=email))
    assert response.status_code == 200
    with client.application.app_context():
        assert User.query.filter_by(username="test-learner").first() is None


@pytest.mark.parametrize("password", ["short", "alllowercase123", "NoDigitsHere"])
def test_weak_password_is_rejected(client, password):
    response = client.post("/auth/register", data=registration_form(password=password))
    assert response.status_code == 200
    with client.application.app_context():
        assert User.query.filter_by(username="test-learner").first() is None


def test_duplicate_email_is_rejected(client):
    client.post("/auth/register", data=registration_form())
    response = client.post("/auth/register", data=registration_form(
        username="another-user"
    ))
    assert response.status_code == 200
    with client.application.app_context():
        assert User.query.filter_by(email="test.learner@example.com").count() == 1


def test_duplicate_username_is_rejected(client):
    client.post("/auth/register", data=registration_form())
    response = client.post("/auth/register", data=registration_form(
        email="different@example.com"
    ))
    assert response.status_code == 200
    with client.application.app_context():
        assert User.query.filter_by(username="test-learner").count() == 1


def test_registration_can_be_disabled_by_admin_setting(client, app):
    with app.app_context():
        set_setting("registration_enabled", "0")
        db.session.commit()
    response = client.post("/auth/register", data=registration_form())
    assert response.status_code == 403
    with app.app_context():
        assert User.query.filter_by(email="test.learner@example.com").first() is None


def test_resend_verification_has_generic_response(client):
    response = client.post("/auth/resend-verification", data={"email": "unknown@example.com"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")
