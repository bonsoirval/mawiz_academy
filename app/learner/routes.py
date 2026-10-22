"""Learner dashboard, profile, assessment, path, and referral routes."""

import json
import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app, send_file, abort
from datetime import datetime, timezone
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.common.security import current_user, permission_required, audit
from app.extensions import db
from app.models import AssessmentAttempt, AssessmentQuestion, AssessmentResponse, Course, Enrollment, LearnerSkill, PortfolioItem, Project, Simulation, Skill, User, Module, Lesson, Quiz, ProjectSubmission, SimulationAttempt, CareerPathContent

learner_bp = Blueprint("learner", __name__, url_prefix="/learner")

CAREER_GOALS = ["Backend Developer", "Frontend Developer", "Data Analyst", "Cybersecurity Analyst", "Digital Marketer", "AI Content Creator", "Automation Specialist"]
EXPERIENCE_LEVELS = ["Beginner", "Early Career", "Intermediate", "Advanced", "Professional"]


@learner_bp.route("/dashboard")
@permission_required("learner.dashboard.view", "learner", "instructor", "mentor", "admin")
def dashboard():
    user = current_user()
    if user.role == "instructor":
        courses = Course.query.order_by(Course.title).all()
        recent_enrollments = Enrollment.query.order_by(Enrollment.started_at.desc()).limit(8).all()
        learner_ids = {row.user_id for row in recent_enrollments}
        learner_map = {u.id: u for u in User.query.filter(User.id.in_(learner_ids)).all()} if learner_ids else {}
        return render_template(
            "instructor/dashboard.html", courses=courses,
            course_count=len(courses), published_courses=sum(1 for c in courses if c.published),
            module_count=Module.query.count(), lesson_count=Lesson.query.count(),
            enrollment_count=Enrollment.query.count(), learner_count=User.query.filter_by(role="learner").count(),
            draft_courses=sum(1 for c in courses if not c.published), recent_enrollments=recent_enrollments,
            learner_map=learner_map,
        )
    if user.role == "mentor":
        learners = User.query.filter_by(role="learner", is_active=True).order_by(User.created_at.desc()).limit(12).all()
        recent_submissions = ProjectSubmission.query.order_by(ProjectSubmission.submitted_at.desc()).limit(8).all()
        submission_learner_ids = {row.learner_id for row in recent_submissions}
        submission_learners = {u.id: u for u in User.query.filter(User.id.in_(submission_learner_ids)).all()} if submission_learner_ids else {}
        return render_template(
            "mentor/dashboard.html", learners=learners, learner_count=User.query.filter_by(role="learner", is_active=True).count(),
            active_enrollments=Enrollment.query.filter(Enrollment.progress < 100).count(),
            pending_submissions=ProjectSubmission.query.filter_by(status="pending").count(),
            recent_submissions=recent_submissions, submission_learners=submission_learners,
            projects=Project.query.filter_by(published=True).count(), simulations=Simulation.query.filter_by(published=True).count(),
        )
    enrollments = Enrollment.query.filter_by(user_id=user.id).all()
    from app.simulations.routes import simulations_for_learner
    learner_simulations = simulations_for_learner(user)
    return render_template("learner/dashboard.html", enrollments=enrollments, projects=Project.query.filter_by(published=True).limit(3).all(), simulations=learner_simulations[:3], portfolio_count=PortfolioItem.query.filter_by(learner_id=user.id).count())


@learner_bp.route("/learning-path", methods=["GET", "POST"])
@permission_required("profile.manage", "learner")
def choose_learning_path():
    """Show the learner's four-stage journey and allow one career-path choice at the end."""
    user = current_user()
    if not user.profile:
        flash("Your learner profile is not available. Please contact support.", "error")
        return redirect(url_for("learner.dashboard"))

    from app.learning.routes import _stage_is_unlocked
    valid_paths = {"entrepreneurship", "job"}

    if request.method == "POST":
        selected_path = request.form.get("career_path", "").strip()
        if user.profile.career_path:
            flash("Your career path has already been selected and cannot be changed here.", "warning")
            return redirect(url_for("learner.choose_learning_path"))
        if selected_path not in valid_paths:
            flash("Choose either Entrepreneurship or Job & Freelance.", "error")
            return redirect(url_for("learner.choose_learning_path"))
        if not _stage_is_unlocked(user, "career_path"):
            flash("Complete Hard Skills, Soft Skills and the required Work Simulations before choosing a career path.", "warning")
            return redirect(url_for("learner.choose_learning_path"))
        user.profile.career_path = selected_path
        db.session.commit()
        flash("Your career path has been saved. You can now open its content.", "success")
        return redirect(url_for("learner.career_path_content", path_name=selected_path))

    published_by_stage = {
        stage: Course.query.filter_by(published=True, stage=stage).order_by(Course.title).all()
        for stage in ("hard_skills", "soft_skills")
    }
    enrollments = {row.course_id: row for row in Enrollment.query.filter_by(user_id=user.id).all()}
    stage_progress = {}
    stage_complete = {}
    stage_course_links = {}
    for stage, courses in published_by_stage.items():
        progress_values = [int(enrollments[c.id].progress or 0) if c.id in enrollments else 0 for c in courses]
        stage_progress[stage] = round(sum(progress_values) / len(courses)) if courses else 0
        stage_complete[stage] = bool(courses) and all(value >= 100 for value in progress_values)
        in_progress = next((c for c in courses if c.id in enrollments and enrollments[c.id].progress < 100), None)
        stage_course_links[stage] = url_for("learning.course_detail", slug=in_progress.slug) if in_progress else url_for("learning.courses")

    from app.simulations.routes import simulations_for_learner
    simulations = simulations_for_learner(user)
    attempted_ids = {
        attempt.simulation_id
        for attempt in SimulationAttempt.query.filter_by(learner_id=user.id).all()
    }
    simulation_count = len(simulations)
    simulation_completed_count = sum(1 for sim in simulations if sim.id in attempted_ids)
    simulation_progress = round(simulation_completed_count * 100 / simulation_count) if simulation_count else 100
    simulation_complete = simulation_completed_count == simulation_count
    hard_complete = stage_complete["hard_skills"]
    soft_complete = stage_complete["soft_skills"]
    soft_unlocked = _stage_is_unlocked(user, "soft_skills")
    simulation_unlocked = _stage_is_unlocked(user, "simulation")
    career_unlocked = _stage_is_unlocked(user, "career_path")

    return render_template(
        "learner/choose_learning_path.html",
        selected_path=user.profile.career_path or "",
        stage_progress=stage_progress,
        stage_complete=stage_complete,
        stage_course_links=stage_course_links,
        hard_complete=hard_complete,
        soft_complete=soft_complete,
        soft_unlocked=soft_unlocked,
        simulation_unlocked=simulation_unlocked,
        career_unlocked=career_unlocked,
        simulation_count=simulation_count,
        simulation_completed_count=simulation_completed_count,
        simulation_progress=simulation_progress,
        simulation_complete=simulation_complete,
        simulations=simulations,
    )


@learner_bp.route("/career-path/<path_name>")
@permission_required("profile.manage", "learner")
def career_path_content(path_name):
    """Open content for the one career path the learner selected."""
    user = current_user()
    if not user.profile or path_name not in {"entrepreneurship", "job"}:
        return redirect(url_for("learner.choose_learning_path"))
    if user.profile.career_path != path_name:
        flash("You can only open the career path you selected.", "warning")
        return redirect(url_for("learner.choose_learning_path"))
    from app.learning.routes import _stage_is_unlocked
    if not _stage_is_unlocked(user, "career_path"):
        flash("Complete the earlier Learning Path stages before opening career content.", "warning")
        return redirect(url_for("learner.choose_learning_path"))
    resources = CareerPathContent.query.filter_by(path_name=path_name, published=True).order_by(CareerPathContent.position, CareerPathContent.id).all()
    parsed_resources = []
    for resource in resources:
        cards = []
        if resource.content_type == "flashcards":
            try:
                cards = json.loads(resource.flashcards_json or "[]")
                if not isinstance(cards, list): cards = []
            except (TypeError, ValueError):
                cards = []
        video_embed = None
        if resource.content_type == "video" and resource.video_url:
            from urllib.parse import urlparse, parse_qs
            import re
            parsed = urlparse(resource.video_url.strip())
            host = parsed.netloc.lower().split(":")[0]
            video_id = ""
            if host in {"youtu.be", "www.youtu.be"}:
                video_id = parsed.path.strip("/").split("/")[0]
            elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "www.youtube-nocookie.com"}:
                if parsed.path == "/watch": video_id = parse_qs(parsed.query).get("v", [""])[0]
                elif parsed.path.startswith(("/embed/", "/shorts/")):
                    bits = parsed.path.strip("/").split("/"); video_id = bits[1] if len(bits) > 1 else ""
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                video_embed = "https://www.youtube-nocookie.com/embed/" + video_id
        parsed_resources.append({"item": resource, "cards": cards, "video_embed": video_embed})
    return render_template("learner/career_path_content.html", path_name=path_name, resources=parsed_resources)


@learner_bp.route("/profile/upload", methods=["POST"])
@permission_required("profile.manage", "learner", "instructor", "mentor", "admin")
def upload_profile_picture():
    user = current_user()
    if not user.profile:
        flash("Your profile is not available yet.", "error")
        return redirect(url_for("learner.dashboard"))
    upload = request.files.get("profile_picture")
    if not upload or not upload.filename:
        flash("Choose an image to upload.", "error")
        return redirect(request.referrer or url_for("learner.onboarding"))
    allowed = {"jpg", "jpeg", "png", "webp"}
    original = secure_filename(upload.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in allowed:
        flash("Upload a JPG, PNG, or WebP image.", "error")
        return redirect(request.referrer or url_for("learner.onboarding"))
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size <= 0 or size > 3 * 1024 * 1024:
        flash("Profile pictures must be smaller than 3 MB.", "error")
        return redirect(request.referrer or url_for("learner.onboarding"))
    signature = upload.stream.read(12)
    upload.stream.seek(0)
    valid_image = (
        (ext in {"jpg", "jpeg"} and signature.startswith(bytes.fromhex("ffd8ff"))) or
        (ext == "png" and signature.startswith(bytes.fromhex("89504e470d0a1a0a"))) or
        (ext == "webp" and signature[:4] == b"RIFF" and signature[8:12] == b"WEBP")
    )
    if not valid_image:
        flash("The selected file is not a valid JPG, PNG, or WebP image.", "error")
        return redirect(request.referrer or url_for("learner.onboarding"))
    upload_dir = Path(current_app.static_folder) / "uploads" / "profile_pictures"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"user-{user.id}-{uuid.uuid4().hex}.{ext}"
    upload.save(upload_dir / filename)
    old_picture = user.profile.profile_picture
    user.profile.profile_picture = f"uploads/profile_pictures/{filename}"
    db.session.commit()
    if old_picture and old_picture.startswith("uploads/profile_pictures/"):
        try:
            old_path = Path(current_app.static_folder) / old_picture
            if old_path.is_file():
                old_path.unlink()
        except OSError:
            current_app.logger.warning("Could not remove replaced profile picture")
    flash("Profile picture updated.", "success")
    return redirect(request.referrer or url_for("learner.onboarding"))


@learner_bp.route("/profile/download")
@permission_required("profile.manage", "learner")
def download_profile():
    user = current_user()
    if not user.profile:
        abort(404)
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from app.models import LearnerSkill, PortfolioItem
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 60
    pdf.setTitle(f"{user.profile.first_name} {user.profile.last_name} - Mawiz Learner Profile")
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, y, f"{user.profile.first_name} {user.profile.last_name}"[:90]); y -= 28
    pdf.setFont("Helvetica", 11)
    for label, value in [
        ("Username", user.username), ("Headline", user.profile.headline),
        ("Career goal", user.profile.career_goal), ("Experience level", user.profile.experience_level),
        ("Education", user.profile.education), ("Employment", user.profile.employment),
        ("Location", user.profile.location),
    ]:
        if value:
            pdf.drawString(50, y, f"{label}: {str(value)[:100]}"); y -= 18
    y -= 8
    pdf.setFont("Helvetica-Bold", 13); pdf.drawString(50, y, "Skills"); y -= 20
    pdf.setFont("Helvetica", 10)
    for row in LearnerSkill.query.filter_by(learner_id=user.id).all():
        if y < 70: pdf.showPage(); y = height - 60; pdf.setFont("Helvetica", 10)
        pdf.drawString(60, y, f"- {row.skill.name} ({row.level})"[:110]); y -= 15
    y -= 8
    pdf.setFont("Helvetica-Bold", 13); pdf.drawString(50, y, "Portfolio"); y -= 20
    pdf.setFont("Helvetica", 10)
    for item in PortfolioItem.query.filter_by(learner_id=user.id).order_by(PortfolioItem.created_at.desc()).all():
        if y < 70: pdf.showPage(); y = height - 60; pdf.setFont("Helvetica", 10)
        pdf.drawString(60, y, f"- {item.title}"[:110]); y -= 14
        for line in (item.description or "").splitlines():
            if y < 70: pdf.showPage(); y = height - 60; pdf.setFont("Helvetica", 10)
            pdf.drawString(72, y, line[:100]); y -= 13
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                     download_name=f"mawiz-profile-{user.username}.pdf")


@learner_bp.route("/onboarding", methods=["GET", "POST"])
@permission_required("profile.manage", "learner", "instructor", "mentor", "admin")
def onboarding():
    user = current_user()
    profile = user.profile
    skills = Skill.query.order_by(Skill.name).all()
    if request.method == "POST":
        profile.headline = request.form.get("headline", "").strip()[:255]
        profile.location = request.form.get("location", "").strip()[:150]
        profile.education = request.form.get("education", "").strip()[:200]
        profile.employment = request.form.get("employment", "").strip()[:200]
        profile.career_goal = request.form.get("career_goal", "").strip()[:150]
        profile.experience_level = request.form.get("experience_level", "").strip()[:50]
        selected_ids = {int(v) for v in request.form.getlist("skills") if v.isdigit()}
        for skill in skills:
            ls = LearnerSkill.query.filter_by(learner_id=user.id, skill_id=skill.id).first()
            if skill.id in selected_ids and not ls:
                db.session.add(LearnerSkill(learner_id=user.id, skill_id=skill.id, level="Not Assessed"))
            elif ls and skill.id not in selected_ids:
                db.session.delete(ls)
        profile.onboarding_completed = True
        profile.onboarding_completed_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Your profile is saved.", "success")
        if user.role == "learner":
            return redirect(url_for("learner.assessment"))
        return redirect(url_for("learner.dashboard"))
    selected = {x.skill_id for x in LearnerSkill.query.filter_by(learner_id=user.id).all()}
    return render_template("learner/onboarding.html", career_goals=CAREER_GOALS, experience_levels=EXPERIENCE_LEVELS, skills=skills, selected=selected)


@learner_bp.route("/assessment", methods=["GET", "POST"])
@permission_required("learner.assessment.take", "learner")
def assessment():
    user = current_user()
    if not user.profile or not user.profile.onboarding_completed:
        flash("Complete your learner profile first.", "error")
        return redirect(url_for("learner.onboarding"))
    questions = AssessmentQuestion.query.filter_by(active=True).order_by(AssessmentQuestion.id).all()
    if request.method == "POST":
        attempt = AssessmentAttempt(learner_id=user.id, assessment_type="initial", max_score=sum(q.points for q in questions))
        db.session.add(attempt)
        score = 0
        for q in questions:
            selected = request.form.get(f"question_{q.id}", "")
            correct = selected == q.correct_option
            score += q.points if correct else 0
            db.session.add(AssessmentResponse(attempt=attempt, question_id=q.id, selected_option=selected[:255], is_correct=correct))
        attempt.score = score
        db.session.commit()
        return redirect(url_for("learner.assessment_result", attempt_id=attempt.id))
    parsed = [(q, json.loads(q.options_json)) for q in questions]
    return render_template("learner/assessment.html", questions=parsed)


@learner_bp.route("/assessment/<int:attempt_id>/result")
@permission_required("learner.assessment.view", "learner")
def assessment_result(attempt_id):
    user = current_user()
    attempt = AssessmentAttempt.query.filter_by(id=attempt_id, learner_id=user.id).first_or_404()
    percent = round((attempt.score / attempt.max_score) * 100) if attempt.max_score else 0
    if percent < 50: level = "Beginner"
    elif percent < 75: level = "Developing"
    else: level = "Competent"
    if user.profile:
        user.profile.experience_level = user.profile.experience_level or level
    db.session.commit()
    recommended = Course.query.filter_by(published=True, career_goal=user.profile.career_goal).all() or Course.query.filter_by(published=True).limit(3).all()
    return render_template("learner/assessment_result.html", attempt=attempt, percent=percent, level=level, recommended=recommended)


@learner_bp.route("/referrals", methods=["GET", "POST"])
@permission_required("profile.manage", "learner")
def referrals():
    """Referral activity, commission earnings, and payout requests."""
    from decimal import Decimal, InvalidOperation
    from app.models import Referral, ReferralEvent, ReferralPayout, User
    from app.common.settings import get_setting, get_bool
    user = current_user()
    codes = Referral.query.filter_by(referrer_id=user.id).order_by(Referral.created_at.desc()).all()
    referral_ids = [referral.id for referral in codes]
    events = ReferralEvent.query.filter(ReferralEvent.referral_id.in_(referral_ids)).order_by(ReferralEvent.created_at.desc()).all() if referral_ids else []
    events_by_referral = {referral_id: [] for referral_id in referral_ids}
    for event in events:
        events_by_referral[event.referral_id].append(event)
    referred_ids = sorted({event.referred_user_id for event in events if event.referred_user_id})
    referred = {u.id: u for u in User.query.filter(User.id.in_(referred_ids)).all()} if referred_ids else {}
    earned = sum((Decimal(str(e.commission_amount or 0)) for e in events if e.event_type == "purchase"), Decimal("0.00"))
    payouts = ReferralPayout.query.filter_by(referrer_id=user.id).order_by(ReferralPayout.requested_at.desc()).all()
    committed = sum((Decimal(str(p.amount or 0)) for p in payouts if p.status in {"pending", "approved", "paid"}), Decimal("0.00"))
    available = max(Decimal("0.00"), earned - committed)
    minimum = Decimal(str(get_setting("referral_minimum_payout", "5000") or "5000"))
    if request.method == "POST":
        if not get_bool("referral_program_enabled", True):
            flash("The referral program is currently disabled.", "error")
            return redirect(url_for("learner.referrals"))
        bank_name = request.form.get("bank_name", "").strip()[:120]
        account_name = request.form.get("account_name", "").strip()[:160]
        account_number = ''.join(ch for ch in request.form.get("account_number", "") if ch.isdigit())[:40]
        try:
            amount = Decimal(request.form.get("amount", "0").strip()).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            amount = Decimal("0.00")
        if not bank_name or not account_name or len(account_number) < 8:
            flash("Enter a bank name, account name and valid account number.", "error")
        elif amount < minimum:
            flash(f"The minimum payout request is NGN {minimum:,.2f}.", "error")
        elif amount <= 0 or amount > available:
            flash(f"Enter an amount up to your available balance of NGN {available:,.2f}.", "error")
        else:
            db.session.add(ReferralPayout(referrer_id=user.id, amount=amount, bank_name=bank_name,
                account_name=account_name, account_number=account_number, status="pending"))
            audit("referral.payout_requested")
            db.session.commit()
            flash("Payout request submitted for administrator review.", "success")
            return redirect(url_for("learner.referrals"))
    return render_template("learner/referrals.html", referrals=codes, referred=referred,
        events_by_referral=events_by_referral, events=events, payouts=payouts, earned=earned,
        available=available, minimum_payout=minimum, referral_program_enabled=get_bool("referral_program_enabled", True))
