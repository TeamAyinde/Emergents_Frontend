"""Email preferences, post-event feedback (bonus points) and win-back offers."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from services.emailer import EMAIL_FROM_NAME, send_email
from server import current_user, db, require_roles
from services.stripe_core import OWN_KEY, call

router = APIRouter(prefix="/api")
log = logging.getLogger("engage")
UserDep = Annotated[dict, Depends(current_user)]
BRAND = escape(EMAIL_FROM_NAME)
PREF_KEYS = ("reminders", "receipts", "feedback", "offers", "recap")  # newsletter = marketing_opt_in
FEEDBACK_POINTS = 50
WINBACK_PCT = 30
FEEDBACK_EVERY_S = 1800


def wants(user: dict, key: str) -> bool:
    return (user.get("email_prefs") or {}).get(key, True)


def _wrap(title: str, body: str) -> str:
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
        f'<h2 style="margin:0 0 12px">{title}</h2>{body}'
        f'<p style="font-size:12px;color:#888;margin-top:24px">Sent by {BRAND}. Change which emails you get under '
        f"Profile &rarr; Email preferences. We never ask for your password or card details by email.</p></td></tr></table>"
    )


# ---------- Preferences ----------

class EmailPrefs(BaseModel):
    reminders: bool = True
    receipts: bool = True
    feedback: bool = True
    offers: bool = True
    recap: bool = True  # promoters: Monday recap email
    newsletter: bool = False


class EmailPrefsIn(BaseModel):
    reminders: Optional[bool] = None
    receipts: Optional[bool] = None
    feedback: Optional[bool] = None
    offers: Optional[bool] = None
    recap: Optional[bool] = None
    newsletter: Optional[bool] = None


@router.get("/me/email-prefs", response_model=EmailPrefs)
async def get_prefs(user: UserDep):
    p = user.get("email_prefs") or {}
    return EmailPrefs(**{k: p.get(k, True) for k in PREF_KEYS}, newsletter=bool(user.get("marketing_opt_in")))


@router.put("/me/email-prefs", response_model=EmailPrefs)
async def put_prefs(body: EmailPrefsIn, user: UserDep):
    """Partial update: only the keys sent are changed."""
    cur = await get_prefs(user)
    new = cur.model_copy(update=body.model_dump(exclude_none=True))
    upd = {"email_prefs": {k: getattr(new, k) for k in PREF_KEYS}, "marketing_opt_in": new.newsletter}
    if new.newsletter and not user.get("marketing_opt_in"):
        upd["marketing_opt_in_at"] = datetime.now(timezone.utc)
    await db.users.update_one({"id": user["id"]}, {"$set": upd})
    return new


# ---------- Post-event feedback ----------

class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=500)


@router.get("/feedback/{ticket_id}")
async def feedback_info(ticket_id: str, user: UserDep):
    t = await db.tickets.find_one({"id": ticket_id, "user_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket not found")
    done = await db.feedback.find_one({"ticket_id": ticket_id}, {"_id": 0, "rating": 1})
    ev_date = t.get("event_date")
    can_rate = not ev_date or (ev_date if ev_date.tzinfo else ev_date.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
    return {"event_title": t["event_title"], "venue_name": t.get("venue_name", ""), "event_date": ev_date,
            "submitted": bool(done), "rating": (done or {}).get("rating"), "points": FEEDBACK_POINTS, "can_rate": can_rate}


@router.post("/feedback/{ticket_id}")
async def submit_feedback(ticket_id: str, body: FeedbackIn, user: UserDep):
    t = await db.tickets.find_one({"id": ticket_id, "user_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket not found")
    ev_date = t.get("event_date")
    if ev_date and (ev_date if ev_date.tzinfo else ev_date.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
        raise HTTPException(400, "You can rate the night once it has happened")
    ev = await db.events.find_one({"id": t["event_id"]}, {"_id": 0, "venue_id": 1})
    try:
        await db.feedback.insert_one({
            "_id": ticket_id, "ticket_id": ticket_id, "event_id": t["event_id"], "user_id": user["id"],
            "venue_id": (ev or {}).get("venue_id"), "event_title": t["event_title"], "user_name": user["full_name"],
            "rating": body.rating, "comment": (body.comment or "").strip() or None, "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        raise HTTPException(409, "You've already rated this night — thank you!")
    await db.users.update_one({"id": user["id"]}, {"$inc": {"points": FEEDBACK_POINTS}})
    await db.points_ledger.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "points": FEEDBACK_POINTS,
                                       "reason": f"Feedback · {t['event_title']}", "created_at": datetime.now(timezone.utc)})
    return {"points": FEEDBACK_POINTS}


async def send_feedback_requests() -> int:
    """Morning after: guests whose event ended 8–36h ago get one 'rate your night' email."""
    origin = ((await db.settings.find_one({"_id": "public_origin"})) or {}).get("url", "")
    if not origin.startswith("https://"):
        return 0  # link needs the public app address (saved on first real checkout)
    now = datetime.now(timezone.utc)
    sent = 0
    async for t in db.tickets.find({"event_date": {"$gte": now - timedelta(hours=36), "$lte": now - timedelta(hours=8)},
                                    "feedback_sent": {"$ne": True}}, {"_id": 0}):
        if not (await db.tickets.update_one({"id": t["id"], "feedback_sent": {"$ne": True}},
                                            {"$set": {"feedback_sent": True}})).modified_count:
            continue
        user = await db.users.find_one({"id": t["user_id"]}, {"_id": 0})
        if not user or not wants(user, "feedback"):
            continue
        link = f"{origin}/feedback/{t['id']}"
        body = (f"<p>Hi {escape(user['full_name'].split(' ')[0])}, how was <strong>{escape(t['event_title'])}</strong>"
                f"{' at ' + escape(t['venue_name']) if t.get('venue_name') else ''}?</p>"
                f"<p>Rate your night in 10 seconds and get <strong>{FEEDBACK_POINTS} bonus reward points</strong>.</p>"
                f'<p><a href="{escape(link)}" style="background:#d4af37;color:#1a0a00;padding:12px 20px;border-radius:24px;'
                f'text-decoration:none;font-weight:bold">Rate my night</a></p>')
        try:
            await send_email(to=user["email"], subject=f"How was {t['event_title']}?", html=_wrap("Rate your night", body))
            sent += 1
        except Exception:
            await db.tickets.update_one({"id": t["id"]}, {"$set": {"feedback_sent": False}})
    return sent


async def feedback_loop() -> None:
    while True:
        try:
            await send_feedback_requests()
        except Exception:
            log.exception("feedback round failed")
        await asyncio.sleep(FEEDBACK_EVERY_S)


# ---------- Win-back offer ----------

async def _winback_coupon() -> str:
    doc = await db.settings.find_one({"_id": "winback_coupon"})
    if doc:
        return doc["coupon_id"]
    c = await call(stripe.Coupon.create, percent_off=WINBACK_PCT, duration="once", name=f"Stay with {EMAIL_FROM_NAME}")
    await db.settings.update_one({"_id": "winback_coupon"}, {"$set": {"coupon_id": c.id}}, upsert=True)
    return c.id


async def on_renewal_cancelled(user: dict) -> None:
    """Once per member: email a one-time discount on their next renewal if they keep their plan."""
    if user.get("winback_offered") or not wants(user, "offers"):
        return
    res = await db.users.update_one({"id": user["id"], "winback_offered": {"$ne": True}},
                                    {"$set": {"winback_offered": True, "winback_offered_at": datetime.now(timezone.utc)}})
    if not res.modified_count:
        return
    level = (user.get("subscription_level") or "").capitalize()
    body = (f"<p>Hi {escape(user['full_name'].split(' ')[0])}, we're sorry to see you go.</p>"
            f"<p>Keep your <strong>{escape(level)}</strong> perks and get <strong>{WINBACK_PCT}% off your next renewal</strong>. "
            f"Open the {BRAND} app, go to Membership and tap <strong>Keep my plan</strong> — the discount is applied automatically.</p>")
    try:
        await send_email(to=user["email"], subject=f"{WINBACK_PCT}% off to stay {level}", html=_wrap("A little thank-you", body))
    except Exception:
        log.exception("win-back email failed")


async def apply_winback(user: dict, sub_id: str) -> bool:
    """On resume: apply the one-time discount if it was offered and not used yet."""
    if not OWN_KEY or not user.get("winback_offered") or user.get("winback_used"):
        return False
    res = await db.users.update_one({"id": user["id"], "winback_used": {"$ne": True}}, {"$set": {"winback_used": True}})
    if not res.modified_count:
        return False
    try:
        await call(stripe.Subscription.modify, sub_id, discounts=[{"coupon": await _winback_coupon()}])
        return True
    except Exception:
        await db.users.update_one({"id": user["id"]}, {"$set": {"winback_used": False}})
        log.exception("could not apply win-back discount")
        return False


# ---------- Host feedback view ----------

@router.get("/host/feedback")
async def host_feedback(user: Annotated[dict, Depends(require_roles("venue_owner", "admin"))]):
    """Guest ratings & comments for the owner's venues (guest shown by first name only)."""
    filt = {} if user["role"] == "admin" else {"owner_id": user["id"]}
    ids = [v["id"] async for v in db.venues.find(filt, {"id": 1})]
    rows = [r async for r in db.feedback.find({"venue_id": {"$in": ids}}, {"_id": 0}).sort("created_at", -1).limit(50)]
    agg = await db.feedback.aggregate([{"$match": {"venue_id": {"$in": ids}}},
                                       {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}}]).to_list(1)
    return {
        "average": round(agg[0]["avg"], 1) if agg else None, "count": agg[0]["n"] if agg else 0,
        "items": [{"id": r["ticket_id"], "event_title": r.get("event_title", ""), "rating": r["rating"],
                   "comment": r.get("comment"), "guest": (r.get("user_name") or "Guest").split(" ")[0],
                   "created_at": r["created_at"]} for r in rows],
    }


# ---------- Referral rewards ----------

REFERRER_POINTS = 200
FRIEND_POINTS = 100


async def reward_referral(user_id: str) -> None:
    """First paid night of an invited member: both friends get bonus points, once."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("referred_by"):
        return
    res = await db.users.update_one({"id": user_id, "referral_rewarded": {"$ne": True}}, {"$set": {"referral_rewarded": True}})
    if not res.modified_count:
        return
    now = datetime.now(timezone.utc)
    for uid, pts, why in ((user["referred_by"], REFERRER_POINTS, f"Invited {user['full_name'].split(' ')[0]}"),
                          (user_id, FRIEND_POINTS, "Welcome bonus · first night")):
        await db.users.update_one({"id": uid}, {"$inc": {"points": pts}})
        await db.points_ledger.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "points": pts, "reason": why, "created_at": now})


@router.get("/me/invites")
async def my_invites(user: UserDep):
    total = await db.users.count_documents({"referred_by": user["id"]})
    rewarded = await db.users.count_documents({"referred_by": user["id"], "referral_rewarded": True})
    return {"code": user["referral_code"], "invited": total, "rewarded": rewarded,
            "points_earned": rewarded * REFERRER_POINTS, "referrer_points": REFERRER_POINTS, "friend_points": FRIEND_POINTS}
