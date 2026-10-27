"""
CULTURA — college cultural festival management platform.

A Flask application for discovering events, competitions, and schedules,
registering for activities, managing teams, and administering the festival.

Architecture
------------
    app.py            routes, template context, error handling
    config.py         settings (paths, secret key, rate limits)
    lib/storage.py    safe JSON reading/writing with file locking
    lib/security.py   CSRF tokens and a small rate limiter
    data/events.json  the event catalogue (single source of truth)
    data/settings.json site-wide settings and the FAQ
    data/registrations.json  runtime registration records (git-ignored)

No database is used. Registrations are appended to a local JSON file, which
means they belong to the machine running the application: they do not
synchronise between visitors' devices and may not survive a redeploy on an
ephemeral filesystem. The interface says so plainly.

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import os
import re
import secrets
import string
from datetime import datetime

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import Config, TestConfig
from lib.security import (
    CSRF_FIELD_NAME,
    RateLimiter,
    client_ip,
    get_csrf_token,
    rotate_csrf_token,
    validate_csrf_token,
)
from lib.storage import StorageError, read_json, update_json
from lib.auth import (
    hash_password,
    verify_password,
    login_user,
    logout_user,
    is_authenticated,
    is_admin,
    is_student,
    load_current_user,
    get_current_user,
    validate_registration_data,
    generate_user_id,
    generate_team_id,
    generate_competition_id,
    generate_schedule_id,
    generate_poster_id,
    generate_notification_id,
    login_required,
    student_required,
    admin_required,
    create_jwt,
    decode_jwt,
)

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{6,18}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ACADEMIC_YEARS = [
    "1st Year",
    "2nd Year",
    "3rd Year",
    "4th Year",
    "Post Graduate",
]

DEPARTMENTS = [
    "Computer Science & Engineering",
    "Information Technology",
    "Electronics & Communication",
    "Mechanical Engineering",
    "Civil Engineering",
    "Artificial Intelligence & Data Science",
    "Business Administration",
    "Commerce",
    "Science (Physics / Chemistry / Mathematics)",
    "Design & Multimedia",
    "Other",
]

REGISTRATION_STATUSES = ("open", "closed")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(config_object=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    os.makedirs(os.path.join(app.instance_path), exist_ok=True)

    limiter = RateLimiter(
        max_requests=app.config["RATE_LIMIT_MAX"],
        window_seconds=app.config["RATE_LIMIT_WINDOW"],
    )
    app.limiter = limiter

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def load_settings():
        """Return the site settings dictionary."""
        data = read_json(app.config["SETTINGS_FILE"], {})
        if not isinstance(data, dict):
            raise StorageError("settings.json must contain a JSON object.")
        return data.get("site", {}) or {}

    def load_faq():
        """Return the site-wide FAQ entries."""
        data = read_json(app.config["SETTINGS_FILE"], {})
        if not isinstance(data, dict):
            raise StorageError("settings.json must contain a JSON object.")
        return data.get("faq", []) or []

    def load_events():
        """
        Return the event catalogue as a list of normalised dictionaries.

        Slugs are validated and normalised here so that every page trusts the
        same shape.
        """
        data = read_json(app.config["EVENTS_FILE"], {})
        if not isinstance(data, dict):
            raise StorageError("events.json must contain a JSON object.")

        raw_events = data.get("events", [])
        if not isinstance(raw_events, list):
            raise StorageError("events.json must contain an 'events' list.")

        events = []
        seen_slugs = set()

        for raw in raw_events:
            if not isinstance(raw, dict):
                continue

            event = dict(raw)
            slug = str(event.get("slug", "")).strip().lower()

            if not SLUG_RE.match(slug):
                # A slug that cannot form a safe URL is skipped rather than
                # rendered into a broken link.
                continue
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            event["slug"] = slug
            event["title"] = str(event.get("title", "Untitled event")).strip()
            event["category"] = str(event.get("category", "General")).strip()
            event["short_description"] = str(event.get("short_description", "")).strip()
            event["description"] = str(event.get("description", "")).strip()
            event["date"] = str(event.get("date", "") or "").strip()
            event["start_time"] = str(event.get("start_time", "") or "").strip()
            event["end_time"] = str(event.get("end_time", "") or "").strip()
            event["venue"] = str(event.get("venue", "") or "").strip()
            event["eligibility"] = str(event.get("eligibility", "")).strip()
            event["team_requirements"] = str(event.get("team_requirements", "")).strip()
            event["rules"] = list(event.get("rules") or [])
            event["highlights"] = list(event.get("highlights") or [])
            event["milestones"] = list(event.get("milestones") or [])
            event["faq"] = list(event.get("faq") or [])
            event["prizes"] = dict(event.get("prizes") or {})

            try:
                event["min_team_size"] = max(1, int(event.get("min_team_size", 1)))
                event["max_team_size"] = max(
                    event["min_team_size"], int(event.get("max_team_size", 1))
                )
            except (TypeError, ValueError):
                event["min_team_size"] = 1
                event["max_team_size"] = 1

            event["participation_type"] = str(
                event.get("participation_type", "individual")
            ).strip()
            if event["participation_type"] not in ("individual", "team", "both"):
                event["participation_type"] = "individual"

            status = str(event.get("registration_status", "open")).strip().lower()
            event["registration_status"] = (
                status if status in REGISTRATION_STATUSES else "open"
            )

            capacity = event.get("capacity")
            event["capacity"] = int(capacity) if isinstance(capacity, int) else None

            events.append(event)

        return events

    def find_event(slug):
        """Return one event by slug, or None."""
        slug = (slug or "").strip().lower()
        if not slug:
            return None
        for event in load_events():
            if event["slug"] == slug:
                return event
        return None

    def load_registrations():
        """
        Return the list of registration records.

        Registration files are never served over HTTP.
        """
        data = read_json(app.config["REGISTRATIONS_FILE"], [])
        if isinstance(data, dict):
            data = data.get("registrations", [])
        if not isinstance(data, list):
            return []
        return data

    def save_registration(record):
        """Append a registration record to the local JSON file."""
        def append(current):
            records = current if isinstance(current, list) else []
            records.append(record)
            return records

        update_json(app.config["REGISTRATIONS_FILE"], [], append)

    # ------------------------------------------------------------------
    # New Cultura data access functions
    # ------------------------------------------------------------------

    def load_users():
        """Return the list of user accounts."""
        data = read_json(app.config["USERS_FILE"], {"users": []})
        if not isinstance(data, dict):
            raise StorageError("users.json must contain a JSON object.")
        users = data.get("users", [])
        if not isinstance(users, list):
            return []
        return users

    def find_user_by_email(email):
        """Find a user by email (case-insensitive)."""
        email = (email or "").strip().lower()
        if not email:
            return None
        for user in load_users():
            if user.get("email", "").lower() == email:
                return user
        return None

    def find_user_by_id(user_id):
        """Find a user by ID."""
        if not user_id:
            return None
        for user in load_users():
            if user.get("id") == user_id:
                return user
        return None

    def save_user(user):
        """Save a new user or update existing user."""
        def upsert(current):
            data = current if isinstance(current, dict) else {"users": []}
            users = data.get("users", [])
            if not isinstance(users, list):
                users = []
            # Remove existing user with same ID
            users = [u for u in users if u.get("id") != user["id"]]
            users.append(user)
            return {"users": users}

        update_json(app.config["USERS_FILE"], {"users": []}, upsert)

    def load_teams():
        """Return the list of teams."""
        data = read_json(app.config["TEAMS_FILE"], {"teams": []})
        if not isinstance(data, dict):
            raise StorageError("teams.json must contain a JSON object.")
        teams = data.get("teams", [])
        if not isinstance(teams, list):
            return []
        return teams

    def find_team_by_id(team_id):
        """Find a team by ID."""
        if not team_id:
            return None
        for team in load_teams():
            if team.get("id") == team_id:
                return team
        return None

    def find_teams_by_competition(competition_slug):
        """Find all teams for a competition."""
        slug = (competition_slug or "").strip().lower()
        if not slug:
            return []
        return [t for t in load_teams() if t.get("competition_slug") == slug]

    def find_teams_by_captain(captain_id):
        """Find all teams where user is captain."""
        if not captain_id:
            return []
        return [t for t in load_teams() if t.get("captain_id") == captain_id]

    def find_user_teams(user_id):
        """Find all teams where user is a member."""
        if not user_id:
            return []
        return [t for t in load_teams() if user_id in t.get("member_ids", [])]

    def save_team(team):
        """Save a new team or update existing team."""
        def upsert(current):
            data = current if isinstance(current, dict) else {"teams": []}
            teams = data.get("teams", [])
            if not isinstance(teams, list):
                teams = []
            teams = [t for t in teams if t.get("id") != team["id"]]
            teams.append(team)
            return {"teams": teams}

        update_json(app.config["TEAMS_FILE"], {"teams": []}, upsert)

    def load_competitions():
        """Return the list of competitions."""
        data = read_json(app.config["COMPETITIONS_FILE"], {"competitions": []})
        if not isinstance(data, dict):
            raise StorageError("competitions.json must contain a JSON object.")
        comps = data.get("competitions", [])
        if not isinstance(comps, list):
            return []
        return comps

    def find_competition(slug):
        """Find a competition by slug."""
        slug = (slug or "").strip().lower()
        if not slug:
            return None
        for comp in load_competitions():
            if comp.get("slug") == slug:
                return comp
        return None

    def load_schedule_entries():
        """Return the list of schedule entries."""
        data = read_json(app.config["SCHEDULE_ENTRIES_FILE"], {"schedule_entries": []})
        if not isinstance(data, dict):
            raise StorageError("schedule_entries.json must contain a JSON object.")
        entries = data.get("schedule_entries", [])
        if not isinstance(entries, list):
            return []
        return entries

    def load_published_schedule_entries():
        """Return only published schedule entries."""
        return [e for e in load_schedule_entries() if e.get("is_published")]

    def save_schedule_entry(entry):
        """Save a new schedule entry or update existing."""
        def upsert(current):
            data = current if isinstance(current, dict) else {"schedule_entries": []}
            entries = data.get("schedule_entries", [])
            if not isinstance(entries, list):
                entries = []
            entries = [e for e in entries if e.get("id") != entry["id"]]
            entries.append(entry)
            return {"schedule_entries": entries}

        update_json(app.config["SCHEDULE_ENTRIES_FILE"], {"schedule_entries": []}, upsert)

    def load_posters():
        """Return the list of posters."""
        data = read_json(app.config["POSTERS_FILE"], {"posters": []})
        if not isinstance(data, dict):
            raise StorageError("posters.json must contain a JSON object.")
        posters = data.get("posters", [])
        if not isinstance(posters, list):
            return []
        return posters

    def find_poster(poster_id):
        """Find a poster by ID."""
        if not poster_id:
            return None
        for poster in load_posters():
            if poster.get("id") == poster_id:
                return poster
        return None

    def save_poster(poster):
        """Save a new poster or update existing."""
        def upsert(current):
            data = current if isinstance(current, dict) else {"posters": []}
            posters = data.get("posters", [])
            if not isinstance(posters, list):
                posters = []
            posters = [p for p in posters if p.get("id") != poster["id"]]
            posters.append(poster)
            return {"posters": posters}

        update_json(app.config["POSTERS_FILE"], {"posters": []}, upsert)

    def load_notifications(user_id=None):
        """Return notifications, optionally filtered by user."""
        data = read_json(app.config["NOTIFICATIONS_FILE"], {"notifications": []})
        if not isinstance(data, dict):
            raise StorageError("notifications.json must contain a JSON object.")
        notifs = data.get("notifications", [])
        if not isinstance(notifs, list):
            return []
        if user_id is None:
            # Return broadcast announcements (user_id is null)
            return [n for n in notifs if n.get("user_id") is None]
        # Return user-specific notifications + broadcasts
        return [n for n in notifs if n.get("user_id") in (None, user_id)]

    def save_notification(notification):
        """Save a new notification."""
        def append(current):
            data = current if isinstance(current, dict) else {"notifications": []}
            notifs = data.get("notifications", [])
            if not isinstance(notifs, list):
                notifs = []
            notifs.append(notification)
            return {"notifications": notifs}

        update_json(app.config["NOTIFICATIONS_FILE"], {"notifications": []}, append)

    def mark_notification_read(notification_id, user_id):
        """Mark a notification as read."""
        def update(current):
            data = current if isinstance(current, dict) else {"notifications": []}
            notifs = data.get("notifications", [])
            if not isinstance(notifs, list):
                return data
            for n in notifs:
                if n.get("id") == notification_id and n.get("user_id") == user_id:
                    n["is_read"] = True
                    n["read_at"] = datetime.now().isoformat(timespec="seconds")
            return {"notifications": notifs}

        update_json(app.config["NOTIFICATIONS_FILE"], {"notifications": []}, update)

    # ------------------------------------------------------------------
    # Template context
    # ------------------------------------------------------------------

    @app.context_processor
    def inject_globals():
        settings = load_settings()
        try:
            events = load_events()
        except StorageError:
            events = []
        current_user = get_current_user()
        return {
            "site": settings,
            "site_name": settings.get("name", app.config["SITE_NAME"]),
            "all_events": events,
            "event_count": len(events),
            "categories": sorted({e["category"] for e in events}),
            "current_path": request.path,
            "current_year": datetime.now().year,
            "csrf_token": get_csrf_token(),
            "csrf_field": CSRF_FIELD_NAME,
            "current_user": current_user,
            "is_authenticated": current_user is not None,
            "is_admin": current_user is not None and current_user.role == "admin",
            "is_student": current_user is not None and current_user.role == "student",
        }

    @app.template_filter("pretty_date")
    def pretty_date(value):
        """Turn '2026-03-12' into '12 Mar 2026'. Empty input stays empty."""
        if not value:
            return ""
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return value
        return parsed.strftime("%d %b %Y").lstrip("0")

    @app.template_filter("pretty_time")
    def pretty_time(value):
        """Turn '14:30' into '2:30 PM'. Empty input stays empty."""
        if not value:
            return ""
        try:
            hours, minutes = value.split(":")
            hours = int(hours)
        except (ValueError, AttributeError):
            return value
        suffix = "AM" if hours < 12 else "PM"
        display = hours % 12 or 12
        return "{}:{} {}".format(display, minutes, suffix)

    @app.template_filter("has_value")
    def has_value(value):
        """True when a data field has been filled in."""
        return bool(value and str(value).strip())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def make_reference(event_slug):
        """Build a readable registration reference, e.g. 'TVN-PRWA-4F2A'."""
        letters = [c for c in event_slug.upper() if c.isalpha()]
        code = "".join(letters[:4]) or "EVT"
        return "TVN-{}-{}".format(code, secrets.token_hex(2).upper())

    def build_schedule(events):
        """
        Build the schedule from confirmed event data only.

        Events without a confirmed date are skipped, because inventing a time
        would misrepresent the festival programme.
        """
        sessions = []
        for event in events:
            if not event.get("date"):
                continue
            sessions.append({
                "slug": event["slug"],
                "title": event["title"],
                "category": event["category"],
                "date": event["date"],
                "start_time": event.get("start_time", ""),
                "end_time": event.get("end_time", ""),
                "venue": event.get("venue", ""),
            })

        sessions.sort(key=lambda s: (s["date"], s["start_time"]))
        days = []
        for session in sessions:
            if session["date"] not in [d["date"] for d in days]:
                days.append({"date": session["date"]})
        return sessions, days

    # ------------------------------------------------------------------
    # Authentication: before_request and auth routes
    # ------------------------------------------------------------------

    @app.before_request
    def load_user():
        """Load current user into g for every request."""
        load_current_user()

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """Student login page."""
        if request.method == "GET":
            next_url = request.args.get("next") or url_for("index")
            return render_template("login.html", page_title="Login", next_url=next_url)

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))
        next_url = request.form.get("next") or url_for("index")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html", page_title="Login", next_url=next_url, email=email), 400

        user = find_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            flash("Invalid email or password.", "error")
            return render_template("login.html", page_title="Login", next_url=next_url, email=email), 401

        if not user.get("is_active", True):
            flash("This account has been deactivated.", "error")
            return render_template("login.html", page_title="Login", next_url=next_url), 403

        if user.get("role") != "student":
            flash("Please use the admin login for administrator accounts.", "error")
            return render_template("login.html", page_title="Login", next_url=next_url), 403

        login_user(user["id"], "student", remember=remember)
        flash("Welcome back!", "success")
        return redirect(next_url)

    @app.route("/logout")
    def logout():
        """Log out the current user."""
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("index"))

    # ==================================================================
    # Student Dashboard Routes
    # ==================================================================

    @app.route("/dashboard")
    @student_required
    def student_dashboard():
        """Student dashboard with personalized data."""
        user = get_current_user()
        email = user.email

        # Get user's registrations
        registrations = [r for r in load_registrations()
                        if r.get("participant", {}).get("email") == email]

        # Get user's teams
        teams = find_user_teams(user.id)

        # Get upcoming events (events with dates in the future)
        from datetime import datetime
        today = datetime.now().date()
        all_events = load_events()
        upcoming_events = []
        for event in all_events:
            if event.get("date"):
                try:
                    event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                    if event_date >= today:
                        upcoming_events.append(event)
                except ValueError:
                    pass

        return render_template(
            "student/dashboard.html",
            page_title="Dashboard",
            registration_count=len(registrations),
            team_count=len(teams),
            upcoming_events=upcoming_events[:5],
            recent_registrations=registrations[-5:],
            teams=teams,
        )

    @app.route("/my-registrations")
    @student_required
    def my_registrations():
        """Student's registrations list."""
        user = get_current_user()
        email = user.email

        registrations = [r for r in load_registrations()
                        if r.get("participant", {}).get("email") == email]

        return render_template(
            "student/registrations.html",
            page_title="My Registrations",
            registrations=registrations,
        )

    @app.route("/my-teams")
    @student_required
    def my_teams():
        """Student's teams list."""
        user = get_current_user()
        teams = find_user_teams(user.id)

        # Also get captained teams
        captained = find_teams_by_captain(user.id)

        return render_template(
            "student/teams.html",
            page_title="My Teams",
            teams=teams,
            captained_teams=captained,
        )

    @app.route("/my-schedule")
    @student_required
    def my_schedule():
        """Student's personal schedule from registrations."""
        user = get_current_user()
        email = user.email

        registrations = [r for r in load_registrations()
                        if r.get("participant", {}).get("email") == email]

        # Build schedule from registered events
        events = load_events()
        schedule_sessions = []
        for reg in registrations:
            event = find_event(reg.get("event_slug", ""))
            if event and event.get("date"):
                schedule_sessions.append({
                    "title": event["title"],
                    "category": event["category"],
                    "date": event["date"],
                    "start_time": event.get("start_time", ""),
                    "end_time": event.get("end_time", ""),
                    "venue": event.get("venue", ""),
                    "slug": event["slug"],
                })

        schedule_sessions.sort(key=lambda s: (s["date"], s["start_time"]))

        # Group by date
        days = []
        for session in schedule_sessions:
            if session["date"] not in [d["date"] for d in days]:
                days.append({"date": session["date"]})

        return render_template(
            "student/schedule.html",
            page_title="My Schedule",
            sessions=schedule_sessions,
            days=days,
        )

    @app.route("/profile")
    @student_required
    def profile():
        """Student profile view/edit."""
        user = get_current_user()

        return render_template(
            "student/profile.html",
            page_title="Profile",
            user=user,
            academic_years=ACADEMIC_YEARS,
            departments=DEPARTMENTS,
        )

    @app.route("/profile", methods=["POST"])
    @student_required
    def profile_update():
        """Update student profile."""
        user = get_current_user()
        user_data = find_user_by_id(user.id)

        if not user_data:
            flash("User not found.", "error")
            return redirect(url_for("profile"))

        # Update allowed fields
        user_data["full_name"] = (request.form.get("full_name") or "").strip()
        user_data["student_id"] = (request.form.get("student_id") or "").strip()
        user_data["department"] = (request.form.get("department") or "").strip()
        user_data["academic_year"] = (request.form.get("academic_year") or "").strip()
        user_data["institution"] = (request.form.get("institution") or "").strip()
        user_data["phone"] = (request.form.get("phone") or "").strip()
        user_data["updated_at"] = datetime.now().isoformat(timespec="seconds")

        save_user(user_data)
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    @app.route("/register", methods=["GET", "POST"])
    def register_account():
        """Student account registration."""
        if request.method == "GET":
            return render_template("register_account.html", page_title="Create Account",
                                 academic_years=ACADEMIC_YEARS, departments=DEPARTMENTS,
                                 errors={}, form_data={})

        form_data = {
            "email": (request.form.get("email") or "").strip(),
            "password": request.form.get("password") or "",
            "confirm_password": request.form.get("confirm_password") or "",
            "full_name": (request.form.get("full_name") or "").strip(),
            "student_id": (request.form.get("student_id") or "").strip(),
            "department": (request.form.get("department") or "").strip(),
            "academic_year": (request.form.get("academic_year") or "").strip(),
            "institution": (request.form.get("institution") or "").strip(),
            "phone": (request.form.get("phone") or "").strip(),
        }

        errors = validate_registration_data(form_data)
        if errors:
            return render_template("register_account.html", page_title="Create Account",
                                 academic_years=ACADEMIC_YEARS, departments=DEPARTMENTS,
                                 form_data=form_data, errors=errors), 400

        # Create user
        user = {
            "id": generate_user_id(),
            "email": form_data["email"].lower(),
            "password_hash": hash_password(form_data["password"]),
            "role": "student",
            "full_name": form_data["full_name"],
            "student_id": form_data["student_id"],
            "department": form_data["department"],
            "academic_year": form_data["academic_year"],
            "institution": form_data["institution"],
            "phone": form_data["phone"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "last_login_at": None,
            "is_active": True,
        }

        save_user(user)
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        """Admin login page."""
        if request.method == "GET":
            next_url = request.args.get("next") or url_for("index")
            return render_template("admin/login.html", page_title="Admin Login", next_url=next_url)

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        next_url = request.form.get("next") or url_for("index")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("admin/login.html", page_title="Admin Login", next_url=next_url, email=email), 400

        user = find_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            flash("Invalid email or password.", "error")
            return render_template("admin/login.html", page_title="Admin Login", next_url=next_url, email=email), 401

        if not user.get("is_active", True):
            flash("This account has been deactivated.", "error")
            return render_template("admin/login.html", page_title="Admin Login", next_url=next_url), 403

        if user.get("role") != "admin":
            flash("Invalid admin credentials.", "error")
            return render_template("admin/login.html", page_title="Admin Login", next_url=next_url), 403

        login_user(user["id"], "admin", remember=True)
        flash("Welcome to the admin portal!", "success")
        return redirect(next_url)

    # ==================================================================
    # Routes
    # ==================================================================

    @app.route("/")
    def index():
        """Homepage — the visual identity anchor."""
        events = load_events()
        settings = load_settings()

        featured = events[:4]
        sessions, days = build_schedule(events)

        return render_template(
            "index.html",
            page_title="Home",
            featured_events=featured,
            schedule_sessions=sessions[:5],
            schedule_days=days,
            has_schedule=bool(sessions),
            meta_description=settings.get(
                "hero_description", "Technovana — a student technology festival."
            ),
        )

    @app.route("/events")
    def events():
        """
        Event directory with search, category filters and sorting.

        Filtering happens on the server so the page works without JavaScript;
        `static/js/events.js` then makes the same filters feel instant.
        """
        all_events = load_events()
        query = (request.args.get("q") or "").strip()
        category = (request.args.get("category") or "all").strip()
        sort = (request.args.get("sort") or "title").strip()

        results = all_events

        if query:
            needle = query.lower()
            results = [
                event for event in results
                if needle in event["title"].lower()
                or needle in event["category"].lower()
                or needle in event["short_description"].lower()
                or needle in event["description"].lower()
            ]

        if category and category != "all":
            results = [e for e in results if e["category"] == category]

        if sort == "category":
            results = sorted(results, key=lambda e: (e["category"], e["title"]))
        elif sort == "status":
            results = sorted(
                results,
                key=lambda e: (e["registration_status"] != "open", e["title"]),
            )
        elif sort == "date":
            # Events without a confirmed date are placed last.
            results = sorted(
                results,
                key=lambda e: (e["date"] == "", e["date"], e["start_time"], e["title"]),
            )
        else:
            results = sorted(results, key=lambda e: e["title"])

        return render_template(
            "events.html",
            page_title="Events",
            events=results,
            total_events=len(all_events),
            query=query,
            selected_category=category,
            selected_sort=sort,
            categories=sorted({e["category"] for e in all_events}),
        )

    @app.route("/competitions")
    def competitions():
        """
        Competitions directory with search, category filters and sorting.
        
        Shows only competitions (separate from general events).
        """
        all_competitions = load_competitions()
        query = (request.args.get("q") or "").strip()
        category = (request.args.get("category") or "all").strip()
        sort = (request.args.get("sort") or "title").strip()

        results = all_competitions

        if query:
            needle = query.lower()
            results = [
                comp for comp in results
                if needle in comp["title"].lower()
                or needle in comp["category"].lower()
                or needle in comp["short_description"].lower()
                or needle in comp["description"].lower()
            ]

        if category and category != "all":
            results = [c for c in results if c["category"] == category]

        if sort == "category":
            results = sorted(results, key=lambda c: (c["category"], c["title"]))
        elif sort == "status":
            results = sorted(
                results,
                key=lambda c: (c["registration_status"] != "open", c["title"]),
            )
        elif sort == "date":
            results = sorted(
                results,
                key=lambda c: (c["date"] == "", c["date"], c["start_time"], c["title"]),
            )
        else:
            results = sorted(results, key=lambda c: c["title"])

        return render_template(
            "competitions.html",
            page_title="Competitions",
            competitions=results,
            total_competitions=len(all_competitions),
            query=query,
            selected_category=category,
            selected_sort=sort,
            categories=sorted({c["category"] for c in all_competitions}),
        )

    @app.route("/competitions/<slug>")
    def competition_detail(slug):
        """A dedicated page for every competition."""
        comp = find_competition(slug)
        if not comp:
            abort(404)

        related = [
            other for other in load_competitions()
            if other["slug"] != comp["slug"]
            and other["category"] == comp["category"]
        ]
        if len(related) < 3:
            related += [
                other for other in load_competitions()
                if other["slug"] != comp["slug"]
                and other["category"] != comp["category"]
            ]

        return render_template(
            "competition_detail.html",
            page_title=comp["title"],
            competition=comp,
            related_competitions=related[:3],
            meta_description=comp["short_description"] or comp["description"][:150],
        )

    @app.route("/competitions/<slug>/register", methods=["GET", "POST"])
    def register_competition(slug):
        """
        The registration flow for a single competition.
        """
        comp = find_competition(slug)
        if not comp:
            abort(404)

        form_data = {}
        errors = {}

        if request.method == "POST":
            limiter = app.limiter
            if not limiter.allow(client_ip()):
                wait = limiter.retry_after(client_ip())
                flash(
                    "Too many registration attempts from this device. "
                    "Please try again in about {} second{}.".format(
                        wait, "" if wait == 1 else "s"
                    ),
                    "error",
                )
                return redirect(url_for("register_competition", slug=comp["slug"]))

            if not validate_csrf_token(request.form.get(CSRF_FIELD_NAME, "")):
                flash(
                    "Your form session expired or the security token was missing. "
                    "Please review the form and submit it again.",
                    "error",
                )
                return redirect(url_for("register_competition", slug=comp["slug"]))

            if comp["registration_status"] != "open":
                flash(
                    "Registration for '{}' is closed.".format(comp["title"]),
                    "error",
                )
                return redirect(url_for("competition_detail", slug=comp["slug"]))

            form_data = {
                "full_name": (request.form.get("full_name") or "").strip(),
                "email": (request.form.get("email") or "").strip(),
                "institution": (request.form.get("institution") or "").strip(),
                "phone": (request.form.get("phone") or "").strip(),
                "department": (request.form.get("department") or "").strip(),
                "academic_year": (request.form.get("academic_year") or "").strip(),
                "entry_type": (request.form.get("entry_type") or "").strip(),
                "team_name": (request.form.get("team_name") or "").strip(),
                "team_members": [
                    (m or "").strip()
                    for m in request.form.getlist("team_members")
                    if (m or "").strip()
                ],
                "notes": (request.form.get("notes") or "").strip(),
            }

            errors = validate_registration(form_data, comp)

            if not errors:
                record = {
                    "reference": make_reference(comp["slug"]),
                    "event_slug": comp["slug"],
                    "event_title": comp["title"],
                    "category": comp["category"],
                    "participant": {
                        "full_name": form_data["full_name"],
                        "email": form_data["email"],
                        "institution": form_data["institution"],
                        "phone": form_data["phone"],
                        "department": form_data["department"],
                        "academic_year": form_data["academic_year"],
                        "entry_type": form_data["entry_type"],
                        "team_name": form_data["team_name"],
                        "team_members": form_data["team_members"],
                        "notes": form_data["notes"],
                    },
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "confirmed",
                }

                try:
                    save_registration(record)
                except StorageError:
                    app.logger.exception("Could not write the registration file.")
                    flash(
                        "We could not save your registration because the local "
                        "storage file is unavailable. Please try again later.",
                        "error",
                    )
                    return redirect(url_for("register_competition", slug=comp["slug"]))

                rotate_csrf_token()
                session["last_registration"] = record["reference"]
                flash("Registration confirmed.", "success")
                return redirect(url_for("registration_success"))

        return render_template(
            "register.html",
            page_title="Register",
            event=comp,
            form_data=form_data,
            errors=errors,
            academic_years=ACADEMIC_YEARS,
            departments=DEPARTMENTS,
        )

    @app.route("/events/<slug>")
    def event_detail(slug):
        """A dedicated page for every event, all rendered by one template."""
        event = find_event(slug)
        if not event:
            abort(404)

        related = [
            other for other in load_events()
            if other["slug"] != event["slug"]
            and other["category"] == event["category"]
        ]
        if len(related) < 3:
            related += [
                other for other in load_events()
                if other["slug"] != event["slug"]
                and other["category"] != event["category"]
            ]

        return render_template(
            "event_detail.html",
            page_title=event["title"],
            event=event,
            related_events=related[:3],
            meta_description=event["short_description"] or event["description"][:150],
        )

    @app.route("/events/<slug>/register", methods=["GET", "POST"])
    def register(slug):
        """
        The registration flow for a single event.

        GET renders the form, POST validates and stores the record. The server
        is always the final authority — JavaScript only improves the
        experience.
        """
        event = find_event(slug)
        if not event:
            abort(404)

        form_data = {}
        errors = {}

        if request.method == "POST":
            # The limiter is read from the app object so it can be swapped in
            # tests and reconfigured without rebuilding the routes.
            limiter = app.limiter
            if not limiter.allow(client_ip()):
                wait = limiter.retry_after(client_ip())
                flash(
                    "Too many registration attempts from this device. "
                    "Please try again in about {} second{}.".format(
                        wait, "" if wait == 1 else "s"
                    ),
                    "error",
                )
                return redirect(url_for("register", slug=event["slug"]))

            if not validate_csrf_token(request.form.get(CSRF_FIELD_NAME, "")):
                flash(
                    "Your form session expired or the security token was missing. "
                    "Please review the form and submit it again.",
                    "error",
                )
                return redirect(url_for("register", slug=event["slug"]))

            if event["registration_status"] != "open":
                flash(
                    "Registration for '{}' is closed.".format(event["title"]),
                    "error",
                )
                return redirect(url_for("event_detail", slug=event["slug"]))

            form_data = {
                "full_name": (request.form.get("full_name") or "").strip(),
                "email": (request.form.get("email") or "").strip(),
                "institution": (request.form.get("institution") or "").strip(),
                "phone": (request.form.get("phone") or "").strip(),
                "department": (request.form.get("department") or "").strip(),
                "academic_year": (request.form.get("academic_year") or "").strip(),
                "entry_type": (request.form.get("entry_type") or "").strip(),
                "team_name": (request.form.get("team_name") or "").strip(),
                "team_members": [
                    (m or "").strip()
                    for m in request.form.getlist("team_members")
                    if (m or "").strip()
                ],
                "notes": (request.form.get("notes") or "").strip(),
            }

            errors = validate_registration(form_data, event)

            if not errors:
                record = {
                    "reference": make_reference(event["slug"]),
                    "event_slug": event["slug"],
                    "event_title": event["title"],
                    "category": event["category"],
                    "participant": {
                        "full_name": form_data["full_name"],
                        "email": form_data["email"],
                        "institution": form_data["institution"],
                        "phone": form_data["phone"],
                        "department": form_data["department"],
                        "academic_year": form_data["academic_year"],
                        "entry_type": form_data["entry_type"],
                        "team_name": form_data["team_name"],
                        "team_members": form_data["team_members"],
                        "notes": form_data["notes"],
                    },
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "confirmed",
                }

                try:
                    save_registration(record)
                except StorageError:
                    app.logger.exception("Could not write the registration file.")
                    flash(
                        "We could not save your registration because the local "
                        "storage file is unavailable. Please try again later.",
                        "error",
                    )
                    return redirect(url_for("register", slug=event["slug"]))

                rotate_csrf_token()
                # The confirmation is protected: only this browser session can
                # read it.
                session["last_registration"] = record["reference"]
                flash("Registration confirmed.", "success")
                return redirect(url_for("registration_success"))

        return render_template(
            "register.html",
            page_title="Register",
            event=event,
            form_data=form_data,
            errors=errors,
            academic_years=ACADEMIC_YEARS,
            departments=DEPARTMENTS,
        )

    @app.route("/registration/success")
    def registration_success():
        """
        Confirmation page.

        Only the reference stored in the current session can be displayed, so
        one participant can never open another participant's confirmation.
        """
        reference = session.get("last_registration")
        if not reference:
            flash(
                "There is no registration to show in this session. "
                "Register for an event first.",
                "info",
            )
            return redirect(url_for("events"))

        record = None
        for item in load_registrations():
            if item.get("reference") == reference:
                record = item
                break

        if record is None:
            flash(
                "That registration could not be found in the local storage file.",
                "error",
            )
            return redirect(url_for("events"))

        event = find_event(record.get("event_slug", ""))

        return render_template(
            "registration_success.html",
            page_title="Registration confirmed",
            record=record,
            event=event,
        )

    @app.route("/about")
    def about():
        """What Technovana is and what to expect."""
        settings = load_settings()
        return render_template(
            "about.html",
            page_title="About",
            principles=settings.get("principles", []),
            meta_description=settings.get("about_body", "")[:150],
        )

    @app.route("/schedule")
    def schedule():
        """Festival schedule built from confirmed session data only."""
        events = load_events()
        sessions, days = build_schedule(events)

        selected_day = (request.args.get("day") or "all").strip()
        selected_category = (request.args.get("category") or "all").strip()

        if selected_day != "all":
            sessions = [s for s in sessions if s["date"] == selected_day]
        if selected_category != "all":
            sessions = [s for s in sessions if s["category"] == selected_category]

        categories = sorted({e["category"] for e in events if e.get("date")})

        return render_template(
            "schedule.html",
            page_title="Schedule",
            sessions=sessions,
            days=days,
            categories=categories,
            selected_day=selected_day,
            selected_category=selected_category,
            has_schedule=bool(build_schedule(events)[0]),
        )

    @app.route("/faq")
    def faq():
        """Site-wide FAQ."""
        return render_template(
            "faq.html",
            page_title="FAQ",
            faq_entries=load_faq(),
        )

    # ==================================================================
    # Error handling
    # ==================================================================

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "404.html",
            page_title="Page not found",
            suggested_events=load_events()[:3],
        ), 404

    @app.errorhandler(400)
    def bad_request(error):
        return render_template(
            "400.html",
            page_title="Bad request",
        ), 400

    @app.errorhandler(413)
    def too_large(error):
        return render_template(
            "400.html",
            page_title="Request too large",
        ), 413

    @app.errorhandler(500)
    def server_error(error):
        # Never leak an internal traceback to a visitor.
        app.logger.exception("Unhandled error while serving a request.")
        return render_template(
            "500.html",
            page_title="Something went wrong",
        ), 500

    @app.errorhandler(StorageError)
    def storage_error(error):
        app.logger.error("Data file problem: %s", error)
        return render_template(
            "500.html",
            page_title="Data temporarily unavailable",
            storage_message=str(error),
        ), 500

    return app


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_registration(form, event):
    """
    Validate a submitted registration form.

    Returns a dictionary of field name -> error message. An empty dictionary
    means the submission is valid.
    """
    errors = {}

    full_name = form.get("full_name", "")
    email = form.get("email", "")
    institution = form.get("institution", "")
    phone = form.get("phone", "")
    department = form.get("department", "")
    academic_year = form.get("academic_year", "")
    entry_type = form.get("entry_type", "")
    team_name = form.get("team_name", "")
    team_members = form.get("team_members", [])

    if not full_name:
        errors["full_name"] = "Enter the participant's full name."
    elif len(full_name) < 3:
        errors["full_name"] = "The full name must be at least 3 characters long."
    elif len(full_name) > 100:
        errors["full_name"] = "The full name must be 100 characters or fewer."

    if not email:
        errors["email"] = "Enter an email address so the organisers can reach you."
    elif not EMAIL_RE.match(email):
        errors["email"] = "Enter a valid email address, for example name@example.edu."

    if institution and len(institution) > 120:
        errors["institution"] = "The institution name must be 120 characters or fewer."

    if phone and not PHONE_RE.match(phone):
        errors["phone"] = "Enter a valid phone number, or leave the field empty."

    if not department:
        errors["department"] = "Select your department."
    elif department not in DEPARTMENTS:
        errors["department"] = "Select a department from the list."

    if not academic_year:
        errors["academic_year"] = "Select your year of study."
    elif academic_year not in ACADEMIC_YEARS:
        errors["academic_year"] = "Select a year of study from the list."

    # --- Entry type and team rules -----------------------------------
    participation = event["participation_type"]
    min_size = event["min_team_size"]
    max_size = event["max_team_size"]

    if participation == "individual":
        entry_type = "individual"
    elif participation == "team":
        entry_type = "team"
        if not team_name:
            errors["team_name"] = "Enter a name for your team."
        if len(team_members) < min_size:
            errors["team_members"] = (
                "List at least {} team member name(s). You listed {}.".format(
                    min_size, len(team_members)
                )
            )
        if len(team_members) > max_size:
            errors["team_members"] = (
                "This event allows at most {} team member(s). You listed {}.".format(
                    max_size, len(team_members)
                )
            )
        if team_members and len(team_members) != len(
            {m.lower() for m in team_members}
        ):
            errors["team_members"] = "Every team member must be listed only once."
    else:  # "both"
        if entry_type not in ("individual", "team"):
            errors["entry_type"] = "Choose whether you are entering as a team or individually."
        elif entry_type == "team":
            if not team_name:
                errors["team_name"] = "Enter a name for your team."
            if len(team_members) < min_size:
                errors["team_members"] = (
                    "List at least {} team member name(s). You listed {}.".format(
                        min_size, len(team_members)
                    )
                )
            if len(team_members) > max_size:
                errors["team_members"] = (
                    "This event allows at most {} team member(s). You listed {}.".format(
                        max_size, len(team_members)
                    )
                )
            if team_members and len(team_members) != len(
                {m.lower() for m in team_members}
            ):
                errors["team_members"] = "Every team member must be listed only once."

    return errors


# ---------------------------------------------------------------------------
# API Routes (JSON endpoints for frontend integration)
# ---------------------------------------------------------------------------

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        """Authenticate user and return JWT token."""
        from lib.responses import success, unauthorized, validation_error

        if not request.is_json:
            return validation_error({"_form": "JSON body required"})

        data = request.get_json()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return validation_error({"email": "Email and password are required"})

        user = find_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            return unauthorized("Invalid email or password", code="INVALID_CREDENTIALS")

        if not user.get("is_active", True):
            return unauthorized("Account deactivated", code="ACCOUNT_DEACTIVATED")

        token = create_jwt({
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "full_name": user.get("full_name", ""),
        })

        return success({
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user["role"],
            }
        }, message="Login successful")

    @app.route("/api/auth/register", methods=["POST"])
    def api_register():
        """Register a new student account via API."""
        from lib.responses import created, validation_error

        if not request.is_json:
            return validation_error({"_form": "JSON body required"})

        data = request.get_json()
        errors = validate_registration_data(data)
        if errors:
            return validation_error(errors)

        user = {
            "id": generate_user_id(),
            "email": data["email"].lower(),
            "password_hash": hash_password(data["password"]),
            "role": "student",
            "full_name": data["full_name"],
            "student_id": data.get("student_id", ""),
            "department": data["department"],
            "academic_year": data["academic_year"],
            "institution": data.get("institution", ""),
            "phone": data.get("phone", ""),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "last_login_at": None,
            "is_active": True,
        }

        save_user(user)

        token = create_jwt({
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "full_name": user.get("full_name", ""),
        })

        return created({
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user["role"],
            }
        }, message="Account created successfully")

    @app.route("/api/auth/me", methods=["GET"])
    @api_login_required
    def api_me():
        """Get current authenticated user info."""
        from lib.responses import success

        return success({
            "user": g.api_user
        })

    # Student API
    @app.route("/api/student/dashboard", methods=["GET"])
    @api_login_required
    def api_student_dashboard():
        """Get student dashboard data."""
        from lib.responses import success

        if g.api_user.get("role") != "student":
            return unauthorized("Student access required")

        user_id = g.api_user["user_id"]
        registrations = [r for r in load_registrations() if r.get("participant", {}).get("email") == g.api_user.get("email")]
        teams = find_user_teams(user_id)
        upcoming_events = load_events()  # Filter for upcoming

        return success({
            "registration_count": len(registrations),
            "team_count": len(teams),
            "upcoming_events_count": len(upcoming_events),
            "recent_registrations": registrations[:5],
            "teams": teams,
        })

    @app.route("/api/student/registrations", methods=["GET"])
    @api_login_required
    def api_student_registrations():
        """Get student's registrations."""
        from lib.responses import success

        if g.api_user.get("role") != "student":
            return unauthorized("Student access required")

        email = g.api_user.get("email")
        registrations = [r for r in load_registrations() if r.get("participant", {}).get("email") == email]

        return success({"registrations": registrations})

    @app.route("/api/student/teams", methods=["GET"])
    @api_login_required
    def api_student_teams():
        """Get student's teams."""
        from lib.responses import success

        if g.api_user.get("role") != "student":
            return unauthorized("Student access required")

        user_id = g.api_user["user_id"]
        teams = find_user_teams(user_id)

        return success({"teams": teams})

    @app.route("/api/student/teams", methods=["POST"])
    @api_login_required
    def api_student_create_team():
        """Create a new team."""
        from lib.responses import created, validation_error, conflict

        if g.api_user.get("role") != "student":
            return unauthorized("Student access required")

        if not request.is_json:
            return validation_error({"_form": "JSON body required"})

        data = request.get_json()
        competition_slug = (data.get("competition_slug") or "").strip().lower()
        team_name = (data.get("name") or "").strip()

        if not competition_slug or not team_name:
            return validation_error({
                "competition_slug": "Competition is required" if not competition_slug else None,
                "name": "Team name is required" if not team_name else None,
            })

        comp = find_competition(competition_slug)
        if not comp:
            return validation_error({"competition_slug": "Competition not found"})

        if comp.get("participation_type") not in ("team", "both"):
            return validation_error({"competition_slug": "This competition does not support teams"})

        # Check if user already has a team for this competition
        existing = find_user_teams(g.api_user["user_id"])
        for t in existing:
            if t.get("competition_slug") == competition_slug:
                return conflict("You already have a team for this competition", code="DUPLICATE_TEAM_MEMBER")

        team = {
            "id": generate_team_id(),
            "competition_slug": competition_slug,
            "name": team_name,
            "captain_id": g.api_user["user_id"],
            "member_ids": [g.api_user["user_id"]],
            "max_size": comp.get("max_team_size", 4),
            "min_size": comp.get("min_team_size", 2),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "registration_id": None,
            "status": "draft",
        }

        save_team(team)
        return created({"team": team}, message="Team created successfully")

    # Admin API
    @app.route("/api/admin/dashboard", methods=["GET"])
    @api_admin_required
    def api_admin_dashboard():
        """Get admin dashboard metrics."""
        from lib.responses import success

        events = load_events()
        competitions = load_competitions()
        registrations = load_registrations()
        teams = load_teams()
        users = load_users()

        student_users = [u for u in users if u.get("role") == "student"]

        return success({
            "counts": {
                "events": len(events),
                "competitions": len(competitions),
                "registrations": len(registrations),
                "students": len(student_users),
                "teams": len(teams),
            },
            "recent_registrations": registrations[-10:],
            "upcoming_events": [e for e in events if e.get("date")][:5],
        })

    @app.route("/api/admin/events", methods=["GET"])
    @api_admin_required
    def api_admin_events_list():
        """List events with filters."""
        from lib.responses import success

        events = load_events()
        return success({"events": events})

    @app.route("/api/admin/events/<slug>", methods=["GET"])
    @api_admin_required
    def api_admin_events_get(slug):
        """Get single event."""
        from lib.responses import success, not_found

        event = find_event(slug)
        if not event:
            return not_found("Event")
        return success({"event": event})

    @app.route("/api/admin/events", methods=["POST"])
    @api_admin_required
    def api_admin_events_create():
        """Create new event."""
        from lib.responses import created, validation_error

        if not request.is_json:
            return validation_error({"_form": "JSON body required"})

        # TODO: Implement event creation
        return validation_error({"_form": "Not implemented yet"})

    @app.route("/api/admin/competitions", methods=["GET"])
    @api_admin_required
    def api_admin_competitions_list():
        """List competitions."""
        from lib.responses import success

        competitions = load_competitions()
        return success({"competitions": competitions})

    @app.route("/api/admin/competitions/<slug>", methods=["GET"])
    @api_admin_required
    def api_admin_competitions_get(slug):
        """Get single competition."""
        from lib.responses import success, not_found

        comp = find_competition(slug)
        if not comp:
            return not_found("Competition")
        return success({"competition": comp})

    @app.route("/api/admin/registrations", methods=["GET"])
    @api_admin_required
    def api_admin_registrations_list():
        """List all registrations."""
        from lib.responses import success

        registrations = load_registrations()
        return success({"registrations": registrations})

    @app.route("/api/admin/teams", methods=["GET"])
    @api_admin_required
    def api_admin_teams_list():
        """List all teams."""
        from lib.responses import success

        teams = load_teams()
        return success({"teams": teams})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app(Config)


if __name__ == "__main__":
    host = os.environ.get("CULTURA_HOST", "127.0.0.1")
    port = int(os.environ.get("CULTURA_PORT", "5000"))

    print("\n  CULTURA — college cultural festival")
    print("  Storage: local JSON files (no database)")
    print("  Open: http://{}:{}\n".format(host, port))

    app.run(host=host, port=port, debug=True)
