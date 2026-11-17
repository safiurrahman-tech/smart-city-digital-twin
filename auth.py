"""Admin authentication: password login -> signed session cookie, CSRF token for changes,
login lockout, and an optional X-Admin-Token header for scripts (curl)."""
import hmac, secrets, time
from functools import wraps
from flask import session, request, jsonify
from werkzeug.security import check_password_hash
import config

MAX_FAILS, LOCK_SECONDS, MIN_LEN = 5, 300, 10
_fails = {}  # ip -> [count, locked_until]

def problem():
    """Why login is not available, or None when it is."""
    if not config.SECRET_KEY or len(config.SECRET_KEY) < 24:
        return "Set SECRET_KEY to 24+ random characters in .env to enable persistent admin sessions."
    if config.ADMIN_PASSWORD_HASH:
        return None
    if not config.ADMIN_PASSWORD:
        return "Admin login is not set up. Add ADMIN_PASSWORD to .env and restart the server."
    if config.ADMIN_PASSWORD in ("change-me", "your-password") or len(config.ADMIN_PASSWORD) < MIN_LEN:
        return f"ADMIN_PASSWORD must be at least {MIN_LEN} characters and not a placeholder."
    return None

def _password_ok(pw):
    if config.ADMIN_PASSWORD_HASH:
        try:
            return check_password_hash(config.ADMIN_PASSWORD_HASH, pw)
        except ValueError:
            return False
    return hmac.compare_digest(pw.encode(), config.ADMIN_PASSWORD.encode())

def attempt(ip, pw):
    """Returns (ok, message)."""
    msg = problem()
    if msg:
        return False, msg
    now = time.time()
    count, until = _fails.get(ip, [0, 0])
    if until > now:
        return False, f"Too many failed attempts. Try again in {int(until - now) // 60 + 1} minute(s)."
    if _password_ok(pw):
        _fails.pop(ip, None)
        return True, ""
    count += 1
    _fails[ip] = [count, now + LOCK_SECONDS if count >= MAX_FAILS else 0]
    time.sleep(0.5)  # slows guessing a little
    return False, "Wrong password."

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        tok = request.headers.get("X-Admin-Token", "")
        if config.ADMIN_TOKEN and tok and hmac.compare_digest(tok.encode(), config.ADMIN_TOKEN.encode()):
            return f(*a, **k)
        if session.get("admin") is True:
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                sent = request.headers.get("X-CSRF-Token", "")
                if not hmac.compare_digest(sent.encode(), session.get("csrf", "").encode()):
                    return jsonify(error="Session check failed. Reload the page and try again."), 403
            return f(*a, **k)
        return jsonify(error="Sign in required."), 401
    return wrapper
