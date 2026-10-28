"""
Security, Authentication, Authorization & CSRF Middleware (`services/security.py`)
Provides:
  - Session-bound cryptographic CSRF token generation and verification
  - Role-Based Access Control decorators (@login_required, @admin_required)
  - Strict input validation and sanitization helpers
"""

import hmac
import re
import secrets
from datetime import datetime, date
from functools import wraps
from flask import session, request, jsonify, redirect, url_for, flash, abort

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{3,30}$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,20}$")

VALID_CATEGORIES = {
    "Electronics",
    "ID & Cards",
    "Books & Stationery",
    "Bags & Wallets",
    "Keys & Accessories",
    "Clothing & Eyewear",
    "Water Bottles & Umbrellas",
    "Other",
}


def wants_json_response() -> bool:
    """Return True if the request is targeting an `/api/` route or explicitly prefers JSON."""
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return (
        best == "application/json"
        and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def get_csrf_token() -> str:
    """Retrieve or generate a cryptographic 32-byte hex CSRF token bound to the current session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def verify_csrf_token() -> None:
    """
    Validate the CSRF token on all state-changing HTTP methods (POST, PUT, PATCH, DELETE).
    Accepts the token from:
      - Form field `csrf_token`
      - HTTP header `X-CSRF-Token`
      - JSON body field `csrf_token`
    Aborts with HTTP 400 if missing or invalid.
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return

    expected = session.get("_csrf_token")
    submitted = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
    )

    if not expected or not submitted or not hmac.compare_digest(str(expected), str(submitted)):
        abort(400, description="CSRF token is missing or invalid.")


def current_user() -> dict | None:
    """Return the authenticated user dictionary stored in the session, or None."""
    if "user_id" not in session:
        return None
    return {
        "user_id": session.get("user_id"),
        "student_id": session.get("student_id"),
        "full_name": session.get("full_name"),
        "email": session.get("email"),
        "department": session.get("department"),
        "role": session.get("role", "STUDENT"),
    }


def login_required(view_func):
    """Ensure the user is authenticated before accessing the route."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if wants_json_response():
                return jsonify({"ok": False, "error": "Authentication required."}), 401
            flash("Please sign in with your campus account to continue.", "warning")
            return redirect(url_for("login_page", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped


def admin_required(view_func):
    """Ensure the authenticated user holds the `ADMIN` role."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if wants_json_response():
                return jsonify({"ok": False, "error": "Authentication required."}), 401
            flash("Please sign in to access administrator tools.", "warning")
            return redirect(url_for("login_page", next=request.path))
        if session.get("role") != "ADMIN":
            if wants_json_response():
                return jsonify({"ok": False, "error": "Administrator privileges required."}), 403
            flash("Access denied: Administrator privileges are required for this action.", "danger")
            return redirect(url_for("dashboard_page"))
        return view_func(*args, **kwargs)

    return wrapped


def validate_date_str(date_str: str, field_label: str = "Date") -> date:
    """Parse a YYYY-MM-DD date string and verify it is not in the future."""
    if not date_str:
        raise ValueError(f"{field_label} is required.")
    try:
        parsed = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_label} must be in YYYY-MM-DD format.") from exc

    if parsed > date.today():
        raise ValueError(f"{field_label} cannot be in the future.")
    if parsed.year < 2020:
        raise ValueError(f"{field_label} must be a valid recent campus date.")
    return parsed


def clean_str(val: str | None, max_len: int = 255) -> str:
    """Strip whitespace and cap length."""
    if not val:
        return ""
    return str(val).strip()[:max_len]
