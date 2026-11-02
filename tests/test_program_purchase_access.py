from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.models import Course, Enrollment, ProgramEnrollment, Track, User


def _program_with_course(title, slug, price=0):
    track = Track(title=title, slug=slug, description=f"{title} description", published=True,
                  price_amount=price, price_currency="NGN")
    course = Course(title=f"{title} Course", slug=f"{slug}-course", description="Course description",
                    stage="hard_skills", duration_value=30, duration_unit="days", published=True)
    track.courses = [course]
    db.session.add(track)
    db.session.flush()
    return track, course


def test_program_purchase_grants_only_its_courses_and_starts_deadline_from_purchase(app, client, login_as, learner_id):
    with app.app_context():
        learner = db.session.get(User, learner_id)
        first_track, first_course = _program_with_course("Program Alpha", "program-alpha")
        second_track, second_course = _program_with_course("Program Beta", "program-beta")
        db.session.commit()
        first_track_id, first_course_slug = first_track.id, first_course.slug
        second_course_slug = second_course.slug

    login_as(learner_id)
    blocked = client.get(f"/learning/courses/{first_course_slug}")
    assert blocked.status_code == 302
    assert "/programs" in blocked.headers["Location"]

    purchased = client.post(f"/learning/programs/{first_track_id}/checkout")
    assert purchased.status_code == 302
    assert "/program/" in purchased.headers["Location"]

    with app.app_context():
        entitlement = ProgramEnrollment.query.filter_by(user_id=learner_id, track_id=first_track_id, status="active").first()
        enrollment = Enrollment.query.filter_by(user_id=learner_id, course_id=Course.query.filter_by(slug=first_course_slug).first().id).first()
        assert entitlement is not None
        assert enrollment is not None
        assert enrollment.started_at is not None
        assert enrollment.deadline_at is not None
        assert abs((enrollment.deadline_at - enrollment.started_at).total_seconds() - 30 * 86400) < 5

    allowed = client.get(f"/learning/courses/{first_course_slug}")
    assert allowed.status_code == 200
    blocked_other_program = client.get(f"/learning/courses/{second_course_slug}")
    assert blocked_other_program.status_code == 302
    assert "/programs" in blocked_other_program.headers["Location"]


def test_individual_course_checkout_is_disabled(app, client, login_as, learner_id):
    with app.app_context():
        track, course = _program_with_course("Program Gamma", "program-gamma")
        db.session.commit()
        course_id = course.id
    login_as(learner_id)
    response = client.post(f"/learning/courses/{course_id}/checkout")
    assert response.status_code == 302
    assert "/programs" in response.headers["Location"]
