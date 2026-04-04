"""
Customer store — persists SaaS customers in saas/data/customers.json.

Fields per customer:
  id                str   UUID
  slug              str   subdomain handle (e.g. "acme")
  email             str   billing / owner email
  company           str   company name
  plan              str   "starter" | "pro" | "agency"
  status            str   "provisioning" | "active" | "suspended" | "cancelled"
  port              int   internal Docker port (8100+)
  created_at        str   ISO timestamp
  stripe_customer_id      str
  stripe_subscription_id  str
"""

import json
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)

_FILE = os.path.join(os.path.dirname(__file__), "data", "customers.json")


def _load() -> list:
    if not os.path.exists(_FILE):
        return []
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(customers: list):
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(customers, f, indent=2)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_all() -> list:
    return _load()


def get_by_id(customer_id: str) -> dict | None:
    return next((c for c in _load() if c["id"] == customer_id), None)


def get_by_slug(slug: str) -> dict | None:
    return next((c for c in _load() if c["slug"] == slug), None)


def get_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    return next((c for c in _load() if c.get("email", "").lower() == email), None)


def get_by_stripe_session(session_id: str) -> dict | None:
    return next((c for c in _load() if c.get("stripe_session_id") == session_id), None)


def slug_taken(slug: str) -> bool:
    return any(c["slug"] == slug for c in _load())


def next_port(start: int = 8100) -> int:
    used = {c["port"] for c in _load() if c.get("port")}
    port = start
    while port in used:
        port += 1
    return port


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def create(
    email: str,
    company: str,
    plan: str = "starter",
    slug: str = "",
    stripe_customer_id: str = "",
    stripe_session_id: str = "",
) -> dict:
    customers = _load()

    # Auto-generate slug from company name if not provided
    if not slug:
        base = "".join(c for c in company.lower() if c.isalnum() or c == "-").strip("-")
        slug = base[:20] or "customer"
        # ensure uniqueness
        orig = slug
        n = 2
        while any(c["slug"] == slug for c in customers):
            slug = f"{orig}{n}"
            n += 1

    port = next_port()
    customer = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "email": email.strip().lower(),
        "company": company.strip(),
        "plan": plan,
        "status": "provisioning",
        "port": port,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stripe_customer_id": stripe_customer_id,
        "stripe_session_id": stripe_session_id,
        "stripe_subscription_id": "",
    }
    customers.append(customer)
    _save(customers)
    logger.info(f"Created customer '{slug}' ({email}) port={port}")
    return customer


def update(customer_id: str, **fields) -> bool:
    customers = _load()
    for c in customers:
        if c["id"] == customer_id:
            c.update(fields)
            _save(customers)
            return True
    return False


def set_status(customer_id: str, status: str) -> bool:
    return update(customer_id, status=status)


def delete(customer_id: str) -> bool:
    customers = _load()
    new = [c for c in customers if c["id"] != customer_id]
    if len(new) == len(customers):
        return False
    _save(new)
    return True
