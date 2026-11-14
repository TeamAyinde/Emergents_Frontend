"""Monthly memberships (Stripe subscriptions, 7-day trial for gentlemen), venue boosts,
and Stripe Connect bank payouts for promoters and venues."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated, Literal, Optional
from urllib.parse import quote

import stripe
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from server import LEVEL_PRICE, current_user, db, require_roles
from stripe_core import OWN_KEY, call, g, ts

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
PayeeDep = Annotated[dict, Depends(require_roles("promoter", "venue_owner"))]
log = logging.getLogger("billing")
TRIAL_DAYS = 7
BOOST_PLANS = {"week": (49.0, 7), "month": (149.0, 30)}
APP_SCHEMES = ("exp://", "exps://", "frontend://")
ENDED = ("canceled", "unpaid", "incomplete_expired")


def _now():
    return datetime.now(timezone.utc)


# ---------- Memberships ----------

def trial_eligible(user: dict, level: str) -> bool:
    return level == "bronze" and user.get("membership_tier") == "trial_male" and not user.get("trial_used")


def subscription_params(user: dict, level: str) -> dict:
    trial = trial_eligible(user, level)
    sub_data: dict = {"metadata": {"user_id": user["id"], "level": level}}
    if trial:
        sub_data["trial_period_days"] = TRIAL_DAYS
    params = {
        "mode": "subscription",
        "line_items": [{
            "price_data": {
                "currency": "usd", "unit_amount": round(LEVEL_PRICE[level] * 100),
                "recurring": {"interval": "month"},
                "product_data": {"name": f"Nocturne {level.capitalize()} membership"},
            },
            "quantity": 1,
        }],
        "subscription_data": sub_data,
        "payment_method_collection": "always",
    }
    if user.get("stripe_customer_id"):
        params["customer"] = user["stripe_customer_id"]
    else:
        params["customer_email"] = user["email"]
    return params


def _period_end(sub) -> Optional[datetime]:
    end = g(sub, "current_period_end")
    if not end:
        items = g(g(sub, "items", {}), "data", [])
        end = g(items[0], "current_period_end") if items else None
    return ts(end or g(sub, "trial_end"))


async def _apply_subscription(user: dict, sub) -> None:
    status = g(sub, "status")
    upd = {
        "subscription_status": status, "level_paid_until": _period_end(sub),
        "subscription_cancel_at_period_end": bool(g(sub, "cancel_at_period_end", False)),
    }
    if status in ENDED:
        upd.update(stripe_subscription_id=None, subscription_level=None)
        if user.get("level") != "bronze":
            upd.update(level="bronze", level_since=_now())
    await db.users.update_one({"id": user["id"]}, {"$set": upd})


async def activate_subscription(tx: dict, session_id: str) -> str:
    """Called once Checkout completes: switch the member's level and replace any older plan."""
    user = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
    # expanded via the session: works with the test proxy too (it has no /subscriptions endpoint)
    session = await call(stripe.checkout.Session.retrieve, session_id, expand=["subscription"])
    sub = g(session, "subscription")
    sub_id = g(sub, "id")
    old = user.get("stripe_subscription_id")
    if old and old != sub_id:
        try:
            await call(stripe.Subscription.cancel, old)
        except Exception:
            log.exception("Could not cancel replaced subscription %s for user %s", old, user["id"])
    level = tx["payload"]["level"]
    now = _now()
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "level": level, "level_since": now, "subscription_level": level,
        "stripe_customer_id": g(session, "customer"), "stripe_subscription_id": sub_id,
        "trial_used": user.get("trial_used") or g(sub, "status") == "trialing",
    }})
    await _apply_subscription({**user, "level": level}, sub)
    rid = str(uuid.uuid4())
    await db.membership_payments.insert_one({
        "id": rid, "user_id": user["id"], "level": level, "amount": tx["amount"],
        "kind": "subscription", "session_id": session_id, "subscription_id": sub_id, "created_at": now,
    })
    return rid


async def sync_subscription_id(sub_id: str) -> None:
    if not OWN_KEY:
        return  # the test proxy can't read subscriptions; renewals sync once the own key is set
    user = await db.users.find_one({"stripe_subscription_id": sub_id}, {"_id": 0})
    if not user:
        return
    sub = await call(stripe.Subscription.retrieve, sub_id)
    await _apply_subscription(user, sub)


async def cancel_subscription_now(user: dict) -> None:
    if user.get("stripe_subscription_id"):
        try:
            await call(stripe.Subscription.cancel, user["stripe_subscription_id"])
        except Exception:
            log.exception("Could not cancel subscription %s", user["stripe_subscription_id"])
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "stripe_subscription_id": None, "subscription_status": "canceled", "subscription_level": None}})


class SubscriptionOut(BaseModel):
    active: bool
    status: Optional[str] = None
    level: Optional[str] = None
    renews_at: Optional[datetime] = None
    cancel_at_period_end: bool = False
    trial_available: bool = False
    manageable: bool = OWN_KEY  # cancel/resume needs Nocturne's own Stripe key


async def _sub_out(uid: str) -> SubscriptionOut:
    u = await db.users.find_one({"id": uid}, {"_id": 0})
    status = u.get("subscription_status") if u.get("stripe_subscription_id") else None
    return SubscriptionOut(
        active=status in ("active", "trialing", "past_due"), status=status, level=u.get("subscription_level"),
        renews_at=u.get("level_paid_until") if status else None,
        cancel_at_period_end=bool(u.get("subscription_cancel_at_period_end")),
        trial_available=trial_eligible(u, "bronze"),
    )


@router.get("/membership/subscription", response_model=SubscriptionOut)
async def my_subscription(user: UserDep):
    if user.get("stripe_subscription_id"):
        try:
            await sync_subscription_id(user["stripe_subscription_id"])
        except Exception:
            pass
    return await _sub_out(user["id"])


@router.post("/membership/subscription/{action}", response_model=SubscriptionOut)
async def toggle_renewal(action: Literal["cancel", "resume"], user: UserDep):
    sid = user.get("stripe_subscription_id")
    if not sid:
        raise HTTPException(400, "You don't have a monthly plan")
    if not OWN_KEY:
        raise HTTPException(503, "Auto-renew changes switch on once Nocturne's own Stripe account is connected")
    try:
        sub = await call(stripe.Subscription.modify, sid, cancel_at_period_end=action == "cancel")
    except Exception:
        raise HTTPException(503, "Could not reach Stripe — try again")
    await _apply_subscription(user, sub)
    return await _sub_out(user["id"])


# ---------- Venue boosts ----------

async def quote_boost(venue_id: str, plan: str, user: dict) -> dict:
    if plan not in BOOST_PLANS:
        raise HTTPException(400, "Pick a boost plan")
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if not venue:
        raise HTTPException(404, "Venue not found")
    if user["role"] != "admin" and venue.get("owner_id") != user["id"]:
        raise HTTPException(403, "Only the venue owner can boost this venue")
    price, days = BOOST_PLANS[plan]
    return {"total": price, "label": f"Featured boost · {venue['name']} · {days} days", "venue_id": None,
            "payload": {"venue_id": venue_id, "plan": plan}, "no_credit": True}


async def apply_boost(tx: dict) -> str:
    p = tx["payload"]
    _, days = BOOST_PLANS[p["plan"]]
    venue = await db.venues.find_one({"id": p["venue_id"]}, {"_id": 0, "featured_until": 1})
    cur = (venue or {}).get("featured_until")
    cur = cur.replace(tzinfo=timezone.utc) if cur and not cur.tzinfo else cur
    start = max(cur, _now()) if cur else _now()
    await db.venues.update_one({"id": p["venue_id"]}, {"$set": {"featured_until": start + timedelta(days=days)}})
    rid = str(uuid.uuid4())
    await db.boosts.insert_one({"id": rid, "venue_id": p["venue_id"], "user_id": tx["user_id"], "plan": p["plan"],
                                "amount": tx["amount"], "until": start + timedelta(days=days), "created_at": _now()})
    return rid


# ---------- Stripe Connect payouts ----------

class ConnectIn(BaseModel):
    origin_url: str = Field(max_length=300)
    return_url: Optional[str] = Field(default=None, max_length=300)


class ConnectStatus(BaseModel):
    available: bool
    connected: bool = False
    payouts_enabled: bool = False
    details_submitted: bool = False


async def _refresh_account(user: dict) -> ConnectStatus:
    acct_id = user.get("stripe_account_id")
    if not acct_id:
        return ConnectStatus(available=OWN_KEY)
    acct = await call(stripe.Account.retrieve, acct_id)
    st = ConnectStatus(available=OWN_KEY, connected=True, payouts_enabled=bool(g(acct, "payouts_enabled", False)),
                       details_submitted=bool(g(acct, "details_submitted", False)))
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "stripe_payouts_enabled": st.payouts_enabled, "stripe_details_submitted": st.details_submitted}})
    return st


@router.get("/connect/status", response_model=ConnectStatus)
async def connect_status(user: PayeeDep):
    if not OWN_KEY:
        return ConnectStatus(available=False)
    try:
        return await _refresh_account(user)
    except Exception:
        return ConnectStatus(available=True, connected=bool(user.get("stripe_account_id")),
                             payouts_enabled=bool(user.get("stripe_payouts_enabled")))


@router.post("/connect/onboard")
async def connect_onboard(body: ConnectIn, user: PayeeDep):
    if not OWN_KEY:
        raise HTTPException(503, "Bank payouts switch on once Nocturne's own Stripe account is connected")
    origin = body.origin_url.rstrip("/")
    if not origin.startswith(("https://", "http://")):
        raise HTTPException(400, "Invalid origin")
    if body.return_url and not body.return_url.startswith(APP_SCHEMES):
        raise HTTPException(400, "Invalid return link")
    try:
        acct_id = user.get("stripe_account_id")
        if not acct_id:
            acct = await call(stripe.Account.create, type="express", email=user["email"],
                              capabilities={"transfers": {"requested": True}},
                              metadata={"user_id": user["id"], "role": user["role"]})
            acct_id = acct.id
            await db.users.update_one({"id": user["id"]}, {"$set": {"stripe_account_id": acct_id}})
        back = (f"{origin}/api/connect/return?r={quote(body.return_url, safe='')}" if body.return_url
                else f"{origin}/payout-settings")
        link = await call(stripe.AccountLink.create, account=acct_id, type="account_onboarding",
                          refresh_url=back, return_url=back)
    except stripe.StripeError as exc:
        raise HTTPException(503, g(exc, "user_message") or "Stripe Connect isn't enabled on Nocturne's account yet")
    return {"url": link.url}


@router.get("/connect/return", response_class=HTMLResponse, include_in_schema=False)
async def connect_return(r: str):
    if not r.startswith(APP_SCHEMES):
        raise HTTPException(400, "Invalid return link")
    t = escape(r, quote=True)
    return HTMLResponse(
        f"<html><head><meta name=viewport content='width=device-width'><meta http-equiv=refresh content='0;url={t}'></head>"
        f"<body style='background:#09090b;color:#f4f4f5;font-family:sans-serif;text-align:center;padding-top:30vh'>"
        f"<a style='color:#d4af37' href='{t}'>Return to Nocturne</a></body></html>")


async def send_transfer(user_id: str, amount: float, purpose: str, ref: str) -> Optional[str]:
    """Sends `amount` USD to the user's connected bank via Stripe. Returns the transfer id, or None
    when they haven't connected (caller keeps the payout for manual handling)."""
    if not OWN_KEY or amount <= 0:
        return None
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "stripe_account_id": 1, "stripe_payouts_enabled": 1})
    if not u or not u.get("stripe_account_id") or not u.get("stripe_payouts_enabled"):
        return None
    tr = await call(stripe.Transfer.create, amount=round(amount * 100), currency="usd",
                    destination=u["stripe_account_id"], metadata={"purpose": purpose, "ref": ref},
                    idempotency_key=f"{purpose}:{ref}")
    return tr.id


async def try_auto_withdraw(wid: str) -> dict:
    w = await db.withdrawals.find_one({"id": wid}, {"_id": 0})
    try:
        tid = await send_transfer(w["user_id"], w["net"], "withdrawal", wid)
    except Exception as exc:
        await db.withdrawals.update_one({"id": wid}, {"$set": {"transfer_error": str(g(exc, "user_message") or exc)[:200]}})
        return {"status": "pending"}
    if not tid:
        return {"status": "pending"}
    await db.withdrawals.update_one({"id": wid}, {"$set": {"status": "paid", "transfer_id": tid, "paid_at": _now()}})
    return {"status": "paid", "transfer_id": tid}


async def sync_account_id(acct_id: str) -> None:
    user = await db.users.find_one({"stripe_account_id": acct_id}, {"_id": 0})
    if user:
        await _refresh_account(user)
