"""
TECHNOVANA — small security helpers.

Two responsibilities:

* **CSRF protection.** Every state-changing form carries a random token that
  is stored in the signed session cookie and compared with the submitted
  value using `hmac.compare_digest`. The token is generated per session and
  rotated whenever a form is rendered, so a token cannot be replayed from a
  page that was never fetched.

* **Rate limiting.** A small in-memory limiter throttles registration
  attempts per client IP so the endpoint cannot be spammed by a single
  visitor.

Both are intentionally dependency-free — Flask alone is enough.
"""

import hmac
import secrets
import threading
import time

from flask import session


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FIELD_NAME = "csrf_token"


def get_csrf_token():
    """
    Return the CSRF token for the current session, creating one if needed.
    """
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
        session.modified = True
    return token


def rotate_csrf_token():
    """Issue a brand new token — used after a successful submission."""
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    session.modified = True
    return token


def validate_csrf_token(submitted):
    """Return True when the submitted token matches the session token."""
    expected = session.get(CSRF_SESSION_KEY)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(str(expected), str(submitted))


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    A tiny in-memory fixed-window rate limiter.

    `allow(key)` returns True while the client is under the limit. Timestamps
    are kept per key in a dict and pruned as they expire, so memory use stays
    small. This protects a single-process development server; a multi-process
    deployment would need a shared store such as Redis.
    """

    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = {}
        self._guard = threading.Lock()

    def allow(self, key):
        """Record an attempt for `key` and report whether it is allowed."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._guard:
            bucket = [stamp for stamp in self._hits.get(key, []) if stamp > cutoff]
            if len(bucket) >= self.max_requests:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True

    def retry_after(self, key):
        """Return the number of seconds until the next attempt is allowed."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._guard:
            bucket = [stamp for stamp in self._hits.get(key, []) if stamp > cutoff]
            self._hits[key] = bucket
            if len(bucket) < self.max_requests:
                return 0
            return max(0, int(round(bucket[0] + self.window_seconds - now)))

    def reset(self):
        """Forget every recorded attempt (used by the test-suite)."""
        with self._guard:
            self._hits.clear()


def client_ip():
    """Return the best guess at the caller's IP address."""
    from flask import request

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"
