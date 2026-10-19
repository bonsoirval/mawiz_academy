"""Public pages, discovery, search, and referral-link entry routes."""

from flask import Blueprint, render_template, request, abort, redirect, url_for, session, current_app, Response
from app.models import User, Track, Course, Module, Project, Simulation, AuditEvent, Referral, ReferralClick, Coupon, Lesson, Quiz, Skill, LearnerSkill, PortfolioItem, Assignment, TrackRecommendationAttempt
from app.extensions import db
from app.common.settings import get_setting
from app.common.security import current_user, audit
import hashlib
import json
import secrets
from datetime import datetime, timezone

main_bp = Blueprint("main", __name__)

@main_bp.route("/learner/<username>")
def public_learner_profile(username):
    learner = User.query.filter_by(username=username, role="learner", is_active=True).first_or_404()
    if not learner.profile:
        abort(404)
    skills = LearnerSkill.query.filter_by(learner_id=learner.id).all()
    portfolio_items = PortfolioItem.query.filter_by(learner_id=learner.id).order_by(PortfolioItem.created_at.desc()).all()
    viewer = current_user()
    can_download = bool(viewer and viewer.id == learner.id and viewer.role == "learner")
    return render_template("main/public_learner_profile.html", learner=learner, skills=skills,
                           portfolio_items=portfolio_items, can_download=can_download)


@main_bp.route("/learners/<username>")
def legacy_public_learner_profile(username):
    """Redirect old plural profile links to the canonical singular URL."""
    return redirect(url_for("main.public_learner_profile", username=username), code=301)


@main_bp.route("/")
def home():
    programs = Course.query.filter_by(published=True).order_by(Course.title.asc()).limit(6).all()
    return render_template("main/home.html", programs=programs)

@main_bp.route("/about")
def about():
    return render_template("main/about.html")

@main_bp.route("/assess", methods=["GET", "POST"])
def assess():
    questions = [
        {
            "id": "goal",
            "label": "What kind of work would you most like to become good at?",
            "options": [
                ("Build websites, applications and APIs", ["backend", "frontend", "software"]),
                ("Analyze data and turn it into decisions", ["data", "analytics"]),
                ("Protect systems, users and information", ["cybersecurity", "security"]),
                ("Create campaigns, content and digital growth", ["marketing", "content"]),
                ("Use AI and automation to improve how work gets done", ["ai", "automation"]),
            ],
        },
        {
            "id": "strength",
            "label": "Which activity sounds most satisfying?",
            "options": [
                ("Solving a technical problem and making it work", ["software", "backend", "frontend"]),
                ("Finding patterns in information and explaining what they mean", ["data", "analytics"]),
                ("Finding risks before they become problems", ["cybersecurity", "security"]),
                ("Turning an idea into a message people respond to", ["marketing", "content"]),
                ("Automating a repetitive process", ["automation", "ai"]),
            ],
        },
        {
            "id": "context",
            "label": "What would you like your learning to prepare you for?",
            "options": [
                ("A developer or engineering role", ["software", "backend", "frontend"]),
                ("A data or business intelligence role", ["data", "analytics"]),
                ("A security or risk role", ["cybersecurity", "security"]),
                ("A marketing, content or growth role", ["marketing", "content"]),
                ("An AI, automation or operations role", ["ai", "automation"]),
            ],
        },
        {
            "id": "experience",
            "label": "Where are you starting from?",
            "options": [
                ("I am new and need a guided starting point", ["beginner"]),
                ("I know the basics and need practical work", ["practical"]),
                ("I have experience and want stronger workplace evidence", ["advanced", "practical"]),
            ],
        },
    ]
    if request.method == "POST":
        selected = {}
        interest_tags = []
        reasons = []
        for q in questions:
            value = request.form.get(q["id"], "")[:255]
            selected[q["id"]] = value
            for label, tags in q["options"]:
                if label == value:
                    interest_tags.extend(tags)
                    if q["id"] != "experience":
                        reasons.append(label)
                    break
        tracks = Track.query.filter_by(published=True).all()
        scores = []
        for track in tracks:
            searchable = " ".join([track.title or "", track.slug or "", track.description or ""] + [f"{c.title} {c.career_goal or ''} {c.description}" for c in track.courses]).lower()
            score = 0
            matched = []
            for tag in interest_tags:
                aliases = {
                    "software": ["software", "developer", "development", "application"],
                    "backend": ["backend", "api", "server", "node", "python"],
                    "frontend": ["frontend", "front-end", "web", "javascript", "react"],
                    "data": ["data", "analyst", "analytics", "sql", "business intelligence"],
                    "analytics": ["analytics", "analyst", "data"],
                    "cybersecurity": ["cyber", "security", "information security"],
                    "security": ["security", "cyber"],
                    "marketing": ["marketing", "growth", "digital marketing"],
                    "content": ["content", "creator", "copywriting"],
                    "ai": ["ai", "artificial intelligence", "machine learning"],
                    "automation": ["automation", "automate", "operations"],
                    "beginner": ["beginner", "foundation", "foundations", "entry"],
                    "practical": ["practical", "project", "workplace", "professional"],
                    "advanced": ["advanced", "professional", "career"],
                }.get(tag, [tag])
                if any(alias in searchable for alias in aliases):
                    score += 2 if tag not in {"beginner", "practical", "advanced"} else 1
                    matched.append(tag)
            scores.append({"track": track, "score": score, "matched": list(dict.fromkeys(matched))})
        scores.sort(key=lambda x: (-x["score"], x["track"].title.lower()))
        if scores and scores[0]["score"] == 0:
            scores[0]["score"] = 1
        recommendation = scores[0] if scores else None
        alternatives = [item for item in scores[1:3] if item["score"] > 0]
        token = session.get("prospect_assessment_token") or secrets.token_urlsafe(24)
        session["prospect_assessment_token"] = token
        if recommendation:
            record = TrackRecommendationAttempt(session_hash=hashlib.sha256((current_app.config["SECRET_KEY"] + token).encode()).hexdigest(), recommended_track_id=recommendation["track"].id, scores_json=json.dumps({str(x["track"].id): x["score"] for x in scores}), answers_json=json.dumps(selected), created_at=datetime.now(timezone.utc))
            db.session.add(record)
            db.session.commit()
        session["assessment_result"] = {
            "recommendation_id": recommendation["track"].id if recommendation else None,
            "matched": recommendation["matched"] if recommendation else [],
            "reasons": reasons,
            "alternatives": [x["track"].id for x in alternatives],
        }
        return redirect(url_for("main.assess_result"))
    return render_template("main/assess.html", questions=questions)


@main_bp.route("/assess/result")
def assess_result():
    result = session.get("assessment_result")
    if not result:
        return redirect(url_for("main.assess"))
    recommendation = Track.query.filter_by(id=result.get("recommendation_id"), published=True).first() if result.get("recommendation_id") else None
    alternatives = Track.query.filter(Track.id.in_(result.get("alternatives", [])), Track.published.is_(True)).all() if result.get("alternatives") else []
    return render_template("main/assess_result.html", recommendation=recommendation, alternatives=alternatives, reasons=result.get("reasons", []))


@main_bp.route("/programs")
def programs():
    tracks = Track.query.filter_by(published=True).order_by(Track.title.asc()).all()
    programs = Course.query.filter_by(published=True).order_by(Course.title.asc()).all()
    return render_template("main/programs.html", tracks=tracks, programs=programs)

@main_bp.route("/programs/<int:course_id>")
def program_detail(course_id):
    course = Course.query.filter_by(id=course_id, published=True).first_or_404()
    return render_template("main/program_detail.html", course=course)

@main_bp.route("/how-it-works")
def how_it_works():
    return render_template("main/how_it_works.html")

@main_bp.route("/pricing")
def pricing():
    return render_template("main/pricing.html")



@main_bp.route("/r/<token>")
def referral_link(token):
    """Record a referral-link visit and preserve its code through registration.

    Parameters
    ----------
    token : str
        Opaque link token or a referral code supplied in the short-link path.

    Notes
    -----
    The session value is deliberately set before redirecting to registration. It
    lets registration retain attribution even when a visitor navigates around the
    public site before completing the form.
    """
    token = token.strip()[:96]
    referral = Referral.query.filter_by(link_token=token, status="active").first()
    if not referral:
        referral = Referral.query.filter_by(code=token.upper(), status="active").first_or_404()
    referral.clicks = (referral.clicks or 0) + 1
    referral.last_clicked_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ip_hash = hashlib.sha256((current_app.config["SECRET_KEY"] + ip).encode()).hexdigest()
    db.session.add(ReferralClick(referral_id=referral.id, ip_hash=ip_hash, user_agent=request.headers.get("User-Agent", "")[:255]))
    audit("referral.link_clicked")
    db.session.commit()
    session["referral_code"] = referral.code
    return redirect(url_for("auth.register", ref=referral.code))


@main_bp.route("/c/<code>")
def coupon_link(code):
    code = code.strip().upper()[:64]
    coupon = Coupon.query.filter_by(code=code, active=True).first_or_404()
    session["coupon_code"] = coupon.code
    return redirect(url_for("auth.register", coupon=coupon.code))


@main_bp.route("/maintenance")
def maintenance():
    return render_template("main/maintenance.html"), 503


@main_bp.route("/robots.txt")
def robots():
    base = get_setting("canonical_base_url") or request.url_root.rstrip("/")
    return Response(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", mimetype="text/plain")


@main_bp.route("/sitemap.xml")
def sitemap():
    urls = [url_for("main.home", _external=True), url_for("main.about", _external=True), url_for("main.programs", _external=True), url_for("main.how_it_works", _external=True), url_for("main.pricing", _external=True)]
    urls.extend(url_for("main.program_detail", course_id=c.id, _external=True) for c in Course.query.filter_by(published=True).all())
    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{u}</loc></url>' for u in urls) + '</urlset>'
    return Response(body, mimetype="application/xml")


@main_bp.route("/search")
def search():
    user = current_user()
    if not user:
        abort(403)
    q = request.args.get("q", "").strip()[:100]
    results = {"users": [], "tracks": [], "courses": [], "modules": [], "assignments": [], "lessons": [], "quizzes": [], "projects": [], "simulations": [], "skills": [], "portfolio": [], "coupons": [], "referrals": [], "audit": []}
    if q:
        like = f"%{q}%"
        results["tracks"] = Track.query.filter((Track.title.ilike(like)) | (Track.description.ilike(like))).limit(8).all()
        results["courses"] = Course.query.filter((Course.title.ilike(like)) | (Course.description.ilike(like))).limit(8).all()
        results["modules"] = Module.query.filter(Module.title.ilike(like)).limit(8).all()
        results["lessons"] = Lesson.query.filter((Lesson.title.ilike(like)) | (Lesson.body.ilike(like))).limit(8).all()
        results["quizzes"] = Quiz.query.filter((Quiz.title.ilike(like)) | (Quiz.instructions.ilike(like))).limit(8).all()
        results["assignments"] = Assignment.query.filter((Assignment.title.ilike(like)) | (Assignment.instructions.ilike(like))).limit(8).all()
        results["projects"] = Project.query.filter((Project.title.ilike(like)) | (Project.problem.ilike(like))).limit(8).all()
        results["simulations"] = Simulation.query.filter((Simulation.title.ilike(like)) | (Simulation.scenario.ilike(like))).limit(8).all()
        results["skills"] = Skill.query.filter((Skill.name.ilike(like)) | (Skill.description.ilike(like))).limit(8).all()
        if user.role == "learner":
            results["portfolio"] = PortfolioItem.query.filter(PortfolioItem.learner_id == user.id, (PortfolioItem.title.ilike(like)) | (PortfolioItem.description.ilike(like))).limit(8).all()
        if user.role == "admin":
            results["users"] = User.query.filter((User.email.ilike(like))).limit(8).all()
            results["coupons"] = Coupon.query.filter((Coupon.code.ilike(like)) | (Coupon.description.ilike(like))).limit(8).all()
            results["referrals"] = Referral.query.filter(Referral.code.ilike(like)).limit(8).all()
            results["audit"] = AuditEvent.query.filter(AuditEvent.action.ilike(like)).order_by(AuditEvent.created_at.desc()).limit(8).all()
    return render_template("main/search.html", q=q, results=results)
