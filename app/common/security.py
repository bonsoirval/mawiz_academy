"""Authentication, authorization, audit, and redirect-safety helpers."""

from functools import wraps
from flask import abort, current_app, redirect, request, session, url_for
from app.extensions import db
from app.models import AuditEvent, Permission, RolePermission, User, UserPermission


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def has_permission(user, permission_code):
    if not user or not user.is_active:
        return False
    # Direct user-level denies override role grants; direct grants can add access.
    permission = Permission.query.filter_by(code=permission_code).first()
    if not permission:
        return False
    direct = UserPermission.query.filter_by(user_id=user.id, permission_id=permission.id).first()
    if direct is not None:
        return bool(direct.allowed)
    if user.role == "admin":
        return True
    return RolePermission.query.filter_by(role=user.role, permission_id=permission.id).first() is not None


def can(permission_code):
    """Template-friendly permission check for the signed-in user."""
    return has_permission(current_user(), permission_code)


def permission_required(permission_code, *allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or not user.is_active:
                return redirect(url_for("auth.login", next=request.path))
            if allowed_roles and user.role not in allowed_roles:
                abort(403)
            if not has_permission(user, permission_code):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def roles_required(*roles):
    # Backward-compatible RBAC-only decorator. New protected routes should prefer permission_required.
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or not user.is_active:
                return redirect(url_for("auth.login", next=request.path))
            if user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def audit(action):
    user = current_user()
    db.session.add(AuditEvent(user_id=user.id if user else None, action=action, ip_address=request.remote_addr))


def sanitize_next_url(value):
    if not value:
        return None
    from urllib.parse import urlparse
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return None
    return value
