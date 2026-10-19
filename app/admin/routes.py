"""Administrator and instructor operations for learning, users, and reporting."""

import json
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from sqlalchemy import func, or_
from app.common.security import permission_required, audit, current_user
from app.common.settings import get_setting
from app.extensions import db
from app.models import (
    User, Profile, Course, Module, Lesson, Quiz, QuizQuestion, Project,
    Simulation, ProjectSubmission, AssignmentSubmission, Permission, UserPermission, RolePermission,
    Enrollment, LessonProgress, QuizAttempt, AssessmentAttempt, PortfolioItem,
    SimulationAttempt, AuditEvent, Referral, ReferralEvent, Coupon, CouponRedemption, SystemSetting, Track, TrackCourse, CoursePrice, CoursePayment, Assignment, ModuleQuiz, Skill, CareerPathContent
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
COURSE_DURATION_UNITS = {"days", "weeks", "months", "years"}
DEFAULT_ROLE_PASSWORDS = {
    "learner": "ChangeMe!Learner123",
    "instructor": "ChangeMe!Instructor123",
    "mentor": "ChangeMe!Mentor123",
}


def _safe_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _user_name(user):
    if user.profile:
        return f"{user.profile.first_name} {user.profile.last_name}".strip()
    return user.email


def _youtube_embed_url(value):
    parsed = urlparse((value or "").strip())
    host = parsed.netloc.lower().split(":")[0]
    video_id = ""
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/")):
            video_id = parsed.path.strip("/").split("/")[1] if len(parsed.path.strip("/").split("/")) > 1 else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return None
    return f"https://www.youtube-nocookie.com/embed/{video_id}"


@admin_bp.route("/")
@permission_required("admin.dashboard.view", "admin")
def dashboard():
    users = User.query.count()
    learners = User.query.filter_by(role="learner").count()
    instructors = User.query.filter_by(role="instructor").count()
    mentors = User.query.filter_by(role="mentor").count()
    active_users = User.query.filter_by(is_active=True).count()
    courses = Course.query.count()
    published_courses = Course.query.filter_by(published=True).count()
    enrollments = Enrollment.query.count()
    submissions = ProjectSubmission.query.count()
    pending_submissions = ProjectSubmission.query.filter_by(status="pending").count()
    assessments = AssessmentAttempt.query.count()
    quiz_attempts = QuizAttempt.query.count()
    portfolio_items = PortfolioItem.query.count()

    recent_users = User.query.order_by(User.created_at.desc()).limit(7).all()
    recent_audit = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(10).all()
    recent_submissions = ProjectSubmission.query.order_by(ProjectSubmission.submitted_at.desc()).limit(6).all()
    project_map = {p.id: p for p in Project.query.all()}
    user_ids = {event.user_id for event in recent_audit if event.user_id}
    user_ids.update(s.learner_id for s in recent_submissions)
    user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return render_template(
        "admin/dashboard.html",
        users=users, learners=learners, instructors=instructors, mentors=mentors,
        active_users=active_users, courses=courses, published_courses=published_courses,
        enrollments=enrollments, submissions=submissions, pending_submissions=pending_submissions,
        assessments=assessments, quiz_attempts=quiz_attempts, portfolio_items=portfolio_items,
        recent_users=recent_users, recent_audit=recent_audit, recent_submissions=recent_submissions,
        project_map=project_map, user_map=user_map,
    )


@admin_bp.route("/payments")
@permission_required("admin.dashboard.view", "admin")
def payments():
    """Show recent course and deadline-penalty transactions for administrators."""
    status = request.args.get("status", "").strip().lower()
    search = request.args.get("q", "").strip()[:120]
    query = CoursePayment.query
    if status in {"pending", "success", "failed", "abandoned", "initialization_failed", "verification_failed", "ongoing", "processing", "reversed"}:
        query = query.filter(CoursePayment.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.join(User, CoursePayment.user_id == User.id).join(Course, CoursePayment.course_id == Course.id).filter(
            or_(User.email.ilike(pattern), Course.title.ilike(pattern), CoursePayment.reference.ilike(pattern))
        )
    rows = query.order_by(CoursePayment.created_at.desc()).limit(250).all()
    totals = {
        "count": CoursePayment.query.count(),
        "successful": CoursePayment.query.filter_by(status="success").count(),
        "pending": CoursePayment.query.filter_by(status="pending").count(),
    }
    return render_template("admin/payments.html", payments=rows, status=status, search=search, totals=totals)


@admin_bp.route("/users")
@permission_required("admin.dashboard.view", "admin")
def users():
    role = request.args.get("role", "").strip()
    status = request.args.get("status", "").strip()
    query = User.query
    if role in {"learner", "instructor", "mentor", "admin"}:
        query = query.filter_by(role=role)
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)
    user_list = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=user_list, role=role, status=status)


@admin_bp.post("/users/<int:user_id>/resend-verification")
@permission_required("admin.dashboard.view", "admin")
def admin_resend_verification(user_id):
    """Send a fresh verification link to an active, unverified account."""
    user = User.query.get_or_404(user_id)
    if not user.is_active:
        flash("Activate the user before sending a verification email.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    if user.email_verified:
        flash("This user's email is already verified.", "info")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    from app.auth.routes import _email_content, _send_mail, _token
    try:
        link = url_for("auth.verify_email", token=_token(user, "email_verify"), _external=True)
        subject, body = _email_content("verification", link=link, email=user.email)
        _send_mail(subject, user.email, body)
        audit("admin.user_verification_email_resent")
        db.session.commit()
        flash("A fresh verification email has been sent.", "success")
    except Exception:
        current_app.logger.exception("Admin could not resend verification email")
        flash("The verification email could not be sent. Check the email configuration and logs.", "error")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin")
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        if role not in {"learner", "instructor", "mentor", "admin"}:
            flash("Invalid role selected.", "error")
            return redirect(url_for("admin.user_detail", user_id=user.id))
        if user.id == current_user().id and role != "admin":
            flash("You cannot remove your own administrator role.", "error")
            return redirect(url_for("admin.user_detail", user_id=user.id))
        if user.id == current_user().id and request.form.get("is_active") != "on":
            flash("You cannot deactivate your own account.", "error")
            return redirect(url_for("admin.user_detail", user_id=user.id))
        old_role = user.role
        user.role = role
        user.is_active = request.form.get("is_active") == "on"
        if not user.profile:
            user.profile = Profile(first_name=user.email.split("@")[0][:100], last_name="", onboarding_completed=False)
        user.profile.first_name = request.form.get("first_name", "").strip()[:100] or user.profile.first_name
        user.profile.last_name = request.form.get("last_name", "").strip()[:100]
        user.profile.headline = request.form.get("headline", "").strip()[:255]
        audit("admin.user_updated")
        db.session.commit()
        if old_role != user.role:
            audit("admin.user_role_changed")
            db.session.commit()
        flash("User account updated.", "success")
        return redirect(url_for("admin.user_detail", user_id=user.id))

    overrides = UserPermission.query.filter_by(user_id=user.id).all()
    permissions = Permission.query.order_by(Permission.code).all()
    override_map = {item.permission_id: item for item in overrides}
    enrollment_rows = Enrollment.query.filter_by(user_id=user.id).all()
    course_map = {course.id: course for course in Course.query.filter(Course.id.in_([e.course_id for e in enrollment_rows])).all()} if enrollment_rows else {}
    attempts = QuizAttempt.query.filter_by(learner_id=user.id).order_by(QuizAttempt.completed_at.desc()).limit(8).all()
    assessment_attempts = AssessmentAttempt.query.filter_by(learner_id=user.id).order_by(AssessmentAttempt.completed_at.desc()).limit(8).all()
    portfolio_items = PortfolioItem.query.filter_by(learner_id=user.id).order_by(PortfolioItem.created_at.desc()).limit(8).all()
    return render_template(
        "admin/user_detail.html", user=user, permissions=permissions,
        override_map=override_map, enrollment_rows=enrollment_rows, course_map=course_map,
        attempts=attempts, assessment_attempts=assessment_attempts, portfolio_items=portfolio_items,
    )


@admin_bp.post("/users/<int:user_id>/password-reset")
@permission_required("admin.dashboard.view", "admin")
def admin_password_reset(user_id):
    user = User.query.get_or_404(user_id)
    if not user.is_active:
        flash("Activate the user before sending a password reset.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    from app.auth.routes import _send_mail, _token
    reset_link = url_for("auth.reset_password", token=_token(user, "password_reset"), _external=True)
    try:
        from app.auth.routes import _email_content
        subject, body = _email_content("password_reset", link=reset_link, email=user.email)
        _send_mail(subject, user.email, body)
        audit("admin.password_reset_requested")
        db.session.commit()
        flash(f"Password reset instructions were sent to {user.email}.", "success")
    except Exception:
        db.session.rollback()
        flash("The password reset email could not be sent. Check the mail settings.", "error")
    return redirect(url_for("admin.user_detail", user_id=user.id))

@admin_bp.post("/users/<int:user_id>/password-reset-default")
@permission_required("admin.dashboard.view", "admin")
def admin_password_reset_default(user_id):
    """Reset a learner, instructor, or mentor to that role's standard password."""
    user = User.query.get_or_404(user_id)
    default_password = DEFAULT_ROLE_PASSWORDS.get(user.role)
    if not default_password:
        flash("Default password reset is available only for learners, instructors, and mentors.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))

    user.set_password(default_password)
    audit("admin.password_reset_to_default")
    db.session.commit()
    flash(f"Password reset for {user.email}. The password was not displayed. Ask the user to change it after signing in.", "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.post("/users/<int:user_id>/permissions")
@permission_required("admin.dashboard.view", "admin")
def update_user_permissions(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user().id:
        flash("Manage another administrator's overrides instead of your own.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    permission_id = _safe_int(request.form.get("permission_id"), minimum=1)
    permission = db.session.get(Permission, permission_id)
    if not permission:
        flash("Permission not found.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    allowed = request.form.get("allowed") == "true"
    override = UserPermission.query.filter_by(user_id=user.id, permission_id=permission.id).first()
    if override:
        override.allowed = allowed
    else:
        db.session.add(UserPermission(user_id=user.id, permission_id=permission.id, allowed=allowed))
    audit("admin.user_permission_override_updated")
    db.session.commit()
    flash("Permission override saved.", "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.post("/users/<int:user_id>/permissions/<int:permission_id>/reset")
@permission_required("admin.dashboard.view", "admin")
def reset_user_permission(user_id, permission_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user().id:
        flash("You cannot reset your own permission overrides from this screen.", "error")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    override = UserPermission.query.filter_by(user_id=user.id, permission_id=permission_id).first()
    if override:
        db.session.delete(override)
        audit("admin.user_permission_override_reset")
        db.session.commit()
        flash("Permission now follows the user's role.", "success")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.route("/activity")
@permission_required("admin.dashboard.view", "admin")
def activity():
    events = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(100).all()
    user_ids = {event.user_id for event in events if event.user_id}
    user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return render_template("admin/activity.html", events=events, user_map=user_map)


@admin_bp.route("/system-logs")
@permission_required("admin.dashboard.view", "admin")
def system_logs():
    """Show a bounded, read-only tail of the rotating application log."""
    log_path = Path(current_app.config.get("LOG_FILE") or (Path(current_app.instance_path) / "logs" / "mawiz.log"))
    level_filter = request.args.get("level", "ALL").upper()
    if level_filter not in {"ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level_filter = "ALL"
    query = request.args.get("q", "").strip()[:100]
    lines = []
    # Only read the configured log and its configured rotation siblings.
    backup_count = max(1, int(current_app.config.get("LOG_BACKUP_COUNT", 5)))
    for candidate in [log_path] + [Path(str(log_path) + f".{i}") for i in range(1, backup_count + 1)]:
        try:
            with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                lines.extend(handle.readlines()[-1500:])
        except OSError:
            continue
    lines = lines[-4000:]
    if level_filter != "ALL":
        lines = [line for line in lines if re.search(rf"\b{re.escape(level_filter)}\b", line)]
    if query:
        lines = [line for line in lines if query.casefold() in line.casefold()]
    entries = list(reversed(lines[-500:]))
    return render_template("admin/system_logs.html", entries=entries, level_filter=level_filter,
                           query=query, log_path=str(log_path), log_exists=log_path.exists())


@admin_bp.route("/assessments")
@permission_required("admin.dashboard.view", "admin")
def assessments():
    attempts = AssessmentAttempt.query.order_by(AssessmentAttempt.completed_at.desc()).limit(100).all()
    user_ids = {a.learner_id for a in attempts}
    user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return render_template("admin/assessments.html", attempts=attempts, user_map=user_map)


@admin_bp.route("/submissions")
@permission_required("admin.dashboard.view", "admin")
def submissions():
    # The project-management table can link directly to a review queue for one project.
    project_id = _safe_int(request.args.get("project_id"), 0, 1)
    query = ProjectSubmission.query
    selected_project = None
    if project_id:
        selected_project = Project.query.get_or_404(project_id)
        query = query.filter_by(project_id=project_id)
    rows = query.order_by(ProjectSubmission.submitted_at.desc()).limit(200).all()
    user_ids = {row.learner_id for row in rows}
    project_ids = {row.project_id for row in rows}
    user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    project_map = {p.id: p for p in Project.query.filter(Project.id.in_(project_ids)).all()} if project_ids else {}
    return render_template("admin/submissions.html", submissions=rows, user_map=user_map, project_map=project_map, selected_project=selected_project)


@admin_bp.post("/submissions/<int:submission_id>/status")
@permission_required("admin.dashboard.view", "admin")
def submission_status(submission_id):
    submission = ProjectSubmission.query.get_or_404(submission_id)
    status = request.form.get("status", "").strip()
    if status not in {"pending", "in_review", "approved", "revision_requested", "rejected"}:
        flash("Invalid submission status.", "error")
    else:
        submission.status = status
        audit("admin.project_submission_status_changed")
        db.session.commit()
        flash("Submission status updated.", "success")
    project_id = _safe_int(request.form.get("project_id"), 0, 1)
    return redirect(url_for("admin.submissions", project_id=project_id) if project_id else url_for("admin.submissions"))


@admin_bp.route("/marking", methods=["GET"])
@permission_required("admin.courses.manage", "admin", "instructor")
def course_marking():
    submissions = AssignmentSubmission.query.order_by(AssignmentSubmission.submitted_at.desc()).limit(200).all()
    learner_ids = {row.learner_id for row in submissions}
    learners = {u.id: u for u in User.query.filter(User.id.in_(learner_ids)).all()} if learner_ids else {}
    assignments = {a.id: a for a in Assignment.query.all()}
    quiz_attempts = QuizAttempt.query.order_by(QuizAttempt.completed_at.desc()).limit(100).all()
    quiz_ids = {a.quiz_id for a in quiz_attempts}
    quizzes = {q.id: q for q in Quiz.query.filter(Quiz.id.in_(quiz_ids)).all()} if quiz_ids else {}
    quiz_learners = {a.learner_id for a in quiz_attempts}
    learners.update({u.id: u for u in User.query.filter(User.id.in_(quiz_learners)).all()} if quiz_learners else {})
    return render_template("instructor/marking.html", submissions=submissions, learners=learners,
                           assignments=assignments, quiz_attempts=quiz_attempts, quizzes=quizzes)


@admin_bp.post("/marking/assignments/<int:submission_id>")
@permission_required("admin.courses.manage", "admin", "instructor")
def mark_assignment(submission_id):
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    try:
        score = int(request.form.get("score", ""))
        max_score = int(request.form.get("max_score", ""))
    except (TypeError, ValueError):
        flash("Enter valid numeric marks.", "error")
        return redirect(url_for("admin.course_marking"))
    if max_score < 1 or score < 0 or score > max_score:
        flash("Score must be between zero and the maximum mark, and maximum mark must be positive.", "error")
        return redirect(url_for("admin.course_marking"))
    percent = (score / max_score) * 100
    grade = "A" if percent >= 90 else "B" if percent >= 80 else "C" if percent >= 70 else "D" if percent >= 60 else "F"
    submission.score = score
    submission.max_score = max_score
    submission.grade = grade
    submission.feedback = request.form.get("feedback", "").strip()[:5000]
    submission.status = "graded"
    submission.marked_at = datetime.now(timezone.utc)
    submission.marked_by_id = current_user().id
    audit("learning.assignment_marked")
    db.session.commit()
    flash(f"Assignment marked: {score}/{max_score} ({grade}).", "success")
    return redirect(url_for("admin.course_marking"))


@admin_bp.route("/permissions")
@permission_required("admin.dashboard.view", "admin")
def permissions():
    permissions = Permission.query.order_by(Permission.code).all()
    role_rows = {role: {rp.permission_id for rp in RolePermission.query.filter_by(role=role).all()} for role in ("learner", "instructor", "mentor", "admin")}
    return render_template("admin/permissions.html", permissions=permissions, role_rows=role_rows)


def _project_context_from_form():
    """Resolve and validate the selected track/course/module/lesson hierarchy."""
    track_id = _safe_int(request.form.get("track_id"), 0, 1)
    course_id = _safe_int(request.form.get("course_id"), 0, 1)
    module_id = _safe_int(request.form.get("module_id"), 0, 1)
    lesson_id = _safe_int(request.form.get("lesson_id"), 0, 1)
    track = db.session.get(Track, track_id) if track_id else None
    course = db.session.get(Course, course_id) if course_id else None
    module = db.session.get(Module, module_id) if module_id else None
    lesson = db.session.get(Lesson, lesson_id) if lesson_id else None
    if track_id and not track:
        raise ValueError("Select a valid track.")
    if course_id and not course:
        raise ValueError("Select a valid course.")
    if module_id and not module:
        raise ValueError("Select a valid module.")
    if lesson_id and not lesson:
        raise ValueError("Select a valid lesson.")
    if lesson:
        if module and lesson.module_id != module.id:
            raise ValueError("The selected lesson does not belong to the selected module.")
        module = lesson.module
        module_id = module.id
    if module:
        if course and module.course_id != course.id:
            raise ValueError("The selected module does not belong to the selected course.")
        course = module.course
        course_id = course.id
    if track and course and track not in course.tracks:
        raise ValueError("The selected course does not belong to the selected track.")
    if track and not course and not module and not lesson:
        # A track-only project is valid and is available to learners enrolled in one of its courses.
        pass
    return track, course, module, lesson


def _project_form_values(project=None):
    try:
        track, course, module, lesson = _project_context_from_form()
    except ValueError as exc:
        flash(str(exc), "error")
        return False
    title = request.form.get("title", "").strip()[:200]
    problem = request.form.get("problem", "").strip()
    requirements = request.form.get("requirements", "").strip()
    if not title or not problem or not requirements:
        flash("Project title, problem statement and requirements are required.", "error")
        return False
    deadline_raw = request.form.get("deadline", "").strip()
    deadline = None
    if deadline_raw:
        try:
            deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            flash("Enter a valid deadline date.", "error")
            return False
    if project is None:
        project = Project()
        db.session.add(project)
    project.title = title
    project.problem = problem
    project.requirements = requirements
    project.deadline = deadline
    project.track = track
    project.course = course
    project.module = module
    project.lesson = lesson
    project.is_final_program_project = request.form.get("project_type") == "final"
    return project


@admin_bp.route("/projects", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin", "instructor")
def projects():
    if request.method == "POST":
        project = _project_form_values()
        if project:
            project.published = False
            audit("admin.project_created")
            db.session.commit()
            flash("Project created as a draft and linked to its learning context.", "success")
            return redirect(url_for("admin.projects"))
    projects = Project.query.order_by(Project.id.desc()).all()
    submission_counts = dict(
        db.session.query(ProjectSubmission.project_id, func.count(ProjectSubmission.id))
        .group_by(ProjectSubmission.project_id).all()
    )
    tracks = Track.query.order_by(Track.title.asc()).all()
    courses = Course.query.order_by(Course.title.asc()).all()
    modules = Module.query.join(Course).order_by(Course.title.asc(), Module.position.asc()).all()
    lessons = Lesson.query.join(Module).join(Course).order_by(Course.title.asc(), Module.position.asc(), Lesson.position.asc()).all()
    return render_template("admin/projects.html", projects=projects, submission_counts=submission_counts, tracks=tracks, courses=courses, modules=modules, lessons=lessons)


@admin_bp.post("/projects/<int:project_id>/edit")
@permission_required("admin.dashboard.view", "admin", "instructor")
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    updated = _project_form_values(project)
    if updated:
        audit("admin.project_updated")
        db.session.commit()
        flash("Project updated.", "success")
    else:
        db.session.rollback()
    return redirect(url_for("admin.projects"))


@admin_bp.post("/projects/<int:project_id>/publish")
@permission_required("admin.dashboard.view", "admin")
def publish_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.published = not project.published
    audit("admin.project_published" if project.published else "admin.project_unpublished")
    db.session.commit()
    flash("Project publication status updated.", "success")
    return redirect(url_for("admin.projects"))


@admin_bp.post("/projects/<int:project_id>/delete")
@permission_required("admin.dashboard.view", "admin")
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    # Keep submissions and the project together: deleting a project removes its submissions via FK cascade.
    db.session.delete(project)
    audit("admin.project_deleted")
    db.session.commit()
    flash("Project deleted.", "success")
    return redirect(url_for("admin.projects"))


@admin_bp.route("/simulations", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin", "instructor")
def simulations():
    tracks = Track.query.order_by(Track.title.asc()).all()
    courses = Course.query.order_by(Course.title.asc()).all()
    modules = Module.query.join(Course).order_by(Course.title.asc(), Module.position.asc()).all()
    lessons = Lesson.query.join(Module).join(Course).order_by(Course.title.asc(), Module.position.asc(), Lesson.position.asc()).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:200]
        scenario = request.form.get("scenario", "").strip()
        task = request.form.get("task", "").strip()
        if not title or not scenario or not task:
            flash("Simulation title, scenario and task are required.", "error")
        else:
            simulation = Simulation(title=title, scenario=scenario, task=task, published=False)
            simulation.tracks = Track.query.filter(Track.id.in_(_selected_ids("track_ids"))).all()
            simulation.courses = Course.query.filter(Course.id.in_(_selected_ids("course_ids"))).all()
            simulation.modules = Module.query.filter(Module.id.in_(_selected_ids("module_ids"))).all()
            simulation.lessons = Lesson.query.filter(Lesson.id.in_(_selected_ids("lesson_ids"))).all()
            db.session.add(simulation)
            audit("admin.simulation_created")
            db.session.commit()
            flash("Simulation created as a draft and linked to the selected learning content.", "success")
    return render_template("admin/simulations.html", simulations=Simulation.query.order_by(Simulation.id.desc()).all(), tracks=tracks, courses=courses, modules=modules, lessons=lessons)


def _selected_ids(field):
    values = set()
    for value in request.form.getlist(field):
        parsed = _safe_int(value, 0, 1)
        if parsed:
            values.add(parsed)
    return values


@admin_bp.post("/simulations/<int:simulation_id>/links")
@permission_required("admin.dashboard.view", "admin", "instructor")
def update_simulation_links(simulation_id):
    simulation = Simulation.query.get_or_404(simulation_id)
    title = request.form.get("title", "").strip()[:200]
    scenario = request.form.get("scenario", "").strip()
    task = request.form.get("task", "").strip()
    if title and scenario and task:
        simulation.title, simulation.scenario, simulation.task = title, scenario, task
    else:
        flash("Simulation title, scenario and learner task are required.", "error")
        return redirect(url_for("admin.simulations"))
    simulation.tracks = Track.query.filter(Track.id.in_(_selected_ids("track_ids"))).all()
    simulation.courses = Course.query.filter(Course.id.in_(_selected_ids("course_ids"))).all()
    simulation.modules = Module.query.filter(Module.id.in_(_selected_ids("module_ids"))).all()
    simulation.lessons = Lesson.query.filter(Lesson.id.in_(_selected_ids("lesson_ids"))).all()
    audit("admin.simulation_links_updated")
    db.session.commit()
    flash("Simulation learning links updated.", "success")
    return redirect(url_for("admin.simulations"))


@admin_bp.post("/simulations/<int:simulation_id>/publish")
@permission_required("admin.dashboard.view", "admin")
def publish_simulation(simulation_id):
    simulation = Simulation.query.get_or_404(simulation_id)
    simulation.published = not simulation.published
    audit("admin.simulation_published" if simulation.published else "admin.simulation_unpublished")
    db.session.commit()
    flash("Simulation publication status updated.", "success")
    return redirect(url_for("admin.simulations"))


@admin_bp.post("/simulations/<int:simulation_id>/delete")
@permission_required("admin.dashboard.view", "admin")
def delete_simulation(simulation_id):
    simulation = Simulation.query.get_or_404(simulation_id)
    db.session.delete(simulation)
    try:
        audit("admin.simulation_deleted")
        db.session.commit()
        flash("Simulation deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This simulation could not be deleted because related records still depend on it.", "error")
    return redirect(url_for("admin.simulations"))


@admin_bp.route("/career-path-content", methods=["GET", "POST"])
@permission_required("admin.courses.manage", "admin", "instructor")
def career_path_content_management():
    """Create and manage text, video, and flashcard resources per career path."""
    valid_paths = {"entrepreneurship", "job"}
    valid_types = {"text", "video", "flashcards"}
    if request.method == "POST":
        path_name = request.form.get("path_name", "").strip().lower()
        title = request.form.get("title", "").strip()[:200]
        content_type = request.form.get("content_type", "text").strip().lower()
        body = request.form.get("body", "").strip()
        video_url = request.form.get("video_url", "").strip()[:1000]
        if path_name not in valid_paths or content_type not in valid_types or not title:
            flash("Choose a valid career path, content type, and title.", "error")
        else:
            cards = []
            if content_type == "flashcards":
                for line in request.form.get("flashcards", "").splitlines():
                    if not line.strip(): continue
                    if "|" not in line:
                        flash("Each flashcard must use Front | Back format. No content was saved.", "error")
                        return redirect(url_for("admin.career_path_content_management"))
                    front, back = line.split("|", 1)
                    front, back = front.strip()[:1000], back.strip()[:1000]
                    if front and back: cards.append({"front": front, "back": back})
                if not cards:
                    flash("Add at least one flashcard using Front | Back format.", "error")
                    return redirect(url_for("admin.career_path_content_management"))
            if content_type == "video" and not video_url:
                flash("A video URL is required for video content.", "error")
                return redirect(url_for("admin.career_path_content_management"))
            if content_type == "text" and not body:
                flash("Text content is required for a text resource.", "error")
                return redirect(url_for("admin.career_path_content_management"))
            item = CareerPathContent(path_name=path_name, title=title, content_type=content_type,
                body=body, video_url=video_url or None, flashcards_json=json.dumps(cards),
                position=_safe_int(request.form.get("position"), 0, 0, 100000), published=False)
            db.session.add(item); audit("admin.career_path_content_created"); db.session.commit()
            flash("Career-path resource created as a draft.", "success")
        return redirect(url_for("admin.career_path_content_management"))
    items = CareerPathContent.query.order_by(CareerPathContent.path_name, CareerPathContent.position, CareerPathContent.id).all()
    cards_by_item = {}
    for item in items:
        try:
            cards_by_item[item.id] = json.loads(item.flashcards_json or "[]")
            if not isinstance(cards_by_item[item.id], list): cards_by_item[item.id] = []
        except (TypeError, ValueError):
            cards_by_item[item.id] = []
    return render_template("admin/career_path_content.html", items=items, cards_by_item=cards_by_item)


@admin_bp.post("/career-path-content/<int:item_id>/update")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_career_path_content(item_id):
    item = CareerPathContent.query.get_or_404(item_id)
    path_name = request.form.get("path_name", "").strip().lower()
    content_type = request.form.get("content_type", "text").strip().lower()
    title = request.form.get("title", "").strip()[:200]
    if path_name not in {"entrepreneurship", "job"} or content_type not in {"text", "video", "flashcards"} or not title:
        flash("Choose a valid career path, content type, and title.", "error")
        return redirect(url_for("admin.career_path_content_management"))
    body = request.form.get("body", "").strip()
    video_url = request.form.get("video_url", "").strip()[:1000]
    cards = []
    if content_type == "flashcards":
        for line in request.form.get("flashcards", "").splitlines():
            if not line.strip(): continue
            if "|" not in line:
                flash("Each flashcard must use Front | Back format.", "error")
                return redirect(url_for("admin.career_path_content_management"))
            front, back = line.split("|", 1)
            if front.strip() and back.strip(): cards.append({"front": front.strip()[:1000], "back": back.strip()[:1000]})
        if not cards:
            flash("Add at least one flashcard.", "error")
            return redirect(url_for("admin.career_path_content_management"))
    if content_type == "video" and not video_url:
        flash("A video URL is required.", "error"); return redirect(url_for("admin.career_path_content_management"))
    if content_type == "text" and not body:
        flash("Text content is required.", "error"); return redirect(url_for("admin.career_path_content_management"))
    item.path_name, item.title, item.content_type = path_name, title, content_type
    item.body, item.video_url, item.flashcards_json = body, video_url or None, json.dumps(cards)
    item.position = _safe_int(request.form.get("position"), item.position or 0, 0, 100000)
    audit("admin.career_path_content_updated"); db.session.commit()
    flash("Career-path resource updated.", "success")
    return redirect(url_for("admin.career_path_content_management"))


@admin_bp.post("/career-path-content/<int:item_id>/publish")
@permission_required("admin.courses.manage", "admin", "instructor")
def publish_career_path_content(item_id):
    item = CareerPathContent.query.get_or_404(item_id)
    item.published = not item.published
    audit("admin.career_path_content_published" if item.published else "admin.career_path_content_unpublished")
    db.session.commit()
    flash("Career-path resource publication status updated.", "success")
    return redirect(url_for("admin.career_path_content_management"))


@admin_bp.post("/career-path-content/<int:item_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_career_path_content(item_id):
    item = CareerPathContent.query.get_or_404(item_id)
    db.session.delete(item); audit("admin.career_path_content_deleted"); db.session.commit()
    flash("Career-path resource deleted.", "success")
    return redirect(url_for("admin.career_path_content_management"))


def _course_management_redirect(stage="hard_skills"):
    if stage not in {"hard_skills", "soft_skills", "career_path"}:
        stage = "hard_skills"
    return redirect(url_for("admin.courses", stage=stage))


@admin_bp.route("/courses", methods=["GET", "POST"])
@permission_required("admin.courses.manage", "admin", "instructor")
def courses():
    active_stage = request.args.get("stage", "hard_skills").strip().lower()
    if active_stage == "career_path":
        return redirect(url_for("admin.career_path_content_management"))
    if active_stage not in {"hard_skills", "soft_skills"}:
        active_stage = "hard_skills"
    tracks = Track.query.order_by(Track.title.asc()).all()
    skills = Skill.query.order_by(Skill.name.asc()).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:200]
        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
        track_id = _safe_int(request.form.get("track_id"), 0, 1)
        duration_value = _safe_int(request.form.get("duration_value"), 0, 1, 3650)
        duration_unit = request.form.get("duration_unit", "").strip().lower()
        if not title or not slug:
            flash("Course title is required.", "error")
        elif Course.query.filter_by(slug=slug).first():
            flash("A course with that title already exists.", "error")
        elif not duration_value or duration_unit not in COURSE_DURATION_UNITS:
            flash("Set a course duration using days, weeks, months, or years.", "error")
        else:
            stage = request.form.get("stage", "hard_skills").strip()
            if stage not in {"soft_skills", "hard_skills"}: stage = "hard_skills"
            course = Course(title=title, slug=slug, description=request.form.get("description", "").strip(), career_goal=request.form.get("career_goal", "").strip()[:150], stage=stage, duration_value=duration_value, duration_unit=duration_unit, published=False)
            db.session.add(course)
            db.session.flush()
            selected_skill_ids = {_safe_int(value, 0, 1) for value in request.form.getlist("skill_ids")}
            course.skills = [skill for skill in skills if skill.id in selected_skill_ids]
            if track_id:
                track = db.session.get(Track, track_id)
                if track:
                    track.courses.append(course)
            try:
                price = Decimal(request.form.get("price", "0"))
            except (InvalidOperation, TypeError):
                price = Decimal("0")
            if price >= 0:
                db.session.add(CoursePrice(course_id=course.id, amount=price, currency="NGN"))
            audit("admin.course_created")
            db.session.commit()
            flash("Course created as a draft.", "success")
    stage_courses = Course.query.filter_by(stage=active_stage).order_by(Course.id.desc()).all()
    return render_template("admin/courses.html", courses=stage_courses, tracks=tracks, skills=skills, active_stage=active_stage)


@admin_bp.post("/courses/<int:course_id>/skills")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_course_skills(course_id):
    course = Course.query.get_or_404(course_id)
    selected_skill_ids = {_safe_int(value, 0, 1) for value in request.form.getlist("skill_ids")}
    course.skills = Skill.query.filter(Skill.id.in_(selected_skill_ids)).order_by(Skill.name).all() if selected_skill_ids else []
    audit("admin.course_skills_updated")
    db.session.commit()
    flash("Course skills updated. Learners earn these skills when they complete the course.", "success")
    return _course_management_redirect(course.stage)


@admin_bp.post("/modules/<int:module_id>/skills")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_module_skills(module_id):
    module = Module.query.get_or_404(module_id)
    selected = _selected_ids("skill_ids")
    module.skills = Skill.query.filter(Skill.id.in_(selected)).order_by(Skill.name).all() if selected else []
    audit("admin.module_skills_updated")
    db.session.commit()
    flash("Skills awarded for this module's completion updated.", "success")
    return _course_management_redirect(module.course.stage)


@admin_bp.post("/lessons/<int:lesson_id>/skills")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_lesson_skills(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    selected = _selected_ids("skill_ids")
    lesson.skills = Skill.query.filter(Skill.id.in_(selected)).order_by(Skill.name).all() if selected else []
    audit("admin.lesson_skills_updated")
    db.session.commit()
    flash("Skills awarded for this lesson's completion updated.", "success")
    return _course_management_redirect(lesson.module.course.stage)


@admin_bp.post("/courses/<int:course_id>/schedule")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_course_schedule(course_id):
    course = Course.query.get_or_404(course_id)
    duration_value = _safe_int(request.form.get("duration_value"), 0, 1, 3650)
    duration_unit = request.form.get("duration_unit", "").strip().lower()
    if not duration_value or duration_unit not in COURSE_DURATION_UNITS:
        flash("Set a valid course duration.", "error")
    else:
        course.duration_value = duration_value
        course.duration_unit = duration_unit
        audit("admin.course_schedule_updated")
        db.session.commit()
        flash("Course duration updated.", "success")
    return _course_management_redirect(course.stage)


@admin_bp.post("/tracks")
@permission_required("admin.courses.manage", "admin", "instructor")
def create_track():
    title = request.form.get("title", "").strip()[:200]
    slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
    if not title or not slug:
        flash("Track title is required.", "error")
    elif Track.query.filter_by(slug=slug).first():
        flash("That track already exists.", "error")
    else:
        db.session.add(Track(title=title, slug=slug, description=request.form.get("description", "").strip(), published=False))
        audit("admin.track_created")
        db.session.commit()
        flash("Track created as a draft.", "success")
    return _course_management_redirect(request.form.get("stage", "hard_skills"))




@admin_bp.post("/tracks/<int:track_id>/edit")
@permission_required("admin.courses.manage", "admin", "instructor")
def edit_track(track_id):
    track = Track.query.get_or_404(track_id)
    title = request.form.get("title", "").strip()[:200]
    slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
    duplicate = Track.query.filter(Track.slug == slug, Track.id != track.id).first() if slug else None
    if not title or not slug or duplicate:
        flash("Enter a valid track title that is not already in use.", "error")
    else:
        track.title, track.slug = title, slug
        track.description = request.form.get("description", "").strip()
        audit("admin.track_updated"); db.session.commit(); flash("Track updated.", "success")
    return _course_management_redirect(request.form.get("stage", "hard_skills"))


@admin_bp.post("/courses/<int:course_id>/edit")
@permission_required("admin.courses.manage", "admin", "instructor")
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    title = request.form.get("title", "").strip()[:200]
    slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
    duplicate = Course.query.filter(Course.slug == slug, Course.id != course.id).first() if slug else None
    duration_value = _safe_int(request.form.get("duration_value"), 0, 1, 3650)
    duration_unit = request.form.get("duration_unit", "").strip().lower()
    stage = request.form.get("stage", course.stage).strip()
    if not title or not slug or duplicate:
        flash("Enter a valid course title that is not already in use.", "error")
    elif not duration_value or duration_unit not in COURSE_DURATION_UNITS or stage not in {"hard_skills", "soft_skills"}:
        flash("Check the course duration and stage.", "error")
    else:
        course.title, course.slug = title, slug
        course.description = request.form.get("description", "").strip()
        course.career_goal = request.form.get("career_goal", "").strip()[:150]
        course.duration_value, course.duration_unit, course.stage = duration_value, duration_unit, stage
        track_id = _safe_int(request.form.get("track_id"), 0, 1)
        track = db.session.get(Track, track_id) if track_id else None
        course.tracks = [track] if track else []
        selected = {_safe_int(v, 0, 1) for v in request.form.getlist("skill_ids")}
        course.skills = Skill.query.filter(Skill.id.in_(selected)).all() if selected else []
        audit("admin.course_updated"); db.session.commit(); flash("Course content updated.", "success")
    return _course_management_redirect(course.stage)


@admin_bp.post("/modules/<int:module_id>/edit")
@permission_required("admin.courses.manage", "admin", "instructor")
def edit_module(module_id):
    module = Module.query.get_or_404(module_id)
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Module title is required.", "error")
    else:
        module.title = title
        module.position = _safe_int(request.form.get("position"), module.position, 0, 10000)
        audit("admin.module_updated"); db.session.commit(); flash("Module updated.", "success")
    return _course_management_redirect(module.course.stage)


@admin_bp.post("/lessons/<int:lesson_id>/edit")
@permission_required("admin.courses.manage", "admin", "instructor")
def edit_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    title = request.form.get("title", "").strip()[:200]
    youtube_url = _youtube_embed_url(request.form.get("youtube_url", ""))
    body = request.form.get("body", "").strip()
    if not title:
        flash("Lesson title is required.", "error")
    elif request.form.get("youtube_url", "").strip() and not youtube_url:
        flash("Enter a valid YouTube video URL.", "error")
    elif not body and not youtube_url:
        flash("Add text content, a YouTube video, or both.", "error")
    else:
        lesson.title, lesson.body, lesson.youtube_url = title, body, youtube_url
        lesson.position = _safe_int(request.form.get("position"), lesson.position, 0, 10000)
        audit("admin.lesson_updated"); db.session.commit(); flash("Lesson content updated.", "success")
    return _course_management_redirect(lesson.module.course.stage)


@admin_bp.post("/assignments/<int:assignment_id>/edit")
@permission_required("admin.courses.manage", "admin", "instructor")
def edit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Assignment title is required.", "error")
    else:
        assignment.title = title
        assignment.instructions = request.form.get("instructions", "").strip()
        assignment.required = request.form.get("required") == "on"
        assignment.position = _safe_int(request.form.get("position"), assignment.position, 0, 10000)
        audit("admin.assignment_updated"); db.session.commit(); flash("Assignment content updated.", "success")
    stage = assignment.module.course.stage if assignment.module else assignment.lesson.module.course.stage
    return _course_management_redirect(stage)


@admin_bp.post("/quizzes/<int:quiz_id>/edit")
@permission_required("admin.quizzes.manage", "admin", "instructor")
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    title = request.form.get("title", "").strip()[:200]
    if not title:
        flash("Quiz title is required.", "error")
    else:
        quiz.title = title
        quiz.instructions = request.form.get("instructions", "").strip()
        quiz.passing_score = _safe_int(request.form.get("passing_score"), 70, 1, 100)
        audit("admin.quiz_updated"); db.session.commit(); flash("Quiz content updated.", "success")
    return _course_management_redirect(quiz.lesson.module.course.stage)


@admin_bp.post("/tracks/<int:track_id>/publish")
@permission_required("admin.courses.publish", "admin", "instructor")
def publish_track(track_id):
    track = Track.query.get_or_404(track_id)
    track.published = not track.published
    audit("admin.track_published" if track.published else "admin.track_unpublished")
    db.session.commit()
    return _course_management_redirect(request.form.get("stage", "hard_skills"))


@admin_bp.post("/courses/<int:course_id>/price")
@permission_required("admin.courses.manage", "admin", "instructor")
def update_course_price(course_id):
    course = Course.query.get_or_404(course_id)
    try:
        amount = Decimal(request.form.get("price", "0"))
    except (InvalidOperation, TypeError):
        flash("Enter a valid course price.", "error")
        return _course_management_redirect(course.stage)
    if amount < 0:
        flash("Course price cannot be negative.", "error")
        return _course_management_redirect(course.stage)
    if not course.price:
        db.session.add(CoursePrice(course_id=course.id, amount=amount, currency="NGN"))
    else:
        course.price.amount = amount
    audit("admin.course_price_updated")
    db.session.commit()
    flash("Course price updated.", "success")
    return _course_management_redirect(course.stage)


@admin_bp.route("/courses/<int:course_id>/modules", methods=["POST"])
@permission_required("admin.courses.manage", "admin", "instructor")
def add_module(course_id):
    course = Course.query.get_or_404(course_id)
    title = request.form.get("title", "").strip()[:200]
    if title:
        position = len(course.modules) + 1
        db.session.add(Module(course_id=course.id, title=title, position=position))
        audit("admin.module_created")
        db.session.commit()
    return _course_management_redirect(course.stage)


@admin_bp.route("/courses/<int:course_id>/publish", methods=["POST"])
@permission_required("admin.courses.publish", "admin", "instructor")
def publish_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.published = not course.published
    audit("admin.course_published" if course.published else "admin.course_unpublished")
    db.session.commit()
    flash("Course publication status updated.", "success")
    return _course_management_redirect(course.stage)


@admin_bp.route("/modules/<int:module_id>/lessons", methods=["POST"])
@permission_required("admin.courses.manage", "admin", "instructor")
def add_lesson(module_id):
    module = Module.query.get_or_404(module_id)
    title = request.form.get("title", "").strip()[:200]
    body = request.form.get("body", "").strip()
    youtube_url = _youtube_embed_url(request.form.get("youtube_url", ""))
    if not title:
        flash("Lesson title is required.", "error")
    elif request.form.get("youtube_url", "").strip() and not youtube_url:
        flash("Enter a valid YouTube video URL.", "error")
    elif not body and not youtube_url:
        flash("Add text content, a YouTube video, or both.", "error")
    else:
        position = len(module.lessons) + 1
        lesson = Lesson(module_id=module.id, title=title, body=body, youtube_url=youtube_url, position=position)
        db.session.add(lesson)
        audit("admin.lesson_created")
        db.session.commit()
    return _course_management_redirect(module.course.stage)


@admin_bp.route("/lessons/<int:lesson_id>/quiz", methods=["POST"])
@permission_required("admin.quizzes.manage", "admin", "instructor")
def create_quiz(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    title = request.form.get("title", "").strip()[:200]
    if title:
        quiz = Quiz(lesson_id=lesson.id, title=title, instructions=request.form.get("instructions", "").strip(), passing_score=_safe_int(request.form.get("passing_score"), 70, 1, 100))
        db.session.add(quiz)
        audit("admin.quiz_created")
        db.session.commit()
        flash("Quiz draft created.", "success")
    return _course_management_redirect(lesson.module.course.stage)


@admin_bp.post("/modules/<int:module_id>/assignment")
@permission_required("admin.courses.manage", "admin", "instructor")
def create_module_assignment(module_id):
    module = Module.query.get_or_404(module_id)
    title = request.form.get("title", "").strip()[:200]
    if title:
        position = len(module.assignments) + 1
        db.session.add(Assignment(module_id=module.id, title=title, instructions=request.form.get("instructions", "").strip(), required=True, published=False, position=position))
        audit("admin.assignment_created")
        db.session.commit()
        flash("Module assignment created as a draft.", "success")
    return _course_management_redirect(module.course.stage)


@admin_bp.post("/lessons/<int:lesson_id>/assignment")
@permission_required("admin.courses.manage", "admin", "instructor")
def create_lesson_assignment(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    title = request.form.get("title", "").strip()[:200]
    if title:
        position = len(lesson.assignments) + 1
        db.session.add(Assignment(lesson_id=lesson.id, title=title, instructions=request.form.get("instructions", "").strip(), required=True, published=False, position=position))
        audit("admin.assignment_created")
        db.session.commit()
        flash("Lesson assignment created as a draft.", "success")
    return _course_management_redirect(lesson.module.course.stage)


@admin_bp.post("/modules/<int:module_id>/quiz")
@permission_required("admin.quizzes.manage", "admin", "instructor")
def create_module_quiz(module_id):
    module = Module.query.get_or_404(module_id)
    first_lesson = module.lessons[0] if module.lessons else None
    title = request.form.get("title", "").strip()[:200]
    if not first_lesson:
        flash("Add at least one lesson before creating a module quiz.", "error")
    elif title:
        quiz = Quiz(lesson_id=first_lesson.id, title=title, instructions=request.form.get("instructions", "").strip(), passing_score=_safe_int(request.form.get("passing_score"), 70, 1, 100), published=False)
        db.session.add(quiz)
        db.session.flush()
        db.session.add(ModuleQuiz(module_id=module.id, quiz_id=quiz.id))
        audit("admin.module_quiz_created")
        db.session.commit()
        flash("Module quiz created as a draft.", "success")
    return _course_management_redirect(module.course.stage)


@admin_bp.post("/assignments/<int:assignment_id>/publish")
@permission_required("admin.courses.publish", "admin", "instructor")
def publish_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    assignment.published = not assignment.published
    audit("admin.assignment_published" if assignment.published else "admin.assignment_unpublished")
    db.session.commit()
    return _course_management_redirect((assignment.module.course.stage if assignment.module else assignment.lesson.module.course.stage))


@admin_bp.route("/quizzes/<int:quiz_id>/questions", methods=["POST"])
@permission_required("admin.quizzes.manage", "admin", "instructor")
def add_quiz_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    options = [x.strip() for x in request.form.get("options", "").split("|") if x.strip()]
    correct = request.form.get("correct_option", "").strip()
    prompt = request.form.get("prompt", "").strip()
    if prompt and len(options) >= 2 and correct in options:
        db.session.add(QuizQuestion(quiz_id=quiz.id, prompt=prompt, options_json=json.dumps(options), correct_option=correct, explanation=request.form.get("explanation", "").strip(), position=len(quiz.questions) + 1))
        audit("admin.quiz_question_created")
        db.session.commit()
    else:
        flash("Add a question, at least two options, and choose a matching correct option.", "error")
    return _course_management_redirect(quiz.lesson.module.course.stage)


@admin_bp.route("/quizzes/<int:quiz_id>/publish", methods=["POST"])
@permission_required("admin.quizzes.publish", "admin", "instructor")
def publish_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    quiz.published = not quiz.published
    audit("admin.quiz_published" if quiz.published else "admin.quiz_unpublished")
    db.session.commit()
    return _course_management_redirect(quiz.lesson.module.course.stage)




@admin_bp.post("/tracks/<int:track_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_track(track_id):
    track = Track.query.get_or_404(track_id)
    stage = request.form.get("stage", "hard_skills")
    track.courses = list(track.courses)  # preserve courses; remove only the track associations
    db.session.delete(track)
    audit("admin.track_deleted")
    db.session.commit()
    flash("Track deleted. Its courses were retained.", "success")
    return _course_management_redirect(stage)


@admin_bp.post("/courses/<int:course_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    stage = course.stage
    db.session.delete(course)
    try:
        audit("admin.course_deleted")
        db.session.commit()
        flash("Course and its learning content deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This course could not be deleted because related records still depend on it. Unenroll or archive those records first.", "error")
    return _course_management_redirect(stage)


@admin_bp.post("/modules/<int:module_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_module(module_id):
    module = Module.query.get_or_404(module_id)
    stage = module.course.stage
    db.session.delete(module)
    try:
        audit("admin.module_deleted")
        db.session.commit()
        flash("Module deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This module could not be deleted because related records still depend on it.", "error")
    return _course_management_redirect(stage)


@admin_bp.post("/lessons/<int:lesson_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    stage = lesson.module.course.stage
    db.session.delete(lesson)
    try:
        audit("admin.lesson_deleted")
        db.session.commit()
        flash("Lesson deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This lesson could not be deleted because related records still depend on it.", "error")
    return _course_management_redirect(stage)


@admin_bp.post("/assignments/<int:assignment_id>/delete")
@permission_required("admin.courses.manage", "admin")
def delete_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    stage = assignment.module.course.stage if assignment.module else assignment.lesson.module.course.stage
    db.session.delete(assignment)
    try:
        audit("admin.assignment_deleted")
        db.session.commit()
        flash("Assignment deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This assignment could not be deleted because related records still depend on it.", "error")
    return _course_management_redirect(stage)


@admin_bp.post("/quizzes/<int:quiz_id>/delete")
@permission_required("admin.quizzes.manage", "admin")
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    stage = quiz.lesson.module.course.stage
    db.session.delete(quiz)
    try:
        audit("admin.quiz_deleted")
        db.session.commit()
        flash("Quiz and its questions deleted.", "success")
    except Exception:
        db.session.rollback()
        flash("This quiz could not be deleted because related records still depend on it.", "error")
    return _course_management_redirect(stage)


@admin_bp.route("/settings", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin")
def settings():
    from app.common.settings import DEFAULTS, set_setting
    keys = [
        ("site_name", "Site name"), ("site_tagline", "Site tagline"),
        ("maintenance_mode", "Maintenance mode"), ("registration_enabled", "Registration enabled"),
        ("email_verification_required", "Email verification required"),
        ("seo_title", "Default SEO title"), ("seo_description", "Default SEO description"),
        ("seo_keywords", "Default SEO keywords"), ("seo_robots", "Robots directive"),
        ("canonical_base_url", "Canonical base URL"),
        ("deadline_penalty_amount", "Deadline penalty amount (NGN)"),
        ("deadline_penalty_extension_days", "Penalty extension days (0 = original course duration)"),
    ]
    if request.method == "POST":
        for key, label in keys:
            value = request.form.get(key, "").strip()
            if key in {"maintenance_mode", "registration_enabled", "email_verification_required"}:
                value = "1" if request.form.get(key) == "1" else "0"
            if key == "deadline_penalty_amount":
                try:
                    amount = Decimal(value)
                    if amount <= 0:
                        raise InvalidOperation
                    value = str(amount.quantize(Decimal("0.01")))
                except (InvalidOperation, ValueError):
                    flash("Penalty amount must be greater than zero.", "error")
                    return redirect(url_for("admin.settings"))
            if key == "deadline_penalty_extension_days":
                try:
                    value = str(max(0, min(3650, int(value or 0))))
                except ValueError:
                    flash("Penalty extension must be a whole number of days.", "error")
                    return redirect(url_for("admin.settings"))
            set_setting(key, value, label)
        audit("admin.settings_updated")
        db.session.commit()
        flash("System settings updated.", "success")
        return redirect(url_for("admin.settings"))
    values = {key: get_setting(key, DEFAULTS.get(key, "")) for key, _ in keys}
    return render_template("admin/settings.html", settings=values)


@admin_bp.route("/email-management", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin")
def email_management():
    """Edit the subjects and bodies used by transactional system emails."""
    from app.auth.routes import EMAIL_TEMPLATE_DEFAULTS
    from app.common.settings import set_setting
    fields = {
        "verification": "Email verification",
        "password_reset": "Password reset",
        "two_factor": "Sign-in verification code",
        "welcome": "First-login learner welcome",
    }
    if request.method == "POST":
        for key, label in fields.items():
            subject = request.form.get(f"email_{key}_subject", "").strip()
            body = request.form.get(f"email_{key}_body", "").strip()
            if not subject or len(subject) > 200 or not body or len(body) > 12000:
                flash(f"{label}: subject and message are required; subject must be 200 characters or fewer and message 12,000 or fewer.", "error")
                return redirect(url_for("admin.email_management"))
            set_setting(f"email_{key}_subject", subject, f"{label} email subject")
            set_setting(f"email_{key}_body", body, f"{label} email body")
        audit("admin.email_templates_updated")
        db.session.commit()
        flash("Email templates updated.", "success")
        return redirect(url_for("admin.email_management"))

    from app.common.settings import get_setting
    templates = {}
    for key, label in fields.items():
        default_subject, default_body = EMAIL_TEMPLATE_DEFAULTS[key]
        templates[key] = {
            "label": label,
            "subject": get_setting(f"email_{key}_subject", default_subject),
            "body": get_setting(f"email_{key}_body", default_body),
        }
    return render_template("admin/email_management.html", templates=templates)


@admin_bp.route("/referrals")
@permission_required("admin.dashboard.view", "admin")
def referrals():
    rows = Referral.query.order_by(Referral.created_at.desc()).limit(200).all()
    referral_ids = [referral.id for referral in rows]
    events = ReferralEvent.query.filter(ReferralEvent.referral_id.in_(referral_ids)).order_by(ReferralEvent.created_at.desc()).all() if referral_ids else []
    events_by_referral = {referral_id: [] for referral_id in referral_ids}
    for event in events:
        events_by_referral[event.referral_id].append(event)
    user_ids = {x.referrer_id for x in rows} | {event.referred_user_id for event in events if event.referred_user_id}
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return render_template("admin/referrals.html", referrals=rows, users=users, events_by_referral=events_by_referral, events=events)


@admin_bp.route("/referrals/create", methods=["POST"])
@permission_required("admin.dashboard.view", "admin")
def create_referral_code():
    username = request.form.get("username", "").strip().lower()
    user = User.query.filter_by(username=username).first() if username else None
    if not user:
        flash("Enter a valid username.", "error")
        return redirect(url_for("admin.referrals"))
    code = re.sub(r"[^A-Z0-9._-]", "", request.form.get("code", "").upper())[:80] or f"MAWIZ-{user.username.upper()}"[:80]
    if Referral.query.filter_by(code=code).first():
        flash("That referral code already exists.", "error")
        return redirect(url_for("admin.referrals"))
    db.session.add(Referral(referrer_id=user.id, code=code, link_token=__import__("secrets").token_urlsafe(18), status="active"))
    audit("admin.referral_code_created")
    db.session.commit()
    flash("Referral code and link created.", "success")
    return redirect(url_for("admin.referrals"))


@admin_bp.route("/coupons", methods=["GET", "POST"])
@permission_required("admin.dashboard.view", "admin")
def coupons():
    if request.method == "POST":
        code = re.sub(r"[^A-Z0-9_-]", "", request.form.get("code", "").upper())[:64]
        if not code:
            flash("Coupon code is required.", "error")
        elif Coupon.query.filter_by(code=code).first():
            flash("That coupon code already exists.", "error")
        else:
            try:
                discount_value = Decimal(request.form.get("discount_value", "0"))
                minimum_amount = Decimal(request.form.get("minimum_amount", "0"))
            except (InvalidOperation, TypeError):
                discount_value = Decimal("0"); minimum_amount = Decimal("0")
            discount_type = request.form.get("discount_type", "percent") if request.form.get("discount_type") in {"percent", "fixed"} else "percent"
            if discount_value < 0 or minimum_amount < 0 or (discount_type == "percent" and discount_value > 100):
                flash("Enter a valid discount value.", "error")
            else:
                def _dt(name):
                    raw = request.form.get(name, "").strip()
                    if not raw:
                        return None
                    try:
                        return datetime.fromisoformat(raw)
                    except ValueError:
                        return None
                coupon = Coupon(code=code, description=request.form.get("description", "").strip()[:255],
                    discount_type=discount_type, discount_value=discount_value, minimum_amount=minimum_amount,
                    max_redemptions=_safe_int(request.form.get("max_redemptions"), 0, 0, 100000000) or None,
                    per_user_limit=_safe_int(request.form.get("per_user_limit"), 1, 1, 100),
                    starts_at=_dt("starts_at"), expires_at=_dt("expires_at"), active=True)
                db.session.add(coupon); audit("admin.coupon_created"); db.session.commit(); flash("Coupon created.", "success")
    rows = Coupon.query.order_by(Coupon.created_at.desc()).all()
    redemption_counts = {c.id: CouponRedemption.query.filter_by(coupon_id=c.id, status="applied").count() for c in rows}
    return render_template("admin/coupons.html", coupons=rows, redemption_counts=redemption_counts)


@admin_bp.post("/coupons/<int:coupon_id>/toggle")
@permission_required("admin.dashboard.view", "admin")
def toggle_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id); coupon.active = not coupon.active
    audit("admin.coupon_enabled" if coupon.active else "admin.coupon_disabled"); db.session.commit()
    flash("Coupon status updated.", "success"); return redirect(url_for("admin.coupons"))


@admin_bp.route("/coupon/validate", methods=["POST"])
@permission_required("learning.catalog.view", "learner", "instructor", "mentor", "admin")
def validate_coupon():
    from datetime import datetime, timezone
    code = re.sub(r"[^A-Z0-9_-]", "", request.form.get("code", "").upper())
    amount = float(request.form.get("amount", "0") or 0)
    coupon = Coupon.query.filter_by(code=code, active=True).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not coupon or (coupon.starts_at and coupon.starts_at > now) or (coupon.expires_at and coupon.expires_at < now):
        return {"valid": False, "message": "Coupon is invalid or expired."}, 400
    if amount < float(coupon.minimum_amount or 0):
        return {"valid": False, "message": "Minimum amount not met."}, 400
    total = CouponRedemption.query.filter_by(coupon_id=coupon.id, status="applied").count()
    mine = CouponRedemption.query.filter_by(coupon_id=coupon.id, user_id=current_user().id, status="applied").count()
    if coupon.max_redemptions and total >= coupon.max_redemptions: return {"valid": False, "message": "Coupon redemption limit reached."}, 400
    if mine >= coupon.per_user_limit: return {"valid": False, "message": "You have already used this coupon."}, 400
    discount = amount * float(coupon.discount_value) / 100 if coupon.discount_type == "percent" else min(amount, float(coupon.discount_value))
    return {"valid": True, "code": coupon.code, "discount": round(discount, 2), "amount_after": round(amount-discount, 2)}
