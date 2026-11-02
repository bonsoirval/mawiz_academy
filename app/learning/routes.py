"""Course delivery, progression, checkout, and payment-verification routes."""

import hashlib
import hmac
import json
import re
import uuid
import calendar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from app.common.security import current_user, permission_required, audit
from app.extensions import csrf, db
from app.common.settings import get_bool, get_setting
from app.models import (
    Course, Track, ProgramEnrollment, ProgramPayment, MGSCampaign, MGSCEvent, ShareLedgerEntry,
    Lesson, Module, Enrollment, LessonProgress, ModuleProgress,
    Quiz, QuizAttempt, QuizResponse, ModuleQuiz, Assignment, AssignmentSubmission,
    Coupon, CouponRedemption, CoursePayment, Referral, ReferralEvent, ProgramReferralEvent, User,
)
learning_bp = Blueprint("learning", __name__, url_prefix="/learning")


@learning_bp.before_request
def require_learning_path_before_courses():
    """Career-path choice is the final stage, so it must not block earlier learning."""
    return None


def _safe_log_text(value, limit=300):
    """Keep provider diagnostics useful while redacting email-like strings and line breaks."""
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
    return text[:limit]


PROGRAM_STAGE_ORDER = {"hard_skills": 1, "soft_skills": 2, "simulation": 3, "career_path": 4}

def _stage_is_unlocked(user, stage, course=None):
    """Unlock stages within the purchased program context when a course is supplied."""
    order = PROGRAM_STAGE_ORDER.get(stage, 1)
    if order <= 1:
        return True
    if stage == "career_path":
        # Career Path requires skill stages within the learner's owned programs.
        rows_scope = None
        if course is not None:
            owned_ids = {row.track_id for row in ProgramEnrollment.query.filter_by(user_id=user.id, status="active").all()}
            rows_scope = {c.id for tr in Track.query.filter(Track.id.in_(owned_ids)).all() for c in tr.courses} if owned_ids else set()
        for required_stage in ("hard_skills", "soft_skills"):
            rows = Course.query.filter_by(published=True, stage=required_stage).all()
            if rows_scope is not None:
                rows = [c for c in rows if c.id in rows_scope]
            if rows and not all(_is_course_completed(user.id, c) for c in rows):
                return False
        from app.models import SimulationAttempt
        from app.simulations.routes import simulations_for_learner
        # Only simulations attached to this learner's enrolled program count toward progression.
        sims = simulations_for_learner(user)
        return all(
            SimulationAttempt.query.filter_by(learner_id=user.id, simulation_id=x.id).first()
            for x in sims
        )
    previous = {2: "hard_skills", 3: "soft_skills"}.get(order)
    if not previous:
        return False
    rows = Course.query.filter_by(published=True, stage=previous).all()
    if course is not None:
        owned_ids = {row.track_id for row in ProgramEnrollment.query.filter_by(user_id=user.id, status="active").all()}
        relevant_track_ids = {tr.id for tr in course.tracks if tr.id in owned_ids}
        if relevant_track_ids:
            relevant_course_ids = {c.id for tr in Track.query.filter(Track.id.in_(relevant_track_ids)).all() for c in tr.courses}
            rows = [c for c in rows if c.id in relevant_course_ids]
        else:
            rows = []
    if not rows:
        return True
    return all(_is_course_completed(user.id, c) for c in rows)


def _learner_has_program_access(user_id, course):
    """Return True only when a learner owns a program containing this course.

    Courses not assigned to any program remain available to legacy enrolled learners,
    but newly published learning content should be assigned to a purchasable program.
    """
    tracks = list(getattr(course, "tracks", []) or [])
    if not tracks:
        return Enrollment.query.filter_by(user_id=user_id, course_id=course.id).first() is not None
    track_ids = [track.id for track in tracks]
    return ProgramEnrollment.query.filter(
        ProgramEnrollment.user_id == user_id,
        ProgramEnrollment.track_id.in_(track_ids),
        ProgramEnrollment.status == "active",
    ).first() is not None


def _enrollment(user_id, course_id):
    row = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
    if not row or not row.course:
        return row
    if not _learner_has_program_access(user_id, row.course):
        return None
    return row


def _mgsc_record_event(event_type, user_id=None, program_payment=None, occurred_at=None):
    """Count attributed beneficiary events and refresh eligible system-revenue shares."""
    occurred_at = occurred_at or datetime.now(timezone.utc)
    registration = ReferralEvent.query.filter_by(
        referred_user_id=user_id, event_type="registration"
    ).order_by(ReferralEvent.created_at.asc()).first() if user_id else None
    referral = registration.referral if registration else (
        Referral.query.filter_by(referred_user_id=user_id).first() if user_id else None
    )
    campaigns = MGSCampaign.query.filter(
        MGSCampaign.status == "active",
        MGSCampaign.starts_at <= occurred_at,
        MGSCampaign.ends_at >= occurred_at,
    ).all()
    for campaign in campaigns:
        # Only the campaign beneficiary's own attributed registrations and program
        # orders count toward their thresholds. System revenue itself is global.
        attributed = bool(referral and referral.referrer_id == campaign.beneficiary_user_id)
        if attributed and ((event_type == "signup" and user_id) or (event_type == "program_purchase" and program_payment)):
            key = (f"mgsc:{campaign.id}:signup:{user_id}" if event_type == "signup"
                   else f"mgsc:{campaign.id}:purchase:{program_payment.id}")
            if not MGSCEvent.query.filter_by(event_key=key).first():
                db.session.add(MGSCEvent(
                    campaign_id=campaign.id, event_type=event_type, user_id=user_id,
                    program_payment_id=program_payment.id if program_payment else None,
                    event_key=key, amount=program_payment.amount if program_payment else 0,
                    currency=program_payment.currency if program_payment else "NGN", occurred_at=occurred_at,
                ))
                db.session.flush()

        signups = MGSCEvent.query.filter_by(campaign_id=campaign.id, event_type="signup").count()
        purchases = MGSCEvent.query.filter_by(campaign_id=campaign.id, event_type="program_purchase").count()
        campaign.eligible_signup_count = signups
        campaign.eligible_purchase_count = purchases
        counts_eligible = (
            campaign.min_signups <= signups <= campaign.max_signups
            and campaign.min_program_purchases <= purchases <= campaign.max_program_purchases
        )
        if counts_eligible and campaign.eligible_at is None:
            campaign.eligible_at = occurred_at

        # Eligibility is triggered live, while the share base is total eligible
        # Mawiz system revenue from the campaign start through the current event.
        # This intentionally includes eligible revenue generated earlier in the
        # campaign, matching the configured campaign-wide revenue basis.
        if campaign.eligible_at:
            from sqlalchemy import func
            revenue_query = db.session.query(func.coalesce(func.sum(ProgramPayment.eligible_revenue_amount), 0)).filter(
                ProgramPayment.status == "success",
                ProgramPayment.paid_at >= campaign.starts_at,
                ProgramPayment.paid_at <= occurred_at,
            )
            revenue = Decimal(str(revenue_query.scalar() or 0))
            share = (revenue * Decimal(str(campaign.share_percent or 0)) / Decimal("100")).quantize(Decimal("0.01"))
            campaign.estimated_share_amount = share
            ledger = ShareLedgerEntry.query.filter_by(campaign_id=campaign.id, entry_type="estimate").first()
            if not ledger:
                ledger = ShareLedgerEntry(campaign_id=campaign.id, entry_type="estimate", basis_amount=revenue,
                    share_percent=campaign.share_percent, amount=share, currency="NGN", status="estimated",
                    description="Live MGSC share of total eligible system revenue during campaign")
                db.session.add(ledger)
            else:
                ledger.basis_amount = revenue
                ledger.share_percent = campaign.share_percent
                ledger.amount = share


def _add_months(value, months):
    target_month = value.month - 1 + months
    year = value.year + target_month // 12
    month = target_month % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def _course_deadline(course, started_at):
    value = max(1, course.duration_value or 1)
    unit = course.duration_unit or "weeks"
    if unit == "days":
        return started_at + timedelta(days=value)
    if unit == "weeks":
        return started_at + timedelta(weeks=value)
    if unit == "months":
        return _add_months(started_at, value)
    if unit == "years":
        return _add_months(started_at, value * 12)
    return None


def _active_enrollment(user_id, excluding_course_id=None):
    query = Enrollment.query.filter(Enrollment.user_id == user_id)
    if excluding_course_id is not None:
        query = query.filter(Enrollment.course_id != excluding_course_id)
    for enrollment in query.order_by(Enrollment.started_at.asc()).all():
        course = db.session.get(Course, enrollment.course_id)
        if course and not _is_course_completed(user_id, course):
            return enrollment
    return None


def _registration_date(user):
    """Use account registration as the common start of the learner's program clock."""
    registered_at = user.created_at or datetime.now(timezone.utc)
    if registered_at.tzinfo is None:
        registered_at = registered_at.replace(tzinfo=timezone.utc)
    return registered_at


def _days_remaining(deadline_at):
    if not deadline_at:
        return None
    # Compare calendar dates in UTC so the displayed countdown is stable throughout a day.
    return (deadline_at.date() - datetime.now(timezone.utc).date()).days


def _enrollment_expired(enrollment):
    """Deadline enforcement uses the stored UTC instant, not client-side display state."""
    if not enrollment or not enrollment.deadline_at or (enrollment.progress or 0) >= 100:
        return False
    deadline = enrollment.deadline_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= deadline


def _deadline_display(deadline_at):
    remaining = _days_remaining(deadline_at)
    if remaining is None:
        return None
    if remaining > 0:
        return {"days_remaining": remaining, "days_overdue": 0, "is_due_today": False}
    if remaining == 0:
        return {"days_remaining": 0, "days_overdue": 0, "is_due_today": True}
    return {"days_remaining": 0, "days_overdue": abs(remaining), "is_due_today": False}


def _create_enrollment(user_id, course):
    """Start this course's deadline only when the learner actually starts it."""
    started_at = datetime.now(timezone.utc)
    return Enrollment(
        user_id=user_id,
        course_id=course.id,
        progress=0,
        started_at=started_at,
        deadline_at=_course_deadline(course, started_at),
    )


def _effective_enrollment_deadline(enrollment, repair=False):
    """Return a course deadline anchored to its start, preserving verified extensions.

    Legacy deadlines were anchored to account registration. Re-anchor those to the
    enrollment start. A successful deadline-penalty payment may intentionally set a
    different deadline, so retain that deadline instead of overwriting it.
    """
    if not enrollment or not enrollment.course:
        return None
    started_at = enrollment.started_at or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    expected = _course_deadline(enrollment.course, started_at)
    stored = enrollment.deadline_at
    has_verified_extension = CoursePayment.query.filter_by(
        user_id=enrollment.user_id,
        course_id=enrollment.course_id,
        purpose="deadline_penalty",
        status="success",
    ).first() is not None
    if stored and has_verified_extension:
        return stored
    stored_utc = stored.replace(tzinfo=timezone.utc) if stored and stored.tzinfo is None else stored
    expected_utc = expected.replace(tzinfo=timezone.utc) if expected.tzinfo is None else expected
    if not stored or stored_utc != expected_utc:
        if repair:
            enrollment.deadline_at = expected
        return expected
    return stored


def _passed_quiz(user_id, quiz_id):
    attempt = QuizAttempt.query.filter_by(learner_id=user_id, quiz_id=quiz_id, passed=True).order_by(QuizAttempt.completed_at.desc()).first()
    return bool(attempt)


def _assignment_done(user_id, assignment):
    if not assignment.required or not assignment.published:
        return True
    return bool(AssignmentSubmission.query.filter_by(learner_id=user_id, assignment_id=assignment.id).first())


def _lesson_complete(user_id, lesson):
    progress = LessonProgress.query.filter_by(learner_id=user_id, lesson_id=lesson.id, completed=True).first()
    if not progress:
        return False
    for quiz in Quiz.query.filter_by(lesson_id=lesson.id, published=True).all():
        if not _passed_quiz(user_id, quiz.id):
            return False
    for assignment in Assignment.query.filter_by(lesson_id=lesson.id, published=True, required=True).all():
        if not _assignment_done(user_id, assignment):
            return False
    return True


def _module_complete(user_id, module):
    if not module.lessons:
        lesson_ok = True
    else:
        lesson_ok = all(_lesson_complete(user_id, lesson) for lesson in module.lessons)
    if not lesson_ok:
        return False
    for link in ModuleQuiz.query.filter_by(module_id=module.id).all():
        if link.quiz.published and not _passed_quiz(user_id, link.quiz_id):
            return False
    for assignment in Assignment.query.filter_by(module_id=module.id, published=True, required=True).all():
        if not _assignment_done(user_id, assignment):
            return False
    return True


def _refresh_module_progress(user_id, module):
    complete = _module_complete(user_id, module)
    progress = ModuleProgress.query.filter_by(learner_id=user_id, module_id=module.id).first()
    if not progress:
        progress = ModuleProgress(learner_id=user_id, module_id=module.id)
        db.session.add(progress)
    if complete and not progress.completed:
        progress.completed = True
        progress.completed_at = datetime.now(timezone.utc)
    elif not complete:
        progress.completed = False
        progress.completed_at = None
    return progress


def _course_materials_complete(user_id, course):
    modules = list(course.modules)
    # An empty course cannot be considered complete merely because it has no lessons.
    return bool(modules) and all(_module_complete(user_id, module) for module in modules)


def _is_course_completed(user_id, course):
    enrollment = _enrollment(user_id, course.id)
    if not enrollment:
        return False
    return _course_materials_complete(user_id, course)


def _refresh_progress(user_id, course):
    modules = list(course.modules)
    if not modules:
        return 0
    done = sum(_module_complete(user_id, module) for module in modules)
    return round((done / len(modules)) * 100)


def _module_accessible(user_id, module):
    modules = list(module.course.modules)
    index = modules.index(module)
    if index == 0:
        return True
    return _module_complete(user_id, modules[index - 1])


def _lesson_accessible(user_id, lesson):
    module = lesson.module
    if not _module_accessible(user_id, module):
        return False
    lessons = list(module.lessons)
    index = lessons.index(lesson)
    if index == 0:
        return True
    return _lesson_complete(user_id, lessons[index - 1])


def _coupon_offer(user, code, amount, course_id):
    code = "".join(ch for ch in (code or "").upper() if ch.isalnum() or ch in "_-")[:64]
    if not code:
        return None, Decimal("0"), None
    coupon = Coupon.query.filter_by(code=code, active=True).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not coupon or (coupon.starts_at and coupon.starts_at > now) or (coupon.expires_at and coupon.expires_at < now):
        raise ValueError("Coupon is invalid or expired.")
    if amount < Decimal(coupon.minimum_amount or 0):
        raise ValueError("Minimum amount for this coupon has not been met.")
    total = CouponRedemption.query.filter_by(coupon_id=coupon.id, status="applied").count()
    mine = CouponRedemption.query.filter_by(coupon_id=coupon.id, user_id=user.id, status="applied").count()
    if coupon.max_redemptions and total >= coupon.max_redemptions:
        raise ValueError("Coupon redemption limit reached.")
    if mine >= coupon.per_user_limit:
        raise ValueError("You have already used this coupon.")
    discount = amount * Decimal(coupon.discount_value or 0) / Decimal("100") if coupon.discount_type == "percent" else min(amount, Decimal(coupon.discount_value or 0))
    return coupon, discount, code


def _paystack_request(path, method="GET", payload=None):
    """Call Paystack and log safe diagnostics for both successful and failed requests."""
    secret_key = (current_app.config.get("PAYSTACK_SECRET_KEY") or "").strip()
    request_id = getattr(g, "request_id", "-")
    if not secret_key:
        current_app.logger.error("request_id=%s paystack_config_missing path=%s", request_id, path)
        raise RuntimeError("Paystack payment is not configured. Set PAYSTACK_SECRET_KEY and restart the application.")
    base_url = (current_app.config.get("PAYSTACK_API_BASE_URL") or "https://api.paystack.co").strip().rstrip("/")
    if not base_url.startswith("https://"):
        current_app.logger.error("request_id=%s paystack_invalid_api_url", request_id)
        raise RuntimeError("Paystack API URL must use HTTPS.")
    endpoint = f"{base_url}/{path.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    # A stable application User-Agent and explicit connection behavior match
    # the known-working payment reference. Never log Authorization or payloads.
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
        "User-Agent": "MawizAcademy-Payments/1.0",
        "Connection": "close",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    # Never log the Authorization header, request body, email, or full key.
    current_app.logger.info(
        "request_id=%s paystack_request method=%s endpoint=%s key_mode=%s payload_fields=%s",
        request_id, method.upper(), endpoint,
        "test" if secret_key.startswith("sk_test_") else "live" if secret_key.startswith("sk_live_") else "unknown",
        ",".join(sorted(payload.keys())) if isinstance(payload, dict) else "none",
    )
    try:
        with urlopen(Request(endpoint, data=body, headers=headers, method=method.upper()),
                     timeout=current_app.config.get("PAYSTACK_TIMEOUT_SECONDS", 15)) as response:
            status_code = getattr(response, "status", 200)
            raw_response = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get_content_type() if exc.headers else "unknown"
        try:
            error_data = json.loads(raw_error or "{}")
            if not isinstance(error_data, dict):
                error_data = {}
        except (ValueError, TypeError):
            error_data = {}

        provider_message = error_data.get("message")
        if not provider_message and content_type not in ("application/json", "application/problem+json"):
            # An HTML/non-JSON 403 can originate from a proxy, WAF, or network
            # security layer; do not incorrectly diagnose every 403 as a bad key.
            provider_message = (
                f"Paystack endpoint returned a non-JSON HTTP {exc.code} response "
                f"(content type: {content_type}). Check outbound proxy/WAF rules, "
                "network filtering, and the Paystack API endpoint configuration."
            )

        safe_message = _safe_log_text(provider_message)
        current_app.logger.warning(
            "request_id=%s paystack_response endpoint=%s status=%s content_type=%s provider_message=%r",
            request_id, endpoint, exc.code, content_type,
            safe_message or "(no message returned)",
        )
        if exc.code == 401 or (exc.code == 403 and content_type in ("application/json", "application/problem+json")):
            fallback = f"Paystack API authorization was rejected (HTTP {exc.code}). Confirm that the configured key is active and belongs to the intended test/live environment."
        elif exc.code == 403:
            fallback = f"Paystack endpoint returned HTTP 403 with content type {content_type}; this may be a network/proxy/security block rather than a rejected secret key."
        elif exc.code == 429:
            fallback = "Paystack rate limit reached. Wait briefly and try again."
        else:
            fallback = f"Paystack rejected the request (HTTP {exc.code}). Check the transaction details."
        raise RuntimeError(provider_message or fallback) from exc
    except (URLError, TimeoutError, OSError) as exc:
        current_app.logger.warning(
            "request_id=%s paystack_transport_error endpoint=%s error_type=%s reason=%s",
            request_id, endpoint, type(exc).__name__, str(getattr(exc, "reason", "") or "")[:200],
        )
        raise RuntimeError("Could not connect to Paystack. Check the server's internet/DNS/SSL connection and try again.") from exc

    try:
        data = json.loads(raw_response)
    except (ValueError, UnicodeDecodeError) as exc:
        current_app.logger.warning("request_id=%s paystack_response endpoint=%s status=%s invalid_json=true", request_id, endpoint, status_code)
        raise RuntimeError("Paystack returned an invalid response. Please try again later.") from exc
    current_app.logger.info(
        "request_id=%s paystack_response endpoint=%s status=%s api_status=%s",
        request_id, endpoint, status_code, bool(data.get("status")) if isinstance(data, dict) else False,
    )
    if not isinstance(data, dict) or not data.get("status"):
        message = data.get("message") if isinstance(data, dict) else None
        raise RuntimeError(message or "Paystack could not complete the request.")
    return data.get("data") or {}


def _validated_paystack_checkout_url(value):
    """Accept only HTTPS Paystack-hosted checkout URLs returned by initialization."""
    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "checkout.paystack.com"
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
    ):
        raise RuntimeError("Paystack returned an invalid secure checkout URL. Please try again.")
    return parsed.geturl()


def _minor_units(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _record_referral_purchase(payment):
    """Credit a verified payment to the learner's original referral, once.

    Parameters
    ----------
    payment : CoursePayment
        A locally stored payment that was verified as successful by Paystack.

    Notes
    -----
    Paystack can deliver both a browser callback and a webhook for one charge.
    The unique ``ReferralEvent.payment_id`` constraint makes this operation
    idempotent regardless of delivery order. The legacy fallback supports users
    attributed before the event table was added.
    """
    registration = ReferralEvent.query.filter_by(
        referred_user_id=payment.user_id, event_type="registration"
    ).order_by(ReferralEvent.created_at.asc()).first()
    referral = registration.referral if registration else Referral.query.filter_by(
        referred_user_id=payment.user_id
    ).first()
    if not get_bool("referral_program_enabled", True) or not referral or referral.referrer_id == payment.user_id:
        return
    if not registration:
        registration = ReferralEvent(
            referral_id=referral.id,
            referred_user_id=payment.user_id,
            event_type="registration",
            created_at=referral.completed_at or referral.created_at,
        )
        db.session.add(registration)
    if ReferralEvent.query.filter_by(payment_id=payment.id).first():
        return
    try:
        share_percent = Decimal(referral.share_percent if referral.share_percent is not None else get_setting("normal_referral_share_percent", get_setting("referral_share_percent", "10")))
    except (InvalidOperation, TypeError, ValueError):
        share_percent = Decimal("10")
    commission = (Decimal(payment.amount) * share_percent / Decimal("100")).quantize(Decimal("0.01"))
    db.session.add(ReferralEvent(
        referral_id=referral.id,
        referred_user_id=payment.user_id,
        event_type="purchase",
        course_id=payment.course_id,
        payment_id=payment.id,
        amount=payment.amount,
        commission_amount=commission,
        currency=payment.currency,
    ))
    audit("referral.purchase_completed")


def _finalize_payment(payment):
    """Verify a Paystack transaction and grant enrollment and referral credit.

    Parameters
    ----------
    payment : CoursePayment
        Pending payment record identified by the Paystack reference.

    Returns
    -------
    bool
        ``True`` only when Paystack verifies the exact amount, currency, reference,
        and customer email expected by Mawiz.

    Notes
    -----
    Enrollment, coupon redemption, and referral purchase attribution all happen in
    the same database transaction. Repeating a verified callback is safe because
    the payment status and referral payment identifier are both idempotent guards.
    """
    result = _paystack_request(f"/transaction/verify/{payment.reference}")
    expected_minor = _minor_units(payment.amount)
    received_minor = int(result.get("amount") or 0)
    expected_email = payment.user.email.strip().lower()
    received_email = (result.get("customer") or {}).get("email", "").strip().lower()
    if (
        result.get("status") != "success"
        or result.get("reference") != payment.reference
        or received_minor != expected_minor
        or result.get("currency") != payment.currency
        or received_email != expected_email
    ):
        payment.status = result.get("status") or "verification_failed"
        db.session.commit()
        return False

    newly_paid = payment.status != "success"
    if newly_paid:
        payment.status = "success"
        payment.paystack_transaction_id = str(result.get("id") or "")
        payment.paid_at = datetime.now(timezone.utc)
    enrollment = _enrollment(payment.user_id, payment.course_id)
    if payment.purpose == "deadline_penalty":
        # Apply the extension exactly once, only after Paystack verifies payment.
        if newly_paid:
            if not enrollment:
                enrollment = _create_enrollment(payment.user_id, payment.course)
                db.session.add(enrollment)
                db.session.flush()
            extension_days = int(payment.extension_days or 0)
            extension_start = datetime.now(timezone.utc)
            if extension_days <= 0:
                enrollment.deadline_at = _course_deadline(payment.course, extension_start)
            else:
                enrollment.deadline_at = extension_start + timedelta(days=extension_days)
    else:
        if not enrollment:
            db.session.add(_create_enrollment(payment.user_id, payment.course))
            if payment.coupon_id:
                db.session.add(CouponRedemption(
                    coupon_id=payment.coupon_id,
                    user_id=payment.user_id,
                    course_id=payment.course_id,
                    amount_before=payment.amount + payment.discount_amount,
                    discount_amount=payment.discount_amount,
                    amount_after=payment.amount,
                    status="applied",
                ))
        # Free enrollment intentionally does not create a purchase event.
        if newly_paid:
            _record_referral_purchase(payment)
    db.session.commit()
    return True


@learning_bp.route("/courses")
@permission_required("learning.catalog.view", "learner", "instructor", "mentor", "admin")
def courses():
    user = current_user()
    course_rows = Course.query.filter_by(published=True).order_by(Course.title).all()
    active_enrollment = None
    enrollments_by_course = {}
    if user and user.role == "learner":
        owned_track_ids = {row.track_id for row in ProgramEnrollment.query.filter_by(user_id=user.id, status="active").all()}
        filtered_courses = []
        for item in course_rows:
            item_track_ids = {track.id for track in item.tracks}
            if item_track_ids.intersection(owned_track_ids):
                filtered_courses.append(item)
            elif not item_track_ids and Enrollment.query.filter_by(user_id=user.id, course_id=item.id).first():
                filtered_courses.append(item)
        course_rows = filtered_courses
        active_enrollment = _active_enrollment(user.id)
        enrollments_by_course = {
            row.course_id: row
            for row in Enrollment.query.filter_by(user_id=user.id).all()
        }

        # Each course has its own clock. Unstarted courses have no running deadline;
        # an enrollment's deadline begins from that course's started_at timestamp.
        repaired = False
        course_deadline_info = {}
        for course in course_rows:
            existing = enrollments_by_course.get(course.id)
            if existing:
                if existing.started_at is None:
                    existing.started_at = datetime.now(timezone.utc)
                    repaired = True
                old_deadline = existing.deadline_at
                deadline = _effective_enrollment_deadline(existing, repair=True)
                if existing.deadline_at != old_deadline:
                    repaired = True
                course_deadline_info[course.id] = {
                    "deadline_at": deadline,
                    "is_expired": _enrollment_expired(existing),
                    **(_deadline_display(deadline) or {}),
                }
            else:
                course_deadline_info[course.id] = {}
        if repaired:
            db.session.commit()
            active_enrollment = _active_enrollment(user.id)
    return render_template(
        "learning/courses.html",
        courses=course_rows,
        first_login=request.args.get("first_login") == "1",
        active_enrollment=active_enrollment,
        enrollments_by_course=enrollments_by_course,
        stage_unlocked={c.id: (_stage_is_unlocked(user, getattr(c, "stage", "hard_skills"), course=c) if user and user.role == "learner" else True) for c in course_rows},
        course_deadline_info=course_deadline_info if user and user.role == "learner" else {},
    )


@learning_bp.route("/courses/<slug>")
@permission_required("learning.course.view", "learner", "instructor", "mentor", "admin")
def course_detail(slug):
    course = Course.query.filter_by(slug=slug, published=True).first_or_404()
    user = current_user()
    if user and user.role == "learner" and not _learner_has_program_access(user.id, course):
        flash("This course belongs to a program you have not purchased. Browse programs to get access.", "error")
        return redirect(url_for("main.programs"))
    if user and user.role == "learner" and not _stage_is_unlocked(user, getattr(course, "stage", "hard_skills"), course=course):
        flash("Complete the previous Learning Path stage before opening this course.", "warning")
        return redirect(url_for("learning.courses"))
    enrollment = _enrollment(user.id, course.id) if user and user.role == "learner" else None
    active_enrollment = _active_enrollment(user.id, excluding_course_id=course.id) if user and user.role == "learner" else None
    program_deadline_info = None
    if user and user.role == "learner" and enrollment:
        effective_deadline = _effective_enrollment_deadline(enrollment, repair=True)
        if effective_deadline:
            program_deadline_info = {"deadline_at": effective_deadline, **(_deadline_display(effective_deadline) or {})}
            db.session.commit()
    deadline_expired = bool(user and user.role == "learner" and enrollment and _enrollment_expired(enrollment))
    module_states = {}
    module_open = {}
    lesson_states = {}
    lesson_open = {}
    if enrollment and not deadline_expired:
        for module in course.modules:
            _refresh_module_progress(user.id, module)
            module_states[module.id] = _module_complete(user.id, module)
            module_open[module.id] = _module_accessible(user.id, module)
            for lesson in module.lessons:
                lesson_states[lesson.id] = _lesson_complete(user.id, lesson)
                lesson_open[lesson.id] = _lesson_accessible(user.id, lesson)
        enrollment.progress = _refresh_progress(user.id, course)
        if _course_materials_complete(user.id, course):
            enrollment.progress = 100
            if not enrollment.completed_at:
                enrollment.completed_at = datetime.now(timezone.utc)
        else:
            enrollment.completed_at = None
        db.session.commit()
    return render_template("learning/course.html", course=course, enrollment=enrollment, active_enrollment=active_enrollment, module_states=module_states, module_open=module_open, lesson_states=lesson_states, lesson_open=lesson_open, program_deadline_info=program_deadline_info, deadline_expired=deadline_expired)


@learning_bp.post("/courses/<int:course_id>/enroll")
@permission_required("learning.enrollment.create", "learner")
def enroll(course_id):
    user = current_user()
    course = Course.query.filter_by(id=course_id, published=True).first_or_404()
    if course.tracks or not Enrollment.query.filter_by(user_id=user.id, course_id=course.id).first():
        flash("Courses are accessed through a program and cannot be enrolled in individually.", "info")
        return redirect(url_for("main.programs"))
    if not _stage_is_unlocked(user, getattr(course, "stage", "hard_skills"), course=course):
        flash("This course is locked until you complete the previous stage.", "warning")
        return redirect(url_for("learning.courses"))
    if _enrollment(user.id, course.id):
        return redirect(url_for("learning.course_detail", slug=course.slug))
    active = _active_enrollment(user.id, excluding_course_id=course.id)
    if active:
        active_course = db.session.get(Course, active.course_id)
        flash(f"Complete {active_course.title if active_course else 'your current course'} before enrolling in another course.", "error")
        return redirect(url_for("learning.course_detail", slug=active_course.slug if active_course else course.slug))
    amount = Decimal(course.price.amount if course.price else 0)
    coupon_code = request.form.get("coupon_code", "").strip() or (user.signup_coupon_code or "")
    try:
        coupon, discount, _ = _coupon_offer(user, coupon_code, amount, course.id) if coupon_code.strip() else (None, Decimal("0"), None)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    amount_due = max(Decimal("0"), amount - discount)
    if amount_due > 0:
        flash("This is a paid course. Continue to secure checkout to complete payment.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    db.session.add(_create_enrollment(user.id, course))
    if coupon:
        user.signup_coupon_code = None
        db.session.add(CouponRedemption(coupon_id=coupon.id, user_id=user.id, course_id=course.id, amount_before=amount, discount_amount=discount, amount_after=max(Decimal("0"), amount - discount), status="applied"))
        audit("coupon.redeemed")
    audit("learning.course_enrolled")
    db.session.commit()
    flash("You are enrolled in this learning path.", "success")
    return redirect(url_for("learning.course_detail", slug=course.slug))


@learning_bp.post("/programs/<int:track_id>/checkout")
@permission_required("learning.enrollment.create", "learner")
def program_checkout(track_id):
    user = current_user()
    track = Track.query.filter_by(id=track_id, published=True).first_or_404()
    if ProgramEnrollment.query.filter_by(user_id=user.id, track_id=track.id, status="active").first():
        flash("You already have access to this program.", "info")
        return redirect(url_for("main.program_page", track_id=track.id))
    if not any(course.published for course in track.courses):
        flash("This program is not ready for enrolment because it has no published courses.", "warning")
        return redirect(url_for("main.program_page", track_id=track.id))
    amount = Decimal(str(track.price_amount or 0))
    if amount < 0:
        flash("This program is not configured for purchase yet.", "error")
        return redirect(url_for("main.program_page", track_id=track.id))
    if amount == 0:
        now = datetime.now(timezone.utc)
        entitlement = ProgramEnrollment.query.filter_by(user_id=user.id, track_id=track.id).first()
        if entitlement:
            entitlement.purchased_at = now
            entitlement.status = "active"
        else:
            entitlement = ProgramEnrollment(user_id=user.id, track_id=track.id, purchased_at=now, status="active")
            db.session.add(entitlement)
        db.session.flush()
        for course in track.courses:
            if not course.published:
                continue
            existing = Enrollment.query.filter_by(user_id=user.id, course_id=course.id).first()
            if not existing:
                db.session.add(Enrollment(user_id=user.id, course_id=course.id, progress=0, started_at=now,
                    deadline_at=_course_deadline(course, now)))
            elif (existing.progress or 0) < 100:
                shared_with_other_owned_program = any(
                    other.id != track.id and ProgramEnrollment.query.filter_by(user_id=user.id, track_id=other.id, status="active").first()
                    for other in course.tracks
                )
                if not shared_with_other_owned_program:
                    existing.started_at = now
                    existing.deadline_at = _course_deadline(course, now)
        db.session.commit()
        flash("Program access activated. Your course completion periods start from today.", "success")
        return redirect(url_for("main.program_page", track_id=track.id))

    payment = ProgramPayment(user_id=user.id, track_id=track.id, reference=f"mawiz-program-{uuid.uuid4().hex}",
        amount=amount, currency=track.price_currency or "NGN")
    db.session.add(payment); db.session.flush()
    try:
        response = _paystack_request("/transaction/initialize", method="POST", payload={
            "email": (user.email or "").strip().lower(), "amount": _minor_units(amount),
            "currency": payment.currency, "reference": payment.reference,
            "callback_url": url_for("learning.paystack_callback", _external=True),
            "metadata": {"purchase_type": "program", "track_id": track.id, "program_payment_id": payment.id, "user_id": user.id},
        })
        authorization_url = _validated_paystack_checkout_url(response.get("authorization_url"))
        db.session.commit()
    except RuntimeError as exc:
        payment.status = "initialization_failed"; db.session.commit()
        current_app.logger.warning("program_checkout_initialization_failed user_id=%s track_id=%s error=%s", user.id, track.id, _safe_log_text(exc))
        flash(str(exc), "error")
        return redirect(url_for("main.program_page", track_id=track.id))
    return render_template("learning/payment_redirect.html", checkout_url=authorization_url, payment_context="program")


def _record_program_referral_purchase(payment):
    """Credit one verified program order to its original ambassador/SUG referral code."""
    if not get_bool("referral_program_enabled", True):
        return
    if ProgramReferralEvent.query.filter_by(program_payment_id=payment.id).first():
        return
    registration = ReferralEvent.query.filter_by(referred_user_id=payment.user_id, event_type="registration").order_by(ReferralEvent.created_at.asc()).first()
    referral = registration.referral if registration else Referral.query.filter_by(referred_user_id=payment.user_id).first()
    if not referral or referral.referrer_id == payment.user_id or referral.status != "active":
        return
    paid_at = payment.paid_at or datetime.now(timezone.utc)
    starts_at = referral.starts_at.replace(tzinfo=timezone.utc) if referral.starts_at and referral.starts_at.tzinfo is None else referral.starts_at
    ends_at = referral.ends_at.replace(tzinfo=timezone.utc) if referral.ends_at and referral.ends_at.tzinfo is None else referral.ends_at
    paid_at_cmp = paid_at.replace(tzinfo=timezone.utc) if paid_at.tzinfo is None else paid_at
    if starts_at and paid_at_cmp < starts_at:
        return
    if ends_at and paid_at_cmp > ends_at:
        return
    try:
        share_percent = Decimal(referral.share_percent if referral.share_percent is not None else get_setting("normal_referral_share_percent", get_setting("referral_share_percent", "10")))
    except (InvalidOperation, TypeError, ValueError):
        share_percent = Decimal("10")
    commission = (Decimal(payment.amount) * share_percent / Decimal("100")).quantize(Decimal("0.01"))
    db.session.add(ProgramReferralEvent(referral_id=referral.id, referred_user_id=payment.user_id,
        program_payment_id=payment.id, amount=payment.amount, commission_amount=commission,
        currency=payment.currency, status="eligible"))
    audit("referral.program_purchase_completed")


def _finalize_program_payment(payment):
    """Verify exact Paystack details, grant the program and set deadlines from purchase time."""
    result = _paystack_request(f"/transaction/verify/{payment.reference}")
    expected_email = payment.user.email.strip().lower()
    received_email = (result.get("customer") or {}).get("email", "").strip().lower()
    if (result.get("status") != "success" or result.get("reference") != payment.reference
        or int(result.get("amount") or 0) != _minor_units(payment.amount)
        or result.get("currency") != payment.currency or received_email != expected_email):
        payment.status = result.get("status") or "verification_failed"; db.session.commit(); return False
    newly_paid = payment.status != "success"
    if newly_paid:
        payment.status = "success"
        payment.paystack_transaction_id = str(result.get("id") or "")
        payment.paid_at = datetime.now(timezone.utc)
        provider_fee_minor = int(result.get("fees") or 0)
        payment.provider_fee_amount = (Decimal(provider_fee_minor) / Decimal("100")).quantize(Decimal("0.01"))
        payment.eligible_revenue_amount = max(Decimal("0.00"), Decimal(payment.amount) - payment.provider_fee_amount).quantize(Decimal("0.01"))
        paid_at = payment.paid_at
        entitlement = ProgramEnrollment.query.filter_by(user_id=payment.user_id, track_id=payment.track_id).first()
        if not entitlement:
            entitlement = ProgramEnrollment(user_id=payment.user_id, track_id=payment.track_id, payment_id=payment.id,
                purchased_at=paid_at, status="active")
            db.session.add(entitlement)
        else:
            entitlement.status = "active"
            entitlement.purchased_at = paid_at
        for course in payment.track.courses:
            if not course.published:
                continue
            enrollment = Enrollment.query.filter_by(user_id=payment.user_id, course_id=course.id).first()
            if not enrollment:
                db.session.add(Enrollment(user_id=payment.user_id, course_id=course.id, progress=0,
                    started_at=paid_at, deadline_at=_course_deadline(course, paid_at)))
            elif (enrollment.progress or 0) < 100 and not CoursePayment.query.filter_by(
                user_id=payment.user_id, course_id=course.id, purpose="deadline_penalty", status="success").first():
                shared_with_other_owned_program = any(
                    other.id != payment.track_id and ProgramEnrollment.query.filter_by(user_id=payment.user_id, track_id=other.id, status="active").first()
                    for other in course.tracks
                )
                # Never reset a deadline already serving another active program.
                if not shared_with_other_owned_program:
                    enrollment.started_at = paid_at
                    enrollment.deadline_at = _course_deadline(course, paid_at)
        _record_program_referral_purchase(payment)
        _mgsc_record_event("program_purchase", user_id=payment.user_id, program_payment=payment, occurred_at=paid_at)
    db.session.commit()
    return True


@learning_bp.post("/courses/<int:course_id>/checkout")
@permission_required("learning.enrollment.create", "learner")
def checkout(course_id):
    # Individual course checkout has been retired. Course access is purchased by program.
    Course.query.filter_by(id=course_id, published=True).first_or_404()
    flash("Individual course purchases are no longer available. Choose a program instead.", "info")
    return redirect(url_for("main.programs"))


@learning_bp.post("/courses/<int:course_id>/deadline-penalty")
@permission_required("learning.enrollment.create", "learner")
def deadline_penalty_checkout(course_id):
    """Create a Paystack checkout to restore access after a course deadline expires."""
    from app.common.settings import get_setting
    user = current_user()
    course = Course.query.filter_by(id=course_id, published=True).first_or_404()
    enrollment = _enrollment(user.id, course.id)
    if not enrollment:
        flash("Enroll in this course before requesting a deadline extension.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if not _enrollment_expired(enrollment):
        flash("Your course deadline has not expired.", "info")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    try:
        amount = Decimal(str(get_setting("deadline_penalty_amount", "5000") or "5000"))
        extension_days = int(get_setting("deadline_penalty_extension_days", "0") or 0)
        if amount <= 0 or extension_days < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Deadline penalty payment is not configured correctly. Please contact the administrator.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    payment = CoursePayment(
        user_id=user.id, course_id=course.id, reference=f"mawiz-penalty-{uuid.uuid4().hex}",
        amount=amount, currency="NGN",
        purpose="deadline_penalty", extension_days=extension_days,
    )
    db.session.add(payment)
    db.session.flush()
    try:
        response = _paystack_request("/transaction/initialize", method="POST", payload={
            "email": (user.email or "").strip().lower(),
            "amount": _minor_units(amount),
            "currency": payment.currency,
            "reference": payment.reference,
            "callback_url": url_for("learning.paystack_callback", _external=True),
            "metadata": {"purpose": "deadline_penalty", "course_id": course.id, "payment_id": payment.id, "user_id": user.id},
        })
        authorization_url = _validated_paystack_checkout_url(response.get("authorization_url"))
        db.session.commit()
    except RuntimeError as exc:
        payment.status = "initialization_failed"
        db.session.commit()
        current_app.logger.warning("deadline_penalty_checkout_failed user_id=%s course_id=%s error=%s", user.id, course.id, _safe_log_text(exc))
        flash(str(exc), "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    return render_template(
        "learning/payment_redirect.html",
        checkout_url=authorization_url,
        payment_context="deadline extension",
    )


@learning_bp.route("/payments")
@permission_required("learning.catalog.view", "learner")
def payment_history():
    """List only the signed-in learner's own course payments."""
    user = current_user()
    rows = CoursePayment.query.filter_by(user_id=user.id).order_by(CoursePayment.created_at.desc()).limit(100).all()
    program_rows = ProgramPayment.query.filter_by(user_id=user.id).order_by(ProgramPayment.created_at.desc()).limit(100).all()
    return render_template("learning/payments.html", payments=rows, program_payments=program_rows)


@learning_bp.route("/payments/paystack/callback")
def paystack_callback():
    reference = request.args.get("reference", "").strip()
    program_payment = ProgramPayment.query.filter_by(reference=reference).first()
    if program_payment:
        try:
            paid = _finalize_program_payment(program_payment)
        except RuntimeError:
            flash("We could not verify your program payment yet. Please try again shortly.", "error")
            return redirect(url_for("main.program_page", track_id=program_payment.track_id))
        flash("Program payment verified. Your courses are now available." if paid else "Program payment was not successful; access has not been granted.", "success" if paid else "error")
        return redirect(url_for("main.program_page", track_id=program_payment.track_id))
    payment = CoursePayment.query.filter_by(reference=reference).first()
    if not payment:
        flash("We could not find that payment.", "error")
        return redirect(url_for("learning.courses"))
    try:
        paid = _finalize_payment(payment)
    except RuntimeError:
        flash("We could not verify your payment yet. Please return to the course and try again shortly.", "error")
        return redirect(url_for("learning.course_detail", slug=payment.course.slug))
    if paid:
        flash("Payment verified. Your course is now available.", "success")
    else:
        flash("Payment was not successful, so course access has not been granted.", "error")
    return redirect(url_for("learning.course_detail", slug=payment.course.slug))


@learning_bp.post("/payments/paystack/webhook")
@csrf.exempt
def paystack_webhook():
    secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
    signature = request.headers.get("x-paystack-signature", "")
    raw_body = request.get_data()
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest() if secret_key else ""
    if not secret_key or not hmac.compare_digest(signature, expected):
        return jsonify({"ok": False}), 401
    payload = request.get_json(silent=True) or {}
    if payload.get("event") == "charge.success":
        reference = (payload.get("data") or {}).get("reference", "")
        program_payment = ProgramPayment.query.filter_by(reference=reference).first()
        if program_payment and program_payment.status != "success":
            try:
                _finalize_program_payment(program_payment)
            except RuntimeError:
                current_app.logger.exception("Unable to verify Paystack program payment %s", program_payment.reference)
                return jsonify({"ok": False}), 503
        payment = CoursePayment.query.filter_by(reference=reference).first()
        if payment and payment.status != "success":
            try:
                _finalize_payment(payment)
            except RuntimeError:
                current_app.logger.exception("Unable to verify Paystack webhook payment %s", payment.reference)
                return jsonify({"ok": False}), 503
    return jsonify({"ok": True})


@learning_bp.route("/modules/<int:module_id>")
@permission_required("learning.course.view", "learner", "instructor", "mentor", "admin")
def module(module_id):
    item = Module.query.get_or_404(module_id)
    user = current_user()
    if user.role == "learner":
        enrollment = _enrollment(user.id, item.course_id)
        if not enrollment:
            flash("Enroll in this course before opening its modules.", "error")
            return redirect(url_for("learning.course_detail", slug=item.course.slug))
        if _enrollment_expired(enrollment):
            flash("Your course deadline has expired. Pay the deadline penalty to resume learning.", "error")
            return redirect(url_for("learning.course_detail", slug=item.course.slug))
        if not _module_accessible(user.id, item):
            flash("Complete the previous module before opening this one.", "error")
            return redirect(url_for("learning.course_detail", slug=item.course.slug))
    return render_template("learning/module.html", module=item, module_complete=_module_complete(user.id, item) if user.role == "learner" else False)


@learning_bp.route("/lessons/<int:lesson_id>", methods=["GET", "POST"])
@permission_required("learning.lesson.view", "learner", "instructor", "mentor", "admin")
def lesson(lesson_id):
    item = Lesson.query.get_or_404(lesson_id)
    user = current_user()
    course = item.module.course
    if user.role == "learner":
        enrollment = _enrollment(user.id, course.id)
        if not enrollment:
            flash("Enroll in this course before starting its lessons.", "error")
            return redirect(url_for("learning.course_detail", slug=course.slug))
        if _enrollment_expired(enrollment):
            flash("Your course deadline has expired. Pay the deadline penalty to resume learning.", "error")
            return redirect(url_for("learning.course_detail", slug=course.slug))
        if not _lesson_accessible(user.id, item):
            flash("Complete the previous lesson or module before opening this lesson.", "error")
            return redirect(url_for("learning.course_detail", slug=course.slug))
    progress = LessonProgress.query.filter_by(learner_id=user.id, lesson_id=item.id).first() if user.role == "learner" else None
    if request.method == "POST" and user.role == "learner":
        # Re-check every required checkpoint on the server; the button never relies on JS.
        required_quizzes = Quiz.query.filter_by(lesson_id=item.id, published=True).all()
        pending_quizzes = [quiz for quiz in required_quizzes if not _passed_quiz(user.id, quiz.id)]
        required_assignments = Assignment.query.filter_by(lesson_id=item.id, published=True, required=True).all()
        pending_assignments = [assignment for assignment in required_assignments if not _assignment_done(user.id, assignment)]
        if pending_quizzes or pending_assignments:
            missing = []
            if pending_quizzes:
                missing.append("quiz: " + ", ".join(q.title for q in pending_quizzes))
            if pending_assignments:
                missing.append("assignment: " + ", ".join(a.title for a in pending_assignments))
            flash("This lesson is not ready to complete. Finish the required " + "; ".join(missing) + ".", "error")
            return redirect(url_for("learning.lesson", lesson_id=item.id))

        if not progress:
            progress = LessonProgress(learner_id=user.id, lesson_id=item.id)
            db.session.add(progress)
        # Idempotent update: repeated submissions do not reset the original completion time.
        if not progress.completed:
            progress.completed = True
            progress.completed_at = datetime.now(timezone.utc)
        enrollment = _enrollment(user.id, course.id)
        _refresh_module_progress(user.id, item.module)
        enrollment.progress = _refresh_progress(user.id, course)
        if _course_materials_complete(user.id, course):
            enrollment.progress = 100
            if not enrollment.completed_at:
                enrollment.completed_at = datetime.now(timezone.utc)
        else:
            enrollment.completed_at = None
        audit("learning.lesson_completed")
        db.session.commit()
        flash("Lesson marked complete. Your course progress has been updated.", "success")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    quizzes = Quiz.query.filter_by(lesson_id=item.id, published=True).all()
    assignments = Assignment.query.filter_by(lesson_id=item.id, published=True).order_by(Assignment.position).all()
    pending_quizzes = [quiz for quiz in quizzes if not _passed_quiz(user.id, quiz.id)] if user.role == "learner" else []
    pending_assignments = [assignment for assignment in assignments if assignment.required and not _assignment_done(user.id, assignment)] if user.role == "learner" else []
    course_modules = list(course.modules)
    module_number = course_modules.index(item.module) + 1
    course_lesson_number = 1 + sum(len(module.lessons) for module in course_modules[:module_number - 1]) + list(item.module.lessons).index(item)
    lesson_number_in_module = list(item.module.lessons).index(item) + 1
    return render_template("learning/lesson.html", lesson=item, progress=progress, quizzes=quizzes, assignments=assignments, pending_quizzes=pending_quizzes, pending_assignments=pending_assignments, module_number=module_number, lesson_number=lesson_number_in_module, course_lesson_number=course_lesson_number, lesson_complete=_lesson_complete(user.id, item) if user.role == "learner" else False)


@learning_bp.route("/assignments/<int:assignment_id>", methods=["GET", "POST"])
@permission_required("learning.lesson.view", "learner")
def assignment(assignment_id):
    item = Assignment.query.get_or_404(assignment_id)
    user = current_user()
    if not item.published:
        return redirect(url_for("learning.course_detail", slug=item.lesson.module.course.slug if item.lesson else item.module.course.slug))
    course = item.lesson.module.course if item.lesson else item.module.course
    enrollment = _enrollment(user.id, course.id)
    if not enrollment:
        flash("Enroll in this course first.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if _enrollment_expired(enrollment):
        flash("Your course deadline has expired. Pay the deadline penalty to resume learning.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if item.lesson and not _lesson_accessible(user.id, item.lesson):
        flash("Complete the previous lesson first.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if item.module and not item.lesson and not _module_accessible(user.id, item.module):
        flash("Complete the previous module first.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    submission = AssignmentSubmission.query.filter_by(assignment_id=item.id, learner_id=user.id).first()
    if request.method == "POST":
        response = request.form.get("response", "").strip()
        evidence_url = request.form.get("evidence_url", "").strip()[:1000]
        if not response and not evidence_url:
            flash("Provide a response or evidence link.", "error")
            return render_template("learning/assignment.html", assignment=item, submission=submission)
        if not submission:
            submission = AssignmentSubmission(assignment_id=item.id, learner_id=user.id)
            db.session.add(submission)
        submission.response = response
        submission.evidence_url = evidence_url
        submission.status = "submitted"
        audit("learning.assignment_submitted")
        db.session.commit()
        flash("Assignment submitted.", "success")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    return render_template("learning/assignment.html", assignment=item, submission=submission)


@learning_bp.route("/quizzes/<int:quiz_id>", methods=["GET", "POST"])
@permission_required("learning.quiz.take", "learner")
def quiz(quiz_id):
    item = Quiz.query.filter_by(id=quiz_id, published=True).first_or_404()
    user = current_user()
    lesson = Lesson.query.get_or_404(item.lesson_id)
    course = lesson.module.course
    enrollment = _enrollment(user.id, course.id)
    if not enrollment:
        flash("Enroll in this course before taking its quiz.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if _enrollment_expired(enrollment):
        flash("Your course deadline has expired. Pay the deadline penalty to resume learning.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if not _lesson_accessible(user.id, lesson):
        flash("Complete the previous lesson before taking this quiz.", "error")
        return redirect(url_for("learning.course_detail", slug=course.slug))
    if request.method == "POST":
        attempt = QuizAttempt(learner_id=user.id, quiz_id=item.id, max_score=sum(q.points for q in item.questions))
        db.session.add(attempt)
        score = 0
        for question in item.questions:
            selected = request.form.get(f"question_{question.id}", "")[:255]
            correct = selected == question.correct_option
            if correct:
                score += question.points
            db.session.add(QuizResponse(attempt=attempt, question_id=question.id, selected_option=selected, is_correct=correct))
        attempt.score = score
        percent = round((score / attempt.max_score) * 100) if attempt.max_score else 0
        attempt.passed = percent >= item.passing_score
        audit("learning.quiz_completed")
        db.session.commit()
        return render_template("learning/quiz_result.html", attempt=attempt, quiz=item, percent=percent)
    parsed = [(q, json.loads(q.options_json)) for q in item.questions]
    return render_template("learning/quiz.html", quiz=item, questions=parsed)
