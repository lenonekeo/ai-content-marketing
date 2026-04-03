"""
User store — persists users in data/users.json.

Fields per user:
  username     str   unique login handle
  email        str   used for password reset
  password_hash str  sha256 hex
  role         str   "admin" | "user"
  status       str   "active" | "pending"
  created_at   str   ISO timestamp
"""

import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_USERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _load() -> list:
    path = os.path.abspath(_USERS_FILE)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(users: list):
    path = os.path.abspath(_USERS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def bootstrap_admin():
    """
    On first run, migrate APP_USERNAME/APP_PASSWORD from .env into users.json
    so the existing admin account is preserved.
    """
    from config import config
    users = _load()
    if users:
        return  # Already initialised
    if config.app_username and config.app_password:
        users.append({
            "username": config.app_username,
            "email": "",
            "password_hash": _hash(config.app_password),
            "role": "admin",
            "status": "active",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        _save(users)
        logger.info(f"Bootstrapped admin user '{config.app_username}' into users.json")


def get_all() -> list:
    return _load()


def get_by_username(username: str) -> dict | None:
    return next((u for u in _load() if u["username"] == username), None)


def get_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    return next((u for u in _load() if u.get("email", "").lower() == email), None)


def authenticate(username: str, password: str) -> dict | None:
    """Return the user dict if credentials are valid and account is active, else None."""
    user = get_by_username(username)
    if not user:
        return None
    if user.get("status") != "active":
        return None
    if user["password_hash"] == _hash(password):
        return user
    return None


def create_user(username: str, email: str, password: str, role: str = "user", status: str = "pending") -> dict:
    """Create and persist a new user. Raises ValueError on duplicates."""
    users = _load()
    if any(u["username"] == username for u in users):
        raise ValueError("Username already taken.")
    if email and any(u.get("email", "").lower() == email.lower() for u in users):
        raise ValueError("Email already registered.")
    user = {
        "username": username,
        "email": email.strip().lower(),
        "password_hash": _hash(password),
        "role": role,
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    users.append(user)
    _save(users)
    logger.info(f"Created user '{username}' role={role} status={status}")
    return user


def update_password(username: str, new_password: str) -> bool:
    users = _load()
    for u in users:
        if u["username"] == username:
            u["password_hash"] = _hash(new_password)
            _save(users)
            return True
    return False


def update_status(username: str, status: str) -> bool:
    users = _load()
    for u in users:
        if u["username"] == username:
            u["status"] = status
            _save(users)
            return True
    return False


def delete_user(username: str) -> bool:
    users = _load()
    new_users = [u for u in users if u["username"] != username]
    if len(new_users) == len(users):
        return False
    _save(new_users)
    return True


def is_first_user() -> bool:
    return len(_load()) == 0
