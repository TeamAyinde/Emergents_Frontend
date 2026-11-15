"""Stripe client setup shared by payments + billing.

Uses the owner's own secret key (STRIPE_API_KEY = sk_… / rk_…) when present; otherwise falls back
to Emergent's test proxy so checkout keeps working in preview. Connect (bank payouts) needs the own key.
"""
import asyncio
import os
from datetime import datetime, timezone

import certifi
import stripe

from server import db

_raw = (os.environ.get("STRIPE_API_KEY") or "").strip()
OWN_KEY = _raw.startswith(("sk_", "rk_")) and "emergent" not in _raw
stripe.api_key = _raw if OWN_KEY else "sk_test_emergent"
if not OWN_KEY:
    stripe.api_base = "https://integrations.emergentagent.com/stripe"
# Stripe's bundled CA list lacks the issuer used by the payments proxy; use the standard Mozilla bundle.
stripe.ca_bundle_path = certifi.where()

WEBHOOK_EVENTS = [
    "checkout.session.completed", "checkout.session.expired",
    "customer.subscription.updated", "customer.subscription.deleted",
    "invoice.paid", "invoice.payment_failed", "account.updated",
]


async def call(fn, *args, **kwargs):
    """Stripe's SDK is blocking — run it off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def g(obj, key, default=None):
    try:
        val = obj[key]
    except (KeyError, TypeError, AttributeError):
        return default
    return default if val is None else val


def ts(value) -> datetime | None:
    return datetime.fromtimestamp(value, tz=timezone.utc) if value else None


def session_paid(s) -> bool:
    return g(s, "status") == "complete" and g(s, "payment_status") in ("paid", "no_payment_required")


async def _ensure_webhook(origin: str) -> None:
    """With the owner's own key, register our webhook endpoint in their Stripe account (once per URL)."""
    url = f"{origin}/api/webhook/stripe"
    if not url.startswith("https://") or "localhost" in url:
        return
    if await db.settings.find_one({"_id": "stripe_webhook", "url": url}):
        return
    try:
        existing = await call(stripe.WebhookEndpoint.list, limit=100)
        if not any(g(e, "url") == url for e in existing.data):
            await call(stripe.WebhookEndpoint.create, url=url, enabled_events=WEBHOOK_EVENTS)
        await db.settings.update_one({"_id": "stripe_webhook"}, {"$set": {"url": url}}, upsert=True)
    except Exception:
        pass  # status polling still confirms payments


async def create_session(origin: str, **params):
    meta = params.setdefault("metadata", {})
    if OWN_KEY:
        await _ensure_webhook(origin)
    else:
        meta["webhook_url"] = f"{origin}/api/webhook/stripe"  # the proxy forwards events here
    return await call(stripe.checkout.Session.create, **params)


async def retrieve_session(session_id: str):
    return await call(stripe.checkout.Session.retrieve, session_id)
