"""Login and account state regression tests."""

from app.extensions import db
from app.models import User


def test_invalid_credentials_are_rejected(client):
    response = client.post("/auth/login", data={
        "email": "missing@example.com",
        "password": "IncorrectPassword123",
    })
    assert response.status_code == 401


def test_inactive_account_cannot_log_in(client, app):
    with app.app_context():
        user = User.query.filter_by(email="learner@mawiz.local").one()
        user.is_active = False
        db.session.commit()
    response = client.post("/auth/login", data={
        "email": "learner@mawiz.local",
        "password": "ChangeMe!Learner123",
    })
    assert response.status_code == 401


def test_verified_learner_can_log_in(client):
    response = client.post("/auth/login", data={
        "email": "learner@mawiz.local",
        "password": "ChangeMe!Learner123",
    })
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session.get("user_id") is not None


def test_logged_in_user_can_open_change_password_page(client, login_as, learner_id):
    login_as(learner_id)
    response = client.get("/auth/change-password")
    assert response.status_code == 200
