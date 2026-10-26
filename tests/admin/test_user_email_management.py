"""Regression tests for administrator-managed account email addresses."""

from app.extensions import db
from app.models import User


def _account_form(email, role="learner"):
    return {
        "email": email,
        "role": role,
        "is_active": "on",
        "first_name": "Test Learner",
        "last_name": "Account",
        "headline": "",
    }


def test_admin_can_change_learner_email_and_resets_verification(
    app, client, login_as, admin_id, learner_id
):
    login_as(admin_id)
    with app.app_context():
        learner = db.session.get(User, learner_id)
        learner.email_verified = True
        db.session.commit()

    response = client.post(
        f"/admin/users/{learner_id}",
        data=_account_form("new.learner@example.com"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        learner = db.session.get(User, learner_id)
        assert learner.email == "new.learner@example.com"
        assert learner.email_verified is False


def test_admin_cannot_change_email_to_an_invalid_address(
    app, client, login_as, admin_id, learner_id
):
    login_as(admin_id)
    with app.app_context():
        original_email = db.session.get(User, learner_id).email

    response = client.post(
        f"/admin/users/{learner_id}",
        data=_account_form("not-an-email"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(User, learner_id).email == original_email
    assert b"Enter a valid email address." in response.data


def test_admin_cannot_use_another_accounts_email(
    app, client, login_as, admin_id, learner_id
):
    login_as(admin_id)
    with app.app_context():
        admin = db.session.get(User, admin_id)
        admin.email = "admin@example.com"  # Use a syntactically valid address for the uniqueness check.
        db.session.commit()
        admin_email = admin.email
        learner_email = db.session.get(User, learner_id).email

    response = client.post(
        f"/admin/users/{learner_id}",
        data=_account_form(admin_email),
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(User, learner_id).email == learner_email
    assert b"already used by another account" in response.data
