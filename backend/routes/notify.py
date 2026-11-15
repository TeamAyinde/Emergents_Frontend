"""Transactional emails: booking confirmations (with ticket QR), gift resends, leaderboard winner."""
import asyncio
import io
import logging
from html import escape
from typing import Annotated, Optional

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

from services.emailer import EMAIL_FROM_NAME, send_email
from server import current_user, db

router = APIRouter(prefix="/api")
log = logging.getLogger("notify")
UserDep = Annotated[dict, Depends(current_user)]
MAX_GIFT_SENDS = 3
BRAND = escape(EMAIL_FROM_NAME)
_tasks: set = set()


def _wrap(title: str, body: str) -> str:
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
        f'<h2 style="margin:0 0 12px">{title}</h2>{body}'
        f'<p style="font-size:12px;color:#888;margin-top:24px">Sent by {BRAND}. We never ask for your password or card details by email.</p>'
        "</td></tr></table>"
    )


def _fmt(d) -> str:
    return d.strftime("%a %b %d, %Y · %I:%M %p UTC") if d else ""


def background(coro) -> None:
    """Fire-and-forget so payments/webhooks are never slowed by email."""
    async def runner():
        try:
            await coro
        except Exception:
            log.exception("background email failed")
    task = asyncio.create_task(runner())
    _tasks.add(task)  # keep a reference so the task isn't garbage-collected mid-send
    task.add_done_callback(_tasks.discard)


# ---------- Ticket QR image (linked from the confirmation email) ----------

@router.get("/tickets/{tid}/qr.png", include_in_schema=False)
async def ticket_qr(tid: str):
    """The ticket id is the secret printed in the QR; this just renders it as an image."""
    if not await db.tickets.find_one({"id": tid}, {"_id": 1}):
        raise HTTPException(404, "Ticket not found")
    buf = io.BytesIO()
    qrcode.make(tid, box_size=8, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


# ---------- Booking confirmations ----------

async def booking_email(tx: dict, rid: str) -> None:
    user = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0, "email": 1, "full_name": 1})
    if not user:
        return
    hi = f"<p>Hi {escape(user['full_name'].split(' ')[0])}, you're all set.</p>"
    paid = f"<p>Paid: <strong>${tx['amount']:,.2f}</strong></p>" if tx.get("amount") else ""
    if tx["kind"] == "ticket":
        t = await db.tickets.find_one({"id": rid}, {"_id": 0})
        origin = tx.get("origin", "")
        qr = (f'<p><img src="{escape(origin)}/api/tickets/{escape(rid)}/qr.png" width="200" height="200" alt="Ticket QR code"></p>'
              if origin.startswith("https://") else "")
        body = (f"{hi}<p><strong>{escape(t['event_title'])}</strong><br>{escape(t.get('venue_name', ''))}<br>"
                f"{_fmt(t.get('event_date'))}</p><p>{t['quantity']} × ticket</p>{paid}{qr}"
                f'<p>Show this QR at the door, or open the ticket in the {BRAND} app. Ticket ref: <strong>{escape(rid[:8].upper())}</strong></p>')
        subject = f"Your ticket for {t['event_title']}"
    elif tx["kind"] == "table":
        b = await db.table_bookings.find_one({"id": rid}, {"_id": 0})
        body = (f"{hi}<p><strong>Table {escape(b['table_id'])} · {escape(b['section'])}</strong><br>"
                f"{escape(b['event_title'])} · {escape(b['venue_name'])}<br>{_fmt(b.get('event_date'))}</p>"
                f"<p>Party of {b['party_size']} · minimum spend ${b['min_spend']:,.0f}</p>{paid}"
                f"<p>Booking ref: <strong>{escape(rid[:8].upper())}</strong>. Give your name at the door.</p>")
        subject = f"Your table at {b['venue_name']} is confirmed"
    else:
        r = await db.reservations.find_one({"id": rid}, {"_id": 0})
        body = (f"{hi}<p><strong>{escape(r['service_type'].capitalize())} · {escape(r.get('venue_name', ''))}</strong><br>"
                f"{_fmt(r.get('date'))}</p><p>Party of {r['party_size']}</p>{paid}"
                f"<p>Booking ref: <strong>{escape(rid[:8].upper())}</strong>.</p>")
        subject = f"Your reservation at {r.get('venue_name', BRAND)} is confirmed"
    await send_email(to=user["email"], subject=subject, html=_wrap("Booking confirmed", body))
    await db.payment_transactions.update_one({"id": tx["id"]}, {"$set": {"email_sent": True}})


# ---------- Leaderboard winner ----------

async def winner_email(award: dict) -> None:
    user = await db.users.find_one({"id": award["user_id"]}, {"_id": 0, "email": 1, "full_name": 1})
    if not user:
        return
    body = (f"<p>Congratulations {escape(user['full_name'].split(' ')[0])}!</p>"
            f"<p>You brought in <strong>{award['guests']} guests</strong> in {escape(award['_id'])} and finished "
            f"<strong>#1 on the {BRAND} promoter leaderboard</strong>.</p>"
            f"<p>Your <strong>${award['bonus']:,.0f} bonus</strong> is now in your wallet. Withdraw it any time from "
            f"the Profile tab in the {BRAND} app.</p>")
    await send_email(to=user["email"], subject=f"You won the {BRAND} promoter bonus", html=_wrap("You're this month's top promoter", body))


# ---------- Gift resend / change recipient ----------

class GiftEmailIn(BaseModel):
    recipient_email: Optional[EmailStr] = None


@router.post("/gifts/{gid}/email")
async def resend_gift(gid: str, body: GiftEmailIn, user: UserDep):
    from routes.growth import email_gift  # noqa: E402

    gift = await db.gifts.find_one({"id": gid, "buyer_id": user["id"]}, {"_id": 0})
    if not gift:
        raise HTTPException(404, "Gift not found")
    if gift["redeemed"]:
        raise HTTPException(400, "This gift has already been redeemed")
    to = (body.recipient_email or gift.get("recipient_email") or "").lower()
    if not to:
        raise HTTPException(400, "Add your friend's email")
    # atomic: concurrent requests can't push past the limit
    res = await db.gifts.update_one(
        {"id": gid, "redeemed": False, "$or": [{"email_sends": {"$lt": MAX_GIFT_SENDS}}, {"email_sends": {"$exists": False}}]},
        {"$set": {"recipient_email": to, "email_status": "sending"}, "$inc": {"email_sends": 1}})
    if res.modified_count == 0:
        raise HTTPException(429, f"This gift has been emailed {MAX_GIFT_SENDS} times — share the code instead")
    await email_gift(gid)
    g = await db.gifts.find_one({"id": gid}, {"_id": 0, "email_status": 1, "recipient_email": 1})
    if g["email_status"] != "sent":
        await db.gifts.update_one({"id": gid}, {"$inc": {"email_sends": -1}})  # failed sends don't count
        raise HTTPException(503, "Couldn't send the email right now — try again in a minute or share the code")
    return g


# ---------- Day-before event reminders ----------

REMINDER_EVERY_S = 900  # check every 15 minutes


async def _public_origin() -> str:
    doc = await db.settings.find_one({"_id": "public_origin"})
    return (doc or {}).get("url", "")


async def send_due_reminders() -> int:
    """Emails every ticket holder whose event starts in ~20–28 hours, once per ticket."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    origin = await _public_origin()
    sent = 0
    async for t in db.tickets.find({"event_date": {"$gte": now + timedelta(hours=20), "$lte": now + timedelta(hours=28)},
                                    "reminder_sent": {"$ne": True}}, {"_id": 0}):
        claimed = await db.tickets.update_one({"id": t["id"], "reminder_sent": {"$ne": True}}, {"$set": {"reminder_sent": True}})
        if not claimed.modified_count:
            continue
        user = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "email": 1, "full_name": 1, "email_prefs": 1})
        if not user or not (user.get("email_prefs") or {}).get("reminders", True):
            continue
        qr = (f'<p><img src="{escape(origin)}/api/tickets/{escape(t["id"])}/qr.png" width="200" height="200" alt="Ticket QR code"></p>'
              if origin.startswith("https://") else "")
        body = (f"<p>Hi {escape(user['full_name'].split(' ')[0])}, tomorrow's the night.</p>"
                f"<p><strong>{escape(t['event_title'])}</strong><br>{escape(t.get('venue_name', ''))}<br>{_fmt(t.get('event_date'))}</p>"
                f"<p>{t['quantity']} × ticket · ref <strong>{escape(t['id'][:8].upper())}</strong></p>{qr}"
                f"<p>Show this QR at the door, or open your ticket in the {BRAND} app.</p>")
        try:
            await send_email(to=user["email"], subject=f"Tomorrow: {t['event_title']}", html=_wrap("See you tomorrow", body))
            sent += 1
        except Exception:
            await db.tickets.update_one({"id": t["id"]}, {"$set": {"reminder_sent": False}})  # retry next round
    return sent


async def reminder_loop() -> None:
    while True:
        try:
            await send_due_reminders()
        except Exception:
            log.exception("reminder round failed")
        await asyncio.sleep(REMINDER_EVERY_S)


# ---------- Membership renewal receipts ----------

async def renewal_receipt(invoice: dict) -> None:
    """Emails a receipt for an automatic renewal (not the first charge), once per invoice."""
    from datetime import datetime, timezone

    from pymongo.errors import DuplicateKeyError

    if invoice.get("billing_reason") != "subscription_cycle" or not invoice.get("amount_paid"):
        return
    sub_id = invoice.get("subscription") or (((invoice.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
    user = await db.users.find_one({"stripe_subscription_id": sub_id}, {"_id": 0}) if sub_id else None
    if not user or not (user.get("email_prefs") or {}).get("receipts", True):
        return
    try:
        await db.receipts.insert_one({"_id": invoice["id"], "user_id": user["id"], "amount": invoice["amount_paid"] / 100,
                                      "created_at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        return
    level = (user.get("subscription_level") or user.get("level", "")).capitalize()
    period = "year" if user.get("subscription_interval") == "year" else "month"
    renews = user.get("level_paid_until")
    body = (f"<p>Hi {escape(user['full_name'].split(' ')[0])}, thanks for staying with {BRAND}.</p>"
            f"<p><strong>{escape(level)} membership · 1 {period}</strong><br>"
            f"Amount: <strong>${invoice['amount_paid'] / 100:,.2f} {escape(invoice.get('currency', 'usd').upper())}</strong><br>"
            f"Receipt no: {escape(str(invoice.get('number') or invoice['id']))}</p>"
            + (f"<p>Next renewal: {renews.strftime('%b %d, %Y')}</p>" if renews else "")
            + f"<p>Manage or cancel auto-renew any time under Membership in the {BRAND} app.</p>")
    await send_email(to=user["email"], subject=f"Your {EMAIL_FROM_NAME} {level} receipt", html=_wrap("Membership renewed", body))


# ---------- Venue payout summaries ----------

async def payout_email(venue_id: str, ids: list, transfer_id) -> None:
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0, "name": 1, "owner_id": 1})
    owner = await db.users.find_one({"id": (venue or {}).get("owner_id")}, {"_id": 0, "email": 1, "full_name": 1}) if venue else None
    if not owner:
        return
    rows = [r async for r in db.venue_payables.find({"id": {"$in": ids}}, {"_id": 0, "amount": 1, "source": 1})]
    by = {}
    for r in rows:
        n, s = by.get(r["source"], (0, 0.0))
        by[r["source"]] = (n + 1, s + r["amount"])
    names = {"ticket": "Tickets", "table": "Tables", "reservation": "Reservations"}
    lines = "".join(f"<tr><td style='padding:4px 12px 4px 0'>{names.get(k, escape(k))} · {n}</td>"
                    f"<td style='padding:4px 0;text-align:right'>${s:,.2f}</td></tr>" for k, (n, s) in by.items())
    total = sum(r["amount"] for r in rows)
    how = ("It's on its way to your linked bank through Stripe and usually lands in 1–3 business days."
           if transfer_id else f"It has been paid out by the {BRAND} team.")
    body = (f"<p>Hi {escape(owner['full_name'].split(' ')[0])}, here's your payout for <strong>{escape(venue['name'])}</strong>.</p>"
            f"<table role='presentation'>{lines}<tr><td style='padding:8px 12px 0 0'><strong>Total</strong></td>"
            f"<td style='padding:8px 0 0;text-align:right'><strong>${total:,.2f}</strong></td></tr></table>"
            f"<p>{how}</p><p>See every booking under Host Studio → Earnings in the {BRAND} app.</p>")
    await send_email(to=owner["email"], subject=f"{EMAIL_FROM_NAME} payout: ${total:,.2f} for {venue['name']}",
                     html=_wrap("Your payout is on its way", body))
