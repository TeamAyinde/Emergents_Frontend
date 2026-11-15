"""Stripe Checkout (test mode) for tickets, table deposits, venue reservations and memberships.

Money flow (marketplace): the guest pays Nocturne. Nocturne keeps the platform fee, owes the
venue its share (tracked in `venue_payables`) and owes promoters their commission (wallet).
"""
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Annotated, List, Literal, Optional
from urllib.parse import quote

import json
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from routes.billing import (
    YEARLY_PRICE, activate_subscription, apply_boost, apply_spotlight, quote_boost, quote_spotlight, send_transfer, subscription_params, sync_account_id,
    sync_subscription_id, trial_eligible,
)
from routes.growth import create_gift, quote_gift
from routes.features import approved_request, quote_table, save_table
from server import (
    LEVEL_PRICE, LEVEL_RANK, ReservationIn, amount_due, current_user, db, issue_ticket,
    quote_reservation, require_level, require_roles, save_reservation, ticket_price,
)
from services.stripe_core import OWN_KEY, call, create_session, g, retrieve_session, session_paid

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
AdminDep = Annotated[dict, Depends(require_roles("admin"))]
MIN_CHARGE = 0.50  # Stripe minimum in USD
APP_SCHEMES = ("exp://", "exps://", "frontend://")


def _now():
    return datetime.now(timezone.utc)


class CheckoutIn(BaseModel):
    kind: Literal["ticket", "table", "reservation", "membership", "boost", "spotlight", "gift"]
    origin_url: str = Field(max_length=300)
    return_url: Optional[str] = Field(default=None, max_length=300)  # native deep link
    event_id: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=8)
    promoter_code: Optional[str] = Field(default=None, max_length=20)
    table_id: Optional[str] = None
    party_size: int = Field(default=1, ge=1, le=30)
    venue_id: Optional[str] = None
    service_type: Optional[str] = None
    date: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    level: Optional[str] = None
    plan: Optional[str] = None  # boost: week | month · spotlight: 3days | week
    interval: Literal["month", "year"] = "month"  # membership billing
    recipient_email: Optional[EmailStr] = None  # gift
    note: Optional[str] = Field(default=None, max_length=200)  # gift message


class CheckoutOut(BaseModel):
    url: Optional[str] = None
    session_id: Optional[str] = None
    amount: float
    paid_with_credit: bool = False
    result_id: Optional[str] = None


class PaymentStatusOut(BaseModel):
    session_id: str
    kind: str
    label: str
    amount: float
    status: str  # pending | paid | cancelled | expired | failed
    result_id: Optional[str] = None
    error: Optional[str] = None


async def _quote(body: CheckoutIn, user: dict) -> dict:
    """Server-side price + description + the payload needed to fulfil after payment."""
    if body.kind == "ticket":
        ev = await db.events.find_one({"id": body.event_id}, {"_id": 0})
        if not ev:
            raise HTTPException(404, "Event not found")
        ev_date = ev["date"] if ev["date"].tzinfo else ev["date"].replace(tzinfo=timezone.utc)
        if ev_date < _now():
            raise HTTPException(400, "This event has already happened")
        require_level(user, ev.get("min_level", "bronze"))
        if await db.tickets.find_one({"event_id": ev["id"], "user_id": user["id"]}, {"_id": 1}):
            raise HTTPException(400, "You're already on the guest list — see your ticket in Profile")
        approved = await approved_request(ev["id"], user["id"])
        qty = approved["quantity"] if approved else body.quantity
        code = approved.get("promoter_code") if approved else body.promoter_code
        if not approved:
            if ev.get("approval_required"):
                raise HTTPException(409, "This event needs host approval — request to join")
            if qty > 1 + ev.get("plus_one_limit", 7):
                raise HTTPException(400, f"Max {1 + ev.get('plus_one_limit', 7)} tickets per guest")
            if ev.get("tickets_sold", 0) + qty > ev.get("capacity", 10**6):
                raise HTTPException(409, "Sold out — join the waitlist")
        _, _, total = ticket_price(ev, user, qty)
        return {"total": total, "label": f"{qty} × {ev['title']}", "venue_id": ev["venue_id"],
                "payload": {"event_id": ev["id"], "quantity": qty, "promoter_code": code,
                            "request_id": approved["id"] if approved else None}}
    if body.kind == "table":
        ev, table, fee = await quote_table(body.event_id or "", body.table_id or "", body.party_size, user)
        return {"total": round(table["min_spend"] + fee, 2), "label": f"Table {table['name']} · {ev['title']}",
                "venue_id": ev["venue_id"], "venue_share": table["min_spend"],
                "payload": {"event_id": ev["id"], "table_id": table["id"], "party_size": body.party_size}}
    if body.kind == "reservation":
        if not body.date or not body.service_type:
            raise HTTPException(400, "Pick a night and a service")
        res_in = ReservationIn(venue_id=body.venue_id or "", date=body.date, party_size=body.party_size,
                               service_type=body.service_type, base_price=0, notes=body.notes)
        venue, fee, total = await quote_reservation(res_in, user)
        return {"total": total, "label": f"{body.service_type.capitalize()} · {venue['name']}",
                "venue_id": venue["id"], "venue_share": res_in.base_price,
                "payload": res_in.model_dump(mode="json")}
    if body.kind == "boost":
        return await quote_boost(body.venue_id or "", body.plan or "", user)
    if body.kind == "spotlight":
        return await quote_spotlight(body.event_id or "", body.plan or "", user)
    if body.kind == "gift":
        return quote_gift(body.level, body.recipient_email, body.note)
    # membership: monthly subscription, auto-renews
    if body.level not in LEVEL_RANK:
        raise HTTPException(400, "Unknown level")
    if user["role"] in ("admin", "venue_owner"):
        raise HTTPException(400, "Business accounts already have full access")
    if body.level == "bronze" and user.get("membership_tier") == "free_girl":
        raise HTTPException(400, "Bronze is free for you — no payment needed")
    if body.interval == "year" and body.level not in YEARLY_PRICE:
        raise HTTPException(400, "Yearly billing is available for Gold")
    if (user.get("stripe_subscription_id") and user.get("subscription_level") == body.level
            and (user.get("subscription_interval") or "month") == body.interval
            and user.get("subscription_status") in ("active", "trialing")):
        raise HTTPException(400, "You're already on this plan")
    if body.interval == "year":
        price = YEARLY_PRICE[body.level]
        return {"total": price, "label": f"Nocturne {body.level.capitalize()} · ${price:,.0f}/year", "venue_id": None,
                "payload": {"level": body.level, "interval": "year"}, "no_credit": True, "subscription": True}
    price = LEVEL_PRICE[body.level]
    trial = trial_eligible(user, body.level)
    label = (f"Nocturne {body.level.capitalize()} · 7 days free, then ${price:.2f}/month" if trial
             else f"Nocturne {body.level.capitalize()} · ${price:.2f}/month")
    return {"total": 0.0 if trial else price, "label": label, "venue_id": None,
            "payload": {"level": body.level}, "no_credit": True, "subscription": True}


async def _fulfil(tx: dict, payment_session: Optional[str]) -> str:
    """Creates the ticket / booking / membership. Returns the created record id."""
    user = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
    p = tx["payload"]
    if tx["kind"] == "ticket":
        ev = await db.events.find_one({"id": p["event_id"]}, {"_id": 0})
        if await db.tickets.find_one({"event_id": ev["id"], "user_id": user["id"]}, {"_id": 1}):
            raise HTTPException(409, "You already had a ticket for this event")
        # approved guests always get their spot; everyone else is capacity-checked (no overselling)
        t = await issue_ticket(ev, user, p["quantity"], p.get("promoter_code"), override=bool(p.get("request_id")),
                               credit_used=tx["credit_used"], payment_session=payment_session)
        if p.get("request_id"):
            await db.event_requests.update_one({"id": p["request_id"]}, {"$set": {"ticket_issued": True}})
        return t.id
    if tx["kind"] == "table":
        return (await save_table(p["event_id"], p["table_id"], p["party_size"], user, payment_session)).id
    if tx["kind"] == "reservation":
        return (await save_reservation(ReservationIn(**p), user, payment_session)).id
    if tx["kind"] == "boost":
        return await apply_boost(tx)
    if tx["kind"] == "spotlight":
        return await apply_spotlight(tx)
    if tx["kind"] == "gift":
        return await create_gift(tx)
    return await activate_subscription(tx, payment_session)


async def _complete(session_id: str) -> None:
    """Idempotent: only the first caller (webhook or status poll) fulfils."""
    tx = await db.payment_transactions.find_one_and_update(
        {"session_id": session_id, "fulfilled": {"$ne": True}},
        {"$set": {"fulfilled": True, "payment_status": "paid", "status": "paid", "paid_at": _now()}},
    )
    if not tx:
        return
    try:
        rid = await _fulfil(tx, session_id)
        await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"result_id": rid}})
        if tx["kind"] in ("ticket", "table", "reservation"):
            from routes.notify import background, booking_email  # noqa: E402

            background(booking_email({**tx, "result_id": rid}, rid))
    except Exception as exc:
        # paid but could not be fulfilled (e.g. table taken meanwhile): return credit, flag card refund for admin
        detail = exc.detail if isinstance(exc, HTTPException) else "Booking could not be completed"
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "failed", "error": detail, "needs_refund": tx["amount"] > 0}})
        await _refund_credit(tx)
        return
    if tx["kind"] in ("ticket", "table", "reservation"):
        try:  # never let a bonus-points hiccup undo a confirmed booking
            from routes.engage import reward_referral  # noqa: E402

            await reward_referral(tx["user_id"])
        except Exception:
            logging.getLogger("payments").exception("referral reward failed for %s", tx["user_id"])


async def _close_open(tx: dict) -> None:
    """Closes an unpaid checkout (expires the Stripe session, returns reserved credit).
    If it turns out to be paid, it is fulfilled instead."""
    try:
        st = await retrieve_session(tx["session_id"])
        if session_paid(st):
            await _complete(tx["session_id"])
            return
        if g(st, "status") == "open":
            await call(stripe.checkout.Session.expire, tx["session_id"])
    except Exception:
        pass
    res = await db.payment_transactions.update_one(
        {"session_id": tx["session_id"], "fulfilled": False}, {"$set": {"status": "cancelled"}})
    if res.modified_count:
        await _refund_credit(tx)


@router.post("/payments/checkout", response_model=CheckoutOut)
async def create_checkout(body: CheckoutIn, user: UserDep):
    origin = body.origin_url.rstrip("/")
    if not origin.startswith(("https://", "http://")):
        raise HTTPException(400, "Invalid origin")
    if body.return_url and not body.return_url.startswith(APP_SCHEMES):
        raise HTTPException(400, "Invalid return link")
    q = await _quote(body, user)
    # one open checkout per item: close earlier unpaid attempts so nobody pays twice
    same = {f"payload.{k}": v for k, v in q["payload"].items()
            if k in ("event_id", "table_id", "venue_id", "date", "level")}
    async for old in db.payment_transactions.find(
            {"user_id": user["id"], "kind": body.kind, "status": "initiated", "fulfilled": False, **same}, {"_id": 0}):
        await _close_open(old)
    user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    total = q["total"]
    due = total if q.get("no_credit") else amount_due(total, user)
    credit = round(total - due, 2)
    if 0 < due < MIN_CHARGE:
        due = MIN_CHARGE
        credit = round(max(0.0, total - due), 2)
    if credit > 0:
        res = await db.users.update_one({"id": user["id"], "credit_balance": {"$gte": credit}},
                                        {"$inc": {"credit_balance": -credit}})
        if res.modified_count == 0:
            raise HTTPException(409, "Your credit changed — try again")
    tx = {"id": str(uuid.uuid4()), "user_id": user["id"], "kind": body.kind, "label": q["label"],
          "amount": due, "total": total, "credit_used": credit, "currency": "usd",
          "venue_id": q.get("venue_id"), "payload": q["payload"], "fulfilled": False, "created_at": _now()}
    if due <= 0 and not q.get("subscription"):
        # fully covered by reward credit — no card needed
        tx.update(session_id=f"credit_{tx['id']}", status="initiated", payment_status="credit")
        await db.payment_transactions.insert_one(tx)
        await _complete(tx["session_id"])
        done = await db.payment_transactions.find_one({"session_id": tx["session_id"]}, {"_id": 0})
        if done.get("status") == "failed":
            raise HTTPException(409, done.get("error") or "Could not complete booking")
        return CheckoutOut(amount=0, paid_with_credit=True, session_id=tx["session_id"], result_id=done.get("result_id"))

    if body.return_url:
        r = quote(body.return_url, safe="")
        success = f"{origin}/api/payments/done?session_id={{CHECKOUT_SESSION_ID}}&r={r}"
        cancel = f"{origin}/api/payments/done?cancelled=1&tx={tx['id']}&r={r}"
    else:
        success = f"{origin}/payment-result?session_id={{CHECKOUT_SESSION_ID}}"
        cancel = f"{origin}/payment-result?cancelled=1&tx={tx['id']}"
    if q.get("subscription"):
        params = subscription_params(user, q["payload"]["level"], q["payload"].get("interval", "month"))
    else:
        params = {"mode": "payment", "payment_method_types": ["card"], "line_items": [{
            "price_data": {"currency": "usd", "unit_amount": round(due * 100), "product_data": {"name": q["label"][:250]}},
            "quantity": 1,
        }], "customer_email": user["email"]}
    try:
        session = await create_session(
            origin, success_url=success, cancel_url=cancel,
            metadata={"tx_id": tx["id"], "user_id": user["id"], "kind": body.kind}, **params)
    except Exception:
        if credit > 0:
            await db.users.update_one({"id": user["id"]}, {"$inc": {"credit_balance": credit}})
        raise HTTPException(503, "Payments are unavailable right now — try again")
    tx.update(session_id=session.id, status="initiated", payment_status="unpaid", origin=origin)
    if origin.startswith("https://"):  # used for QR images in reminder emails
        await db.settings.update_one({"_id": "public_origin"}, {"$set": {"url": origin}}, upsert=True)
    await db.payment_transactions.insert_one(tx)
    return CheckoutOut(url=session.url, session_id=session.id, amount=due)


async def _refund_credit(tx: dict) -> None:
    if tx.get("credit_used", 0) > 0:
        res = await db.payment_transactions.update_one(
            {"session_id": tx["session_id"], "credit_refunded": {"$ne": True}}, {"$set": {"credit_refunded": True}})
        if res.modified_count:
            await db.users.update_one({"id": tx["user_id"]}, {"$inc": {"credit_balance": tx["credit_used"]}})


@router.get("/payments/status/{session_id}", response_model=PaymentStatusOut)
async def payment_status(session_id: str, user: UserDep):
    tx = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Payment not found")
    if not tx.get("fulfilled") and tx.get("status") not in ("expired", "cancelled") and not session_id.startswith("credit_"):
        try:
            st = await retrieve_session(session_id)
        except Exception:
            st = None
        if st and session_paid(st):
            await _complete(session_id)
        elif st and g(st, "status") == "expired":
            await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"status": "expired"}})
            await _refund_credit(tx)
        tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    status = tx.get("status", "initiated")
    return PaymentStatusOut(
        session_id=session_id, kind=tx["kind"], label=tx["label"], amount=tx["amount"],
        status={"initiated": "pending"}.get(status, status), result_id=tx.get("result_id"), error=tx.get("error"),
    )


@router.post("/payments/cancel/{session_id}")
async def cancel_payment(session_id: str, user: UserDep):
    """Called when the guest backs out of checkout — returns any reserved reward credit."""
    tx = await db.payment_transactions.find_one(
        {"$or": [{"session_id": session_id}, {"id": session_id}], "user_id": user["id"], "fulfilled": False}, {"_id": 0})
    if not tx:
        return {"ok": True}
    await _close_open(tx)
    return {"ok": True}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Never trusts the payload: every object is re-fetched from Stripe before acting."""
    try:
        ev = json.loads(await request.body())
        typ, obj = ev["type"], ev["data"]["object"]
    except Exception:
        raise HTTPException(400, "Invalid webhook")
    try:
        if typ.startswith("checkout.session."):
            if session_paid(await retrieve_session(obj["id"])):
                await _complete(obj["id"])
        elif typ.startswith("customer.subscription."):
            await sync_subscription_id(obj["id"])
        elif typ.startswith("invoice."):
            # older API versions: invoice.subscription; newer: invoice.parent.subscription_details.subscription
            sub_id = obj.get("subscription") or (((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
            if sub_id:
                await sync_subscription_id(sub_id)
            if typ == "invoice.paid" and OWN_KEY:
                from routes.notify import background, renewal_receipt  # noqa: E402

                inv = await call(stripe.Invoice.retrieve, obj["id"])  # trust Stripe, not the payload
                background(renewal_receipt(inv.to_dict() if hasattr(inv, "to_dict") else dict(inv)))
        elif typ == "account.updated":
            await sync_account_id(obj["id"])
    except stripe.StripeError:
        raise HTTPException(400, "Unknown Stripe object")
    return {"received": True}


@router.get("/payments/done", response_class=HTMLResponse, include_in_schema=False)
async def payment_done(r: str, session_id: Optional[str] = None, cancelled: Optional[str] = None, tx: Optional[str] = None):
    """Stripe returns here on phones; bounces back into the app."""
    if not r.startswith(APP_SCHEMES):
        raise HTTPException(400, "Invalid return link")
    sep = "&" if "?" in r else "?"
    target = f"{r}{sep}cancelled=1&tx={quote(tx or '')}" if cancelled else f"{r}{sep}session_id={quote(session_id or '')}"
    t = escape(target, quote=True)
    return HTMLResponse(
        f"<html><head><meta name=viewport content='width=device-width'><meta http-equiv=refresh content='0;url={t}'></head>"
        f"<body style='background:#09090b;color:#f4f4f5;font-family:sans-serif;text-align:center;padding-top:30vh'>"
        f"<p>{'Payment cancelled' if cancelled else 'Payment received'}</p><a style='color:#d4af37' href='{t}'>Return to Nocturne</a></body></html>"
    )


# ---------- Admin payouts (venues + promoters) ----------

class VenuePayout(BaseModel):
    venue_id: str
    venue_name: str
    owed: float
    items: int


class WithdrawalRow(BaseModel):
    id: str
    user_id: str
    user_name: str = ""
    amount: float
    fee: float
    net: float
    status: str = "paid"
    created_at: datetime


class PayoutsOut(BaseModel):
    card_payments_total: float
    venues_owed_total: float
    venues: List[VenuePayout]
    withdrawals: List[WithdrawalRow]
    refunds_needed: int


@router.get("/admin/payouts", response_model=PayoutsOut)
async def admin_payouts(_: AdminDep):
    rows = await db.venue_payables.aggregate([
        {"$match": {"status": "owed"}},
        {"$group": {"_id": "$venue_id", "name": {"$first": "$venue_name"}, "owed": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        {"$sort": {"owed": -1}},
    ]).to_list(200)
    paid = await db.payment_transactions.aggregate([
        {"$match": {"payment_status": "paid"}}, {"$group": {"_id": None, "s": {"$sum": "$amount"}}},
    ]).to_list(1)
    wds = [WithdrawalRow(**w) async for w in db.withdrawals.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1)]
    return PayoutsOut(
        card_payments_total=round(paid[0]["s"], 2) if paid else 0.0,
        venues_owed_total=round(sum(r["owed"] for r in rows), 2),
        venues=[VenuePayout(venue_id=r["_id"], venue_name=r["name"], owed=round(r["owed"], 2), items=r["n"]) for r in rows],
        withdrawals=wds,
        refunds_needed=await db.payment_transactions.count_documents({"needs_refund": True}),
    )


@router.post("/admin/payouts/venues/{venue_id}/settle")
async def settle_venue(venue_id: str, _: AdminDep):
    """Pays the venue owner through Stripe Connect when they've linked a bank, otherwise just marks it paid."""
    rows = [r async for r in db.venue_payables.find({"venue_id": venue_id, "status": "owed"}, {"_id": 0, "id": 1, "amount": 1})]
    if not rows:
        return {"settled": 0, "transfer_id": None}
    ids = [r["id"] for r in rows]
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0, "owner_id": 1})
    try:
        tid = await send_transfer((venue or {}).get("owner_id", ""), sum(r["amount"] for r in rows), "venue", ids[0])
    except stripe.StripeError as exc:
        raise HTTPException(503, g(exc, "user_message") or "Stripe transfer failed — check your Stripe balance")
    res = await db.venue_payables.update_many({"id": {"$in": ids}, "status": "owed"},
                                              {"$set": {"status": "paid", "paid_at": _now(), "transfer_id": tid}})
    from routes.notify import background, payout_email  # noqa: E402

    background(payout_email(venue_id, ids, tid))
    return {"settled": res.modified_count, "transfer_id": tid}


@router.post("/admin/withdrawals/{wid}/paid")
async def mark_withdrawal_paid(wid: str, _: AdminDep):
    res = await db.withdrawals.update_one({"id": wid, "status": "pending"}, {"$set": {"status": "paid", "paid_at": _now()}})
    if res.modified_count == 0:
        raise HTTPException(404, "Withdrawal not found or already paid")
    return {"ok": True}


@router.get("/host/payouts")
async def host_payouts(user: Annotated[dict, Depends(require_roles("venue_owner", "admin"))]):
    """What Nocturne owes this owner's venues, and what has already been paid out."""
    ids = [v["id"] async for v in db.venues.find({"owner_id": user["id"]}, {"id": 1})]
    out = {"owed": 0.0, "paid": 0.0}
    async for r in db.venue_payables.aggregate([
        {"$match": {"venue_id": {"$in": ids}}}, {"$group": {"_id": "$status", "s": {"$sum": "$amount"}}},
    ]):
        out[r["_id"]] = round(r["s"], 2)
    return out
