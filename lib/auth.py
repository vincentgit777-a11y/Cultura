"""
CULTURA — authentication and authorization helpers.

Provides:
- Password hashing with bcrypt
- JWT token generation and validation
- Session-based authentication for web views
- Role-based authorization decorators
- Current user resolution
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

from flask import current_app, g, redirect, request, session, url_for

try:
    import bcrypt
except ImportError:  # pragma: no cover - bcrypt is required
    bcrypt = None  # type: ignore


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Returns a string that can be stored directly in the database.
    """
    if bcrypt is None:
        raise RuntimeError("bcrypt is not installed. Run: pip install bcrypt")
    # bcrypt.gensalt() returns bytes, hashpw returns bytes
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    if bcrypt is None:
        raise RuntimeError("bcrypt is not installed. Run: pip install bcrypt")
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT handling
# ---------------------------------------------------------------------------

# Simple JWT implementation using HMAC-SHA256 (no external dependency)
# For production, consider using PyJWT library.

JWT_ALGORITHM = "HS256"
JWT_HEADER = {"alg": "HS256", "typ": "JWT"}


def _base64url_encode(data: bytes) -> str:
    """Base64 URL-safe encode without padding."""
    import base64
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    """Base64 URL-safe decode with padding handling."""
    import base64
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _signing_key() -> bytes:
    """Get the signing key from app config."""
    secret = current_app.config.get("SECRET_KEY", "fallback-secret")
    # Derive a consistent key from the secret
    return hashlib.sha256(secret.encode("utf-8")).digest()


def create_jwt(payload: dict[str, Any], expires_in: int = 3600) -> str:
    """
    Create a signed JWT token.

    Args:
        payload: Claims to include in the token.
        expires_in: Token lifetime in seconds (default 1 hour).

    Returns:
        A JWT string (header.payload.signature).
    """
    now = int(time.time())
    claims = {
        **payload,
        "iat": now,
        "exp": now + expires_in,
    }

    header_b64 = _base64url_encode(json.dumps(JWT_HEADER, separators=(",", ":")).encode())
    payload_b64 = _base64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    unsigned = f"{header_b64}.{payload_b64}"

    signature = hmac.new(_signing_key(), unsigned.encode("utf-8"), hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{unsigned}.{signature_b64}"


def decode_jwt(token: str) -> Optional[dict[str, Any]]:
    """
    Decode and verify a JWT token.

    Returns the payload dict if valid, None if invalid or expired.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        unsigned = f"{header_b64}.{payload_b64}"

        # Verify signature
        expected_sig = hmac.new(_signing_key(), unsigned.encode("utf-8"), hashlib.sha256).digest()
        expected_b64 = _base64url_encode(expected_sig)
        if not hmac.compare_digest(expected_b64, signature_b64):
            return None

        # Decode payload
        payload = json.loads(_base64url_decode(payload_b64))

        # Check expiration
        exp = payload.get("exp")
        if exp and int(time.time()) > exp:
            return None

        return payload
    except (ValueError, json.JSONDecodeError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Session-based authentication (for server-rendered views)
# ---------------------------------------------------------------------------

SESSION_USER_KEY = "user_id"
SESSION_USER_ROLE = "user_role"


def login_user(user_id: str, role: str, remember: bool = False) -> None:
    """
    Log in a user by storing their ID and role in the session.

    Args:
        user_id: The user's unique identifier.
        role: The user's role ('student' or 'admin').
        remember: If True, use permanent session (7 days).
    """
    session[SESSION_USER_KEY] = user_id
    session[SESSION_USER_ROLE] = role
    if remember:
        session.permanent = True
    session.modified = True


def logout_user() -> None:
    """Log out the current user by clearing the session."""
    session.clear()


def get_current_user_id() -> Optional[str]:
    """Get the current user's ID from the session."""
    return session.get(SESSION_USER_KEY)


def get_current_user_role() -> Optional[str]:
    """Get the current user's role from the session."""
    return session.get(SESSION_USER_ROLE)


def is_authenticated() -> bool:
    """Check if a user is logged in."""
    return get_current_user_id() is not None


def is_admin() -> bool:
    """Check if the current user is an admin."""
    return get_current_user_role() == "admin"


def is_student() -> bool:
    """Check if the current user is a student."""
    return get_current_user_role() == "student"


# ---------------------------------------------------------------------------
# Request context user loading
# ---------------------------------------------------------------------------

@dataclass
class CurrentUser:
    """Current user information attached to request context."""
    id: str
    email: str
    full_name: str
    role: str
    student_id: Optional[str] = None
    department: Optional[str] = None
    academic_year: Optional[str] = None


def load_current_user() -> Optional[CurrentUser]:
    """
    Load the current user from the session and attach to g.

    Should be called via a before_request handler.
    """
    user_id = get_current_user_id()
    if not user_id:
        g.current_user = None
        return None

    from app import load_users  # avoid circular import
    user = find_user_by_id(user_id)
    if not user:
        # User was deleted or session is stale
        logout_user()
        g.current_user = None
        return None

    g.current_user = CurrentUser(
        id=user["id"],
        email=user["email"],
        full_name=user.get("full_name", ""),
        role=user.get("role", "student"),
        student_id=user.get("student_id"),
        department=user.get("department"),
        academic_year=user.get("academic_year"),
    )
    return g.current_user


def find_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    """Find a user by ID from the users data file."""
    from app import load_users
    for user in load_users():
        if user.get("id") == user_id:
            return user
    return None


def get_current_user() -> Optional[CurrentUser]:
    """Get the current user from the request context."""
    return getattr(g, "current_user", None)


# ---------------------------------------------------------------------------
# Authorization decorators
# ---------------------------------------------------------------------------

def login_required(view: Callable) -> Callable:
    """
    Decorator that requires the user to be logged in.

    Redirects to login page with next parameter if not authenticated.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            if request.is_json or request.headers.get("Accept") == "application/json":
                from lib.responses import unauthorized
                return unauthorized("Authentication required")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def student_required(view: Callable) -> Callable:
    """
    Decorator that requires the user to be a student.

    Returns 403 if user is not a student.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            if request.is_json or request.headers.get("Accept") == "application/json":
                from lib.responses import unauthorized
                return unauthorized("Authentication required")
            return redirect(url_for("login", next=request.path))
        if not is_student():
            if request.is_json or request.headers.get("Accept") == "application/json":
                from lib.responses import forbidden
                return forbidden("Student access required")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view: Callable) -> Callable:
    """
    Decorator that requires the user to be an admin.

    Returns 403 if user is not an admin.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            if request.is_json or request.headers.get("Accept") == "application/json":
                from lib.responses import unauthorized
                return unauthorized("Authentication required")
            return redirect(url_for("admin_login", next=request.path))
        if not is_admin():
            if request.is_json or request.headers.get("Accept") == "application/json":
                from lib.responses import forbidden
                return forbidden("Admin access required")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def api_login_required(view: Callable) -> Callable:
    """
    Decorator for API endpoints that requires a valid JWT token.

    Expects Authorization: Bearer <token> header.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            from lib.responses import unauthorized
            return unauthorized("Missing or invalid Authorization header")

        token = auth_header[7:]  # Remove "Bearer "
        payload = decode_jwt(token)
        if not payload:
            from lib.responses import unauthorized
            return unauthorized("Invalid or expired token", code="TOKEN_INVALID")

        # Attach user info to request context
        g.api_user = payload
        return view(*args, **kwargs)
    return wrapped


def api_admin_required(view: Callable) -> Callable:
    """
    Decorator for API endpoints that requires admin role via JWT.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            from lib.responses import unauthorized
            return unauthorized("Missing or invalid Authorization header")

        token = auth_header[7:]
        payload = decode_jwt(token)
        if not payload:
            from lib.responses import unauthorized
            return unauthorized("Invalid or expired token", code="TOKEN_INVALID")

        if payload.get("role") != "admin":
            from lib.responses import forbidden
            return forbidden("Admin access required")

        g.api_user = payload
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# User registration and validation
# ---------------------------------------------------------------------------

def validate_registration_data(data: dict[str, Any]) -> dict[str, str]:
    """
    Validate student registration form data.

    Returns a dict of field -> error message. Empty dict means valid.
    """
    errors = {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""
    full_name = (data.get("full_name") or "").strip()
    student_id = (data.get("student_id") or "").strip()
    department = (data.get("department") or "").strip()
    academic_year = (data.get("academic_year") or "").strip()
    institution = (data.get("institution") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Enter a valid email address."

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if password != confirm_password:
        errors["confirm_password"] = "Passwords do not match."

    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) < 2:
        errors["full_name"] = "Full name must be at least 2 characters."

    if not department:
        errors["department"] = "Department is required."

    if not academic_year:
        errors["academic_year"] = "Academic year is required."

    # Check if email already exists
    from app import find_user_by_email
    if email and find_user_by_email(email):
        errors["email"] = "An account with this email already exists."

    return errors


def generate_user_id() -> str:
    """Generate a unique user ID."""
    return f"usr_{secrets.token_hex(6)}"


def generate_team_id() -> str:
    """Generate a unique team ID."""
    return f"tm_{secrets.token_hex(6)}"


def generate_competition_id() -> str:
    """Generate a unique competition ID."""
    return f"cmp_{secrets.token_hex(6)}"


def generate_schedule_id() -> str:
    """Generate a unique schedule entry ID."""
    return f"sch_{secrets.token_hex(6)}"


def generate_poster_id() -> str:
    """Generate a unique poster ID."""
    return f"pst_{secrets.token_hex(6)}"


def generate_notification_id() -> str:
    """Generate a unique notification ID."""
    return f"notif_{secrets.token_hex(6)}"