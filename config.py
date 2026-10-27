"""
CULTURA — application configuration.

Everything that could reasonably change between machines lives here so that
`app.py` stays focused on routing.

Settings can be overridden with environment variables (see `.env.example`).
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name, default=False):
    """Read a boolean flag from the environment."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Base configuration used by the application."""

    # --- Flask core ------------------------------------------------------
    SECRET_KEY = os.environ.get(
        "CULTURA_SECRET_KEY",
        "cultura-local-development-key-change-me",
    )

    # --- Local data files ------------------------------------------------
    # The JSON data files live OUTSIDE the static folder so they can never be
    # downloaded directly by a browser.
    DATA_DIR = os.environ.get(
        "CULTURA_DATA_DIR",
        os.path.join(BASE_DIR, "data"),
    )

    EVENTS_FILE = os.environ.get(
        "CULTURA_EVENTS_FILE",
        os.path.join(BASE_DIR, "data", "events.json"),
    )

    REGISTRATIONS_FILE = os.environ.get(
        "CULTURA_REGISTRATIONS_FILE",
        os.path.join(BASE_DIR, "data", "registrations.json"),
    )

    SETTINGS_FILE = os.environ.get(
        "CULTURA_SETTINGS_FILE",
        os.path.join(BASE_DIR, "data", "settings.json"),
    )

    # --- New Cultura data files -------------------------------------------
    USERS_FILE = os.environ.get(
        "CULTURA_USERS_FILE",
        os.path.join(BASE_DIR, "data", "users.json"),
    )

    TEAMS_FILE = os.environ.get(
        "CULTURA_TEAMS_FILE",
        os.path.join(BASE_DIR, "data", "teams.json"),
    )

    COMPETITIONS_FILE = os.environ.get(
        "CULTURA_COMPETITIONS_FILE",
        os.path.join(BASE_DIR, "data", "competitions.json"),
    )

    SCHEDULE_ENTRIES_FILE = os.environ.get(
        "CULTURA_SCHEDULE_ENTRIES_FILE",
        os.path.join(BASE_DIR, "data", "schedule_entries.json"),
    )

    POSTERS_FILE = os.environ.get(
        "CULTURA_POSTERS_FILE",
        os.path.join(BASE_DIR, "data", "posters.json"),
    )

    NOTIFICATIONS_FILE = os.environ.get(
        "CULTURA_NOTIFICATIONS_FILE",
        os.path.join(BASE_DIR, "data", "notifications.json"),
    )

    # --- Session / cookies ------------------------------------------------
    SESSION_COOKIE_NAME = "cultura_session"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7  # 7 days
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Set CULTURA_HTTPS=1 when deploying behind HTTPS so the session
    # cookie is only sent over a secure connection.
    SESSION_COOKIE_SECURE = _env_bool("CULTURA_HTTPS", False)

    # --- Abuse prevention --------------------------------------------------
    # Simple in-memory rate limiter for the registration endpoint.
    # 10 attempts per IP per 10 minutes is plenty for a real student.
    RATE_LIMIT_MAX = int(os.environ.get("CULTURA_RATE_LIMIT_MAX", "10"))
    RATE_LIMIT_WINDOW = int(os.environ.get("CULTURA_RATE_LIMIT_WINDOW", "600"))

    # --- Application metadata ---------------------------------------------
    SITE_NAME = "Cultura"
    SITE_URL = os.environ.get("CULTURA_SITE_URL", "http://127.0.0.1:5000")
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB — no uploads in this version


class TestConfig(Config):
    """Configuration used by the automated test-suite.

    The tests point every data file at a temporary directory so that the
    real data files are never touched.
    """

    TESTING = True
    SECRET_KEY = "cultura-test-key"
    SESSION_COOKIE_SECURE = False
