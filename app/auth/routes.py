"""Authentication, account registration, verification, and password recovery routes."""

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import secrets
from pathlib import Path
import smtplib
from email.message import EmailMessage
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from email_validator import validate_email, EmailNotValidError
from app.extensions import db, limiter
from app.models import User, Profile, EmailAuthChallenge, Enrollment, Referral, ReferralEvent
from app.common.security import audit, current_user, sanitize_next_url

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
CAREER_PATHS = {
    "entrepreneurship": "Entrepreneurship",
    "job": "Job & Freelance",
}


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="mawiz-auth")


def _password_stamp(user):
    """Return a stable UTC timestamp whether the DB returns naive or aware datetimes."""
    value = user.password_changed_at
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _token(user, purpose):
    # Verification links are tied to the current email and do not become invalid
    # when the user changes their password. Password-reset links do.
    payload = {"uid": user.id, "purpose": purpose, "email": user.email}
    if purpose == "password_reset":
        payload["stamp"] = _password_stamp(user)
    return _serializer().dumps(payload)


def _load_token(token, purpose, max_age):
    try:
        data = _serializer().loads(token, max_age=max_age)
        if data.get("purpose") != purpose:
            return None
        user = db.session.get(User, int(data["uid"]))
        if not user:
            return None
        # Only password-reset links are invalidated by password changes. Email
        # verification links are checked against the account's current email.
        if purpose == "password_reset" and data.get("stamp") != _password_stamp(user):
            return None
        token_email = data.get("email")
        if purpose == "email_verify" and token_email and token_email.lower() != user.email.lower():
            return None
        return user
    except (BadSignature, SignatureExpired, ValueError, KeyError, TypeError):
        return None


EMAIL_TEMPLATE_DEFAULTS = {
    "verification": ("Verify your Mawiz Academy account", "Welcome to {site_name}! Verify your email address by opening this link:\n\n{link}\n\nIf you did not create this account, you can ignore this email."),
    "password_reset": ("Reset your Mawiz Academy password", "A password reset was requested for your {site_name} account. Use this link to choose a new password:\n\n{link}\n\nIf you did not request this, you can ignore this email."),
    "two_factor": ("Your Mawiz Academy sign-in code", "Your {site_name} verification code is: {code}\n\nIf you did not try to sign in, you can ignore this email."),
    "welcome": ("Welcome to {site_name}, {first_name}!", "Hello {first_name},\n\nWelcome to {site_name}! Your learner account is ready. Sign in to continue your learning journey, explore your courses, build practical skills, and work through simulations and career-path activities.\n\nOpen your learner dashboard: {dashboard_link}\n\nWe are glad to have you with us.\n\nThe {site_name} Team"),
}


def _email_content(kind, **values):
    """Load an admin-editable email subject/body and safely replace known placeholders."""
    from app.common.settings import get_setting
    default_subject, default_body = EMAIL_TEMPLATE_DEFAULTS[kind]
    subject = get_setting(f"email_{kind}_subject", default_subject) or default_subject
    body = get_setting(f"email_{kind}_body", default_body) or default_body
    replacements = {"site_name": get_setting("site_name", "Mawiz Academy"), **values}
    for key, value in replacements.items():
        subject = subject.replace("{" + key + "}", str(value))
        body = body.replace("{" + key + "}", str(value))
    return subject, body


def _send_mail(subject, recipient, body):
    backend = current_app.config["MAIL_BACKEND"].lower()
    if backend == "smtp":
        host = current_app.config["SMTP_HOST"]
        if not host:
            raise RuntimeError("MAIL_BACKEND=smtp requires SMTP_HOST")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = current_app.config["MAIL_FROM"]
        message["To"] = recipient
        message.set_content(body)
        with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=15) as smtp:
            if current_app.config["SMTP_USE_TLS"]:
                smtp.starttls()
            if current_app.config["SMTP_USERNAME"]:
                smtp.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
            smtp.send_message(message)
        return
    path = Path(current_app.config["MAIL_SINK_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} | {subject} | {recipient} | {body}\n")


def _password_ok(password):
    return len(password) >= 12 and any(c.isupper() for c in password) and any(c.isdigit() for c in password)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    """Create a learner account and record referral registration attribution.

    Notes
    -----
    A referral code is held in the session after a referral-link visit and may
    also be submitted with the form. The code is resolved only after the new user
    has an ID. The resulting ``ReferralEvent`` is the source of truth for referral
    reporting; the reusable referral code remains active for later registrations.
    """
    if current_user():
        return redirect(url_for("learner.dashboard"))
    from app.common.settings import get_bool
    if not get_bool("registration_enabled"):
        return render_template("main/maintenance.html", registration_closed=True), 403
    referral_code = request.args.get("ref", "").strip().upper()[:80] or session.get("referral_code", "")
    coupon_code = request.args.get("coupon", "").strip().upper()[:64] or session.get("coupon_code", "")
    if referral_code:
        session["referral_code"] = referral_code
    if coupon_code:
        session["coupon_code"] = coupon_code
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        try:
            validate_email(email)
        except EmailNotValidError:
            flash("Enter a valid email address.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        if not first or not last or len(first) > 100 or len(last) > 100:
            flash("Enter your first and last name.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        if not username or len(username) < 3 or len(username) > 80 or not all(c.isalnum() or c in "._-" for c in username):
            flash("Choose a username using letters, numbers, dots, hyphens or underscores.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        if not _password_ok(password):
            flash("Password must be at least 12 characters and include an uppercase letter and number.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        if User.query.filter_by(email=email).first():
            flash("An account already exists. Try signing in instead.", "error")
            return render_template("auth/register.html", referral_code=referral_code, coupon_code=coupon_code)
        from app.common.settings import get_bool
        verification_required = get_bool("email_verification_required", current_app.config["REQUIRE_EMAIL_VERIFICATION"])
        user = User(email=email, username=username, signup_coupon_code=coupon_code or None, role="learner", email_verified=not verification_required)
        user.set_password(password)
        user.profile = Profile(first_name=first, last_name=last)
        db.session.add(user)
        db.session.flush()
        own_code = f"MAWIZ-{username.upper()}"[:80]
        while Referral.query.filter_by(code=own_code).first():
            own_code = f"MAWIZ-{username.upper()}-{secrets.token_hex(2).upper()}"[:80]
        db.session.add(Referral(referrer_id=user.id, code=own_code, link_token=secrets.token_urlsafe(18), status="active"))
        referral_code = request.form.get("referral_code", "").strip().upper()[:80] or session.get("referral_code", "")
        coupon_code = request.form.get("coupon_code", "").strip().upper()[:64] or session.get("coupon_code", "")
        if referral_code:
            referral = Referral.query.filter_by(code=referral_code, status="active").first()
            # Keep shared codes active so they can attribute more than one signup.
            if referral and referral.referrer_id != user.id:
                db.session.add(ReferralEvent(
                    referral_id=referral.id,
                    referred_user_id=user.id,
                    event_type="registration",
                ))
                audit("referral.registration_completed")
        verify_link = url_for("auth.verify_email", token=_token(user, "email_verify"), _external=True)
        if verification_required:
            subject, body = _email_content("verification", link=verify_link, email=user.email)
            _send_mail(subject, user.email, body)
        audit("account.registered")
        session.pop("referral_code", None)
        db.session.commit()
        flash("Account created. You can sign in now." if not verification_required else "Account created. Check your email to verify the account before signing in.", "success")
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/register.html",
        referral_code=referral_code,
        coupon_code=coupon_code,
    )


@auth_bp.route("/resend-verification", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def resend_verification():
    """Send a fresh email verification link for an unverified account."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        # Keep the response generic to avoid disclosing whether an account exists.
        if user and not user.email_verified and user.is_active:
            try:
                link = url_for("auth.verify_email", token=_token(user, "email_verify"), _external=True)
                subject, body = _email_content("verification", link=link, email=user.email)
                _send_mail(subject, user.email, body)
            except Exception:
                current_app.logger.exception("Could not send verification email")
        flash("If that address belongs to an unverified account, a new verification link has been sent.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/resend_verification.html")


@auth_bp.route("/verify/<token>")
def verify_email(token):
    user = _load_token(token, "email_verify", current_app.config["EMAIL_VERIFY_MAX_AGE"])
    if not user:
        flash("That verification link is invalid or expired.", "error")
        return redirect(url_for("auth.login"))
    user.email_verified = True
    audit("account.email_verified")
    db.session.commit()
    flash("Your email is verified. You can now sign in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.is_active or not user.check_password(password):
            audit("auth.login_failed")
            db.session.commit()
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html"), 401
        from app.common.settings import get_bool
        verification_required = get_bool("email_verification_required", current_app.config["REQUIRE_EMAIL_VERIFICATION"])
        if verification_required and not user.email_verified:
            flash("Please verify your email before signing in.", "error")
            return render_template("auth/login.html"), 403
        if current_app.config["REQUIRE_EMAIL_2FA"]:
            code = f"{secrets.randbelow(1000000):06d}"
            digest = hashlib.sha256((current_app.config["SECRET_KEY"] + code).encode()).hexdigest()
            challenge = EmailAuthChallenge(user_id=user.id, code_hash=digest, expires_at=datetime.now(timezone.utc) + timedelta(seconds=current_app.config["EMAIL_2FA_CODE_MAX_AGE"]))
            db.session.add(challenge)
            db.session.flush()
            session.clear()
            session["preauth_user_id"] = user.id
            session["2fa_challenge_id"] = challenge.id
            subject, body = _email_content("two_factor", code=code, email=user.email)
            _send_mail(subject, user.email, body)
            audit("auth.2fa_challenge_created")
            db.session.commit()
            return redirect(url_for("auth.verify_2fa", next=request.form.get("next") or request.args.get("next") or ""))
        return _complete_login(user, request.form.get("next") or request.args.get("next"))
    return render_template("auth/login.html", next=request.args.get("next", ""))


def _complete_login(user, next_url=None):
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    audit("auth.login")
    db.session.commit()

    # Send a learner welcome email only once, after authentication (including 2FA)
    # has fully succeeded. Email delivery failures must never block sign-in.
    if user.role == "learner" and user.welcome_email_eligible and user.welcome_email_sent_at is None:
        try:
            first_name = (user.profile.first_name if user.profile else "") or user.username or "Learner"
            dashboard_link = url_for("learner.dashboard", _external=True)
            subject, body = _email_content(
                "welcome", first_name=first_name, dashboard_link=dashboard_link, email=user.email
            )
            _send_mail(subject, user.email, body)
            user.welcome_email_sent_at = datetime.now(timezone.utc)
            user.welcome_email_eligible = False
            db.session.commit()
            audit("auth.welcome_email_sent")
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not send first-login welcome email for user id %s", user.id)
            # Leave welcome_email_sent_at unset so a later successful login retries.
            user = db.session.get(User, user.id) or user

    safe_next = sanitize_next_url(next_url)
    if user.role == "admin":
        return redirect(safe_next or url_for("admin.dashboard"))
    if safe_next:
        return redirect(safe_next)
    if user.role == "learner" and not Enrollment.query.filter_by(user_id=user.id).first():
        return redirect(url_for("learning.courses", first_login="1"))
    return redirect(url_for("learner.dashboard"))


@auth_bp.route("/verify-2fa", methods=["GET", "POST"])
@limiter.limit("10 per 10 minutes", methods=["POST"])
def verify_2fa():
    uid = session.get("preauth_user_id")
    challenge_id = session.get("2fa_challenge_id")
    user = db.session.get(User, uid) if uid else None
    challenge = db.session.get(EmailAuthChallenge, challenge_id) if challenge_id else None
    if not user or not challenge or challenge.user_id != user.id or challenge.used or challenge.expires_at.replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None):
        session.clear()
        flash("Your verification code is invalid or expired. Please sign in again.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        challenge.attempts += 1
        digest = hashlib.sha256((current_app.config["SECRET_KEY"] + code).encode()).hexdigest()
        if challenge.attempts > current_app.config["EMAIL_2FA_MAX_ATTEMPTS"] or not hmac.compare_digest(digest, challenge.code_hash):
            audit("auth.2fa_failed")
            if challenge.attempts >= current_app.config["EMAIL_2FA_MAX_ATTEMPTS"]:
                challenge.used = True
            db.session.commit()
            flash("Invalid verification code.", "error")
            return render_template("auth/verify_2fa.html", next=request.args.get("next", "")), 401
        challenge.used = True
        next_url = request.form.get("next") or request.args.get("next")
        db.session.commit()
        return _complete_login(user, next_url)
    return render_template("auth/verify_2fa.html", next=request.args.get("next", ""))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def change_password():
    user = current_user()
    if not user:
        return redirect(url_for("auth.login", next=url_for("auth.change_password")))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not user.check_password(current):
            flash("Your current password is incorrect.", "error")
            return render_template("auth/change_password.html")
        if not _password_ok(password):
            flash("Password must be at least 12 characters and include an uppercase letter and number.", "error")
            return render_template("auth/change_password.html")
        if password != confirmation:
            flash("The new passwords do not match.", "error")
            return render_template("auth/change_password.html")
        if user.check_password(password):
            flash("Choose a new password different from your current password.", "error")
            return render_template("auth/change_password.html")
        user.set_password(password)
        audit("auth.password_changed")
        db.session.commit()
        flash("Your password has been updated successfully.", "success")
        return redirect(url_for("learner.dashboard") if user.role != "admin" else url_for("admin.dashboard"))
    return render_template("auth/change_password.html")

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per 10 minutes", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            link = url_for("auth.reset_password", token=_token(user, "password_reset"), _external=True)
            subject, body = _email_content("password_reset", link=link, email=user.email)
            _send_mail(subject, user.email, body)
            audit("auth.password_reset_requested")
            db.session.commit()
        flash("If an account matches that email, password-reset instructions have been sent.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = _load_token(token, "password_reset", current_app.config["PASSWORD_RESET_MAX_AGE"])
    if not user or not user.is_active:
        flash("That password-reset link is invalid or expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if not _password_ok(password):
            flash("Password must be at least 12 characters and include an uppercase letter and number.", "error")
            return render_template("auth/reset_password.html")
        user.set_password(password)
        audit("auth.password_reset_completed")
        db.session.commit()
        flash("Password updated. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html")


@auth_bp.post("/logout")
def logout():
    if current_user():
        audit("auth.logout")
        db.session.commit()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.home"))
