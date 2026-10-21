from app.extensions import db
from app.models import Course, CoursePayment, CoursePrice, Enrollment, User

def test_home(client):
    assert client.get('/').status_code==200


def test_csrf_token_is_not_rendered_as_visible_text(client):
    response=client.get('/auth/login')
    assert b'name="csrf_token"' in response.data
    assert b'csrf_token">' not in response.data


def test_register_requires_verification(client):
    r=client.post('/auth/register',data={'first_name':'Test','last_name':'User','username':'test-user','email':'test@example.com','password':'StrongPassword123','career_path':'job'})
    assert r.status_code==302
    r=client.post('/auth/login',data={'email':'test@example.com','password':'StrongPassword123'})
    assert r.status_code==403


def test_registration_does_not_require_or_store_learning_path(client):
    response = client.post('/auth/register', data={'first_name':'Path','last_name':'Learner','username':'path-learner','email':'path@example.com','password':'StrongPassword123'})
    assert response.status_code == 302
    with client.application.app_context():
        user = User.query.filter_by(email='path@example.com').first()
        assert user is not None
        assert user.profile.career_path is None


def test_new_learner_can_start_courses_before_career_path_choice(client):
    client.post('/auth/register', data={'first_name':'New','last_name':'Learner','username':'new-path-learner','email':'newpath@example.com','password':'StrongPassword123'})
    response = client.post('/auth/login', data={'email':'newpath@example.com','password':'StrongPassword123'})
    assert response.status_code == 403  # email verification is required in this test configuration

    with client.application.app_context():
        user = User.query.filter_by(email='newpath@example.com').first()
        user.email_verified = True
        db.session.commit()
        learner_id = user.id
    response = client.post('/auth/login', data={'email':'newpath@example.com','password':'StrongPassword123'})
    assert response.status_code == 302
    assert '/learning/courses?first_login=1' in response.headers['Location']

    with client.session_transaction() as sess:
        sess['user_id'] = learner_id
    page = client.get('/learner/learning-path')
    assert page.status_code == 200
    assert b'Hard Skills' in page.data
    assert b'Soft Skills' in page.data
    assert b'Work Simulation' in page.data
    assert b'Career Path' in page.data
    assert b'Complete all Hard Skills courses to unlock this stage' in page.data
    # Career choice is a final stage and cannot be made before progression is complete.
    saved = client.post('/learner/learning-path', data={'career_path':'job'}, follow_redirects=True)
    assert saved.status_code == 200
    with client.application.app_context():
        user = User.query.filter_by(email='newpath@example.com').first()
        assert user.profile.career_path is None


def test_first_learner_login_opens_course_selection_and_blocks_paid_enrollment(client):
    with client.application.app_context():
        learner = User.query.filter_by(email='learner@mawiz.local').first()
        course = Course.query.filter_by(published=True).first()
        assert learner and course
        Enrollment.query.filter_by(user_id=learner.id).delete()
        learner.profile.career_path = learner.profile.career_path or "job"
        if not course.price:
            db.session.add(CoursePrice(course_id=course.id, amount=1000, currency='NGN'))
        else:
            course.price.amount = 1000
        db.session.commit()
        learner_id = learner.id
        course_id = course.id
    with client.session_transaction() as sess:
        sess['user_id'] = learner_id
    catalog = client.get('/learning/courses?first_login=1')
    assert catalog.status_code == 200
    assert b'Choose your first course' in catalog.data
    response = client.post(f'/learning/courses/{course_id}/enroll', follow_redirects=True)
    assert response.status_code == 200
    assert b'Continue to secure checkout' in response.data
    with client.application.app_context():
        assert Enrollment.query.filter_by(user_id=learner_id, course_id=course_id).first() is None



def test_courses_are_available_before_career_path_is_chosen(client):
    with client.application.app_context():
        learner = User.query.filter_by(email='learner@mawiz.local').first()
        assert learner and learner.profile
        learner.profile.career_path = None
        db.session.commit()
        learner_id = learner.id
    with client.session_transaction() as sess:
        sess['user_id'] = learner_id

    response = client.get('/learning/courses')
    assert response.status_code == 200

    response = client.get('/learner/learning-path')
    assert response.status_code == 200
    assert b'Hard Skills' in response.data
    assert b'Career Path' in response.data


def test_public_learner_profile_uses_singular_username_url_and_legacy_redirect(client):
    with client.application.app_context():
        learner = User.query.filter_by(email="learner@mawiz.local").first()
        assert learner is not None
        username = learner.username
    canonical = client.get(f"/learner/{username}")
    assert canonical.status_code == 200
    legacy = client.get(f"/learners/{username}")
    assert legacy.status_code == 301
    assert legacy.headers["Location"].endswith(f"/learner/{username}")


def test_profile_picture_upload_accepts_real_jpeg_signature(client, tmp_path):
    from io import BytesIO
    from pathlib import Path
    with client.application.app_context():
        learner = User.query.filter_by(email="learner@mawiz.local").first()
        assert learner is not None
        learner_id = learner.id
        client.application.static_folder = str(tmp_path)
    with client.session_transaction() as sess:
        sess["user_id"] = learner_id
    # JPEG files begin with the three-byte SOI marker. The upload route checks
    # this signature before storing the file; production uploads are ordinary
    # user-provided image files, not this minimal fixture.
    response = client.post(
        "/learner/profile/upload",
        data={"profile_picture": (BytesIO(b"\xff\xd8\xff" + b"test-image-content"), "avatar.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        learner = db.session.get(User, learner_id)
        assert learner.profile.profile_picture.startswith("uploads/profile_pictures/user-")
        assert list((Path(tmp_path) / "uploads" / "profile_pictures").glob("*.jpg"))


def test_paystack_checkout_creates_pending_payment_and_redirects(client, monkeypatch):
    with client.application.app_context():
        learner = User.query.filter_by(email="learner@mawiz.local").first()
        course = Course.query.filter_by(published=True).first()
        assert learner and course
        Enrollment.query.filter_by(user_id=learner.id).delete()
        course.stage = "hard_skills"
        if not course.price:
            db.session.add(CoursePrice(course_id=course.id, amount=12500, currency="NGN"))
        else:
            course.price.amount = 12500
            course.price.currency = "NGN"
        db.session.commit()
        learner_id, course_id = learner.id, course.id

    with client.session_transaction() as sess:
        sess["user_id"] = learner_id

    def fake_paystack(path, method="GET", payload=None):
        assert path == "/transaction/initialize"
        assert method == "POST"
        assert payload["amount"] == 1250000
        assert payload["currency"] == "NGN"
        assert payload["email"] == "learner@mawiz.local"
        assert payload["metadata"]["course_id"] == course_id
        return {"authorization_url": "https://checkout.paystack.com/test-session"}

    monkeypatch.setattr("app.learning.routes._paystack_request", fake_paystack)
    response = client.post(f"/learning/courses/{course_id}/checkout")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://checkout.paystack.com/test-session"
    with client.application.app_context():
        payment = CoursePayment.query.filter_by(user_id=learner_id, course_id=course_id).first()
        assert payment is not None
        assert payment.status == "pending"
        assert payment.amount == 12500
        assert Enrollment.query.filter_by(user_id=learner_id, course_id=course_id).first() is None


def test_admin_can_view_payment_management_page(client):
    with client.application.app_context():
        admin = User.query.filter_by(role="admin").first()
        assert admin is not None
        admin_id = admin.id
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    response = client.get("/admin/payments")
    assert response.status_code == 200
    assert b"Course payments" in response.data


def test_learner_payment_history_is_scoped_to_signed_in_learner(client):
    with client.application.app_context():
        learner = User.query.filter_by(email="learner@mawiz.local").first()
        course = Course.query.filter_by(published=True).first()
        assert learner and course
        payment = CoursePayment(user_id=learner.id, course_id=course.id, reference="history-test-reference", amount=1000, currency="NGN", status="pending")
        db.session.add(payment)
        db.session.commit()
        learner_id = learner.id
    with client.session_transaction() as sess:
        sess["user_id"] = learner_id
    response = client.get("/learning/payments")
    assert response.status_code == 200
    assert b"Payment history" in response.data
    assert b"history-test-reference" in response.data
