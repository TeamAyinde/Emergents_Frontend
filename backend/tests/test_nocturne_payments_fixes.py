"""Iteration 8 retest of iteration-7 payment fixes: cent rounding sent to Stripe, venue_payables on every
fulfilment path (no double recording), closing earlier unpaid attempts, _fulfil duplicate/capacity guards,
_complete exception handling + credit refund, /payments/cancel by session or tx id.
Uses only TEST_ users created here; everything created is removed by id at module teardown."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import certifi
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import run

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
VENUE = ("venue@nocturne.app", "VenuePass123!")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "sessions": set(), "tickets": [], "tables": [], "res": [], "requests": [], "events": []}


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def register(credit=0.0, level=None):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Fixes", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    uid = d["user"]["id"]
    C["users"].append(uid)
    upd = {"credit_balance": credit}
    if level:
        now = datetime.now(timezone.utc)
        upd.update(level=level, level_since=now, level_paid_until=now + timedelta(days=30))
    DB.users.update_one({"id": uid}, {"$set": upd})
    return d["access_token"], uid


def credit(uid):
    return round(DB.users.find_one({"id": uid})["credit_balance"], 2)


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].add(r.json()["session_id"])
    return r


def track_ticket(tid):
    C["tickets"].append(tid)


def payables(record_id):
    return list(DB.venue_payables.find({"record_id": record_id}, {"_id": 0}))


EV_OPEN = "fc35bae2"  # Velvet Sessions (bronze, $80, no approval)
EV_APPROVAL = "9ea11287"  # Industry Fridays (approval required, $40, owned by venue@)


def full_id(prefix):
    return DB.events.find_one({"id": {"$regex": f"^{prefix}"}})["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for tid in C["tickets"]:
        t = DB.tickets.find_one({"id": tid})
        if t:
            DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
            DB.tickets.delete_one({"id": tid})
        DB.venue_payables.delete_many({"record_id": tid})
    for bid in C["tables"]:
        DB.table_bookings.delete_one({"id": bid})
        DB.venue_payables.delete_many({"record_id": bid})
    for rid in C["res"]:
        DB.reservations.delete_one({"id": rid})
        DB.venue_payables.delete_many({"record_id": rid})
    for rid in C["requests"]:
        DB.event_requests.delete_one({"id": rid})
    for eid in C["events"]:
        DB.events.delete_one({"id": eid})
    for s in C["sessions"]:
        DB.payment_transactions.delete_one({"session_id": s})
    for uid in C["users"]:
        DB.payment_transactions.delete_many({"user_id": uid})
        DB.points_ledger.delete_many({"user_id": uid})
        DB.users.delete_one({"id": uid})


# --- cent rounding: $36.80 must reach Stripe as 3680 cents
def test_cent_rounding_sent_to_stripe():
    sys.path.insert(0, "/app/backend")
    import stripe
    # same config as stripe_core: own sk_/rk_ key, else the Emergent test proxy (env key may be a pk_ key)
    raw = (os.environ.get("STRIPE_API_KEY") or "").strip()
    own = raw.startswith(("sk_", "rk_")) and "emergent" not in raw
    stripe.api_key = raw if own else "sk_test_emergent"
    if not own:
        stripe.api_base = "https://integrations.emergentagent.com/stripe"
    stripe.ca_bundle_path = certifi.where()
    tok, uid = register(credit=round(92.00 - 36.80, 2))
    r = checkout(tok, kind="ticket", event_id=full_id(EV_OPEN))
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 36.80
    st = stripe.checkout.Session.retrieve(r.json()["session_id"])
    assert st.amount_total == 3680, st.amount_total
    requests.post(f"{API}/payments/cancel/{r.json()['session_id']}", headers=h(tok))
    assert credit(uid) == 55.20


# --- venue payable on credit-covered direct purchase
def test_payable_direct_purchase_credit():
    tok, _ = register(credit=100)
    r = requests.post(f"{API}/tickets/purchase", json={"event_id": full_id(EV_OPEN), "quantity": 1}, headers=h(tok))
    assert r.status_code == 201, r.text
    t = r.json()
    track_ticket(t["id"])
    p = payables(t["id"])
    assert len(p) == 1 and p[0]["amount"] == 80.0 and p[0]["source"] == "ticket" and p[0]["status"] == "owed"


# --- venue payable on credit-covered /events/{id}/join
def test_payable_join_credit():
    tok, _ = register(credit=100)
    r = requests.post(f"{API}/events/{full_id(EV_OPEN)}/join", json={"quantity": 1}, headers=h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "ticket", r.json()
    tid = r.json()["ticket"]["id"]
    track_ticket(tid)
    assert len(payables(tid)) == 1


# --- venue payable on host approval covered by credit
def test_payable_host_approval_credit():
    eid = full_id(EV_APPROVAL)
    tok, uid = register(credit=100)
    r = requests.post(f"{API}/events/{eid}/join", json={"quantity": 1, "note": "TEST_"}, headers=h(tok))
    assert r.status_code == 200 and r.json()["result"] == "pending", r.text
    rid = r.json()["request"]["id"]
    C["requests"].append(rid)
    vt = requests.post(f"{API}/auth/login", json={"email": VENUE[0], "password": VENUE[1]}).json()["access_token"]
    r = requests.post(f"{API}/host/requests/{rid}", json={"action": "approve"}, headers=h(vt))
    assert r.status_code == 200, r.text
    t = DB.tickets.find_one({"event_id": eid, "user_id": uid})
    assert t, "ticket not issued on approval although credit covers it"
    track_ticket(t["id"])
    p = payables(t["id"])
    assert len(p) == 1 and p[0]["amount"] == 40.0
    assert credit(uid) == 54.0


# --- credit-only checkout: ticket, table, reservation each record exactly one payable
def test_payable_checkout_credit_paths_not_doubled():
    tok, uid = register(credit=2000, level="silver")
    r = checkout(tok, kind="ticket", event_id=full_id(EV_OPEN))
    assert r.status_code == 200 and r.json()["paid_with_credit"], r.text
    track_ticket(r.json()["result_id"])
    assert len(payables(r.json()["result_id"])) == 1
    eid = full_id(EV_OPEN)
    tables = requests.get(f"{API}/events/{eid}/tables", headers=h(tok)).json()
    free = [t for t in tables if not t.get("booked") and t["min_level"] in ("bronze", "silver")]
    assert free, tables
    r = checkout(tok, kind="table", event_id=eid, table_id=free[0]["id"], party_size=2)
    assert r.status_code == 200 and r.json()["paid_with_credit"], r.text
    C["tables"].append(r.json()["result_id"])
    p = payables(r.json()["result_id"])
    assert len(p) == 1 and p[0]["amount"] == free[0]["min_spend"] and p[0]["source"] == "table"
    vid = DB.venues.find_one({"min_level": {"$in": ["bronze", "silver", None]}})["id"]
    r = checkout(tok, kind="reservation", venue_id=vid, service_type="table", party_size=2,
                 date=(datetime.now(timezone.utc) + timedelta(days=9)).isoformat())
    assert r.status_code == 200 and r.json()["paid_with_credit"], r.text
    C["res"].append(r.json()["result_id"])
    p = payables(r.json()["result_id"])
    assert len(p) == 1 and p[0]["amount"] == 200.0 and p[0]["source"] == "reservation"


# --- new checkout for same item closes earlier unpaid attempt, credit refunded once; cancel by tx id works
def test_new_checkout_closes_previous_and_cancel_by_tx_id():
    tok, uid = register(credit=10)
    eid = full_id(EV_OPEN)
    r1 = checkout(tok, kind="ticket", event_id=eid)
    assert r1.status_code == 200 and r1.json()["amount"] == 82.0, r1.text
    assert credit(uid) == 0.0
    r2 = checkout(tok, kind="ticket", event_id=eid)
    assert r2.status_code == 200, r2.text
    tx1 = DB.payment_transactions.find_one({"session_id": r1.json()["session_id"]})
    assert tx1["status"] == "cancelled" and tx1.get("credit_refunded") is True
    assert credit(uid) == 0.0  # refunded 10 then re-reserved 10 for attempt 2
    # repeat cancel of attempt 1 must not refund again
    requests.post(f"{API}/payments/cancel/{r1.json()['session_id']}", headers=h(tok))
    assert credit(uid) == 0.0
    tx2 = DB.payment_transactions.find_one({"session_id": r2.json()["session_id"]})
    r = requests.post(f"{API}/payments/cancel/{tx2['id']}", headers=h(tok))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert credit(uid) == 10.0
    assert DB.payment_transactions.find_one({"id": tx2["id"]})["status"] == "cancelled"
    requests.post(f"{API}/payments/cancel/{tx2['id']}", headers=h(tok))
    assert credit(uid) == 10.0
    st = requests.get(f"{API}/payments/status/{r2.json()['session_id']}", headers=h(tok)).json()
    assert st["status"] == "cancelled"


# --- method level: _fulfil / _complete guards (in-process, against the same DB)
def _payments():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401  (import order mirrors uvicorn: server -> extras/features/payments)
    from routes import payments
    return payments


def _fake_tx(uid, kind, payload, amount=46.0, credit_used=5.0):
    sid = f"credit_TEST_{uuid.uuid4().hex[:10]}"
    C["sessions"].add(sid)
    DB.payment_transactions.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "kind": kind, "label": "TEST_", "amount": amount, "total": amount + credit_used,
        "credit_used": credit_used, "currency": "usd", "venue_id": None, "payload": payload, "fulfilled": False,
        "session_id": sid, "status": "initiated", "created_at": datetime.now(timezone.utc)})
    return sid


def test_fulfil_existing_ticket_needs_refund():
    p = _payments()
    tok, uid = register(credit=100)
    eid = full_id(EV_OPEN)
    r = requests.post(f"{API}/tickets/purchase", json={"event_id": eid, "quantity": 1}, headers=h(tok))
    assert r.status_code == 201
    track_ticket(r.json()["id"])
    before = credit(uid)
    sid = _fake_tx(uid, "ticket", {"event_id": eid, "quantity": 1, "promoter_code": None, "request_id": None})
    run(p._complete(sid))
    tx = DB.payment_transactions.find_one({"session_id": sid})
    assert tx["status"] == "failed" and tx["needs_refund"] is True and "already" in tx["error"].lower()
    assert credit(uid) == round(before + 5.0, 2)
    assert DB.tickets.count_documents({"event_id": eid, "user_id": uid}) == 1


def test_fulfil_capacity_enforced_unless_approved():
    p = _payments()
    _, uid = register()
    src = DB.events.find_one({"id": full_id(EV_OPEN)}, {"_id": 0})
    ev = {**src, "id": f"TEST_{uuid.uuid4().hex[:8]}", "title": "TEST_ cap", "capacity": 1, "tickets_sold": 1}
    DB.events.insert_one(ev)
    C["events"].append(ev["id"])
    sid = _fake_tx(uid, "ticket", {"event_id": ev["id"], "quantity": 1, "promoter_code": None, "request_id": None})
    run(p._complete(sid))
    tx = DB.payment_transactions.find_one({"session_id": sid})
    assert tx["status"] == "failed" and "sold out" in tx["error"].lower()
    assert credit(uid) == 5.0
    # approved request overrides capacity
    sid2 = _fake_tx(uid, "ticket", {"event_id": ev["id"], "quantity": 1, "promoter_code": None, "request_id": "TEST_req"})
    run(p._complete(sid2))
    tx2 = DB.payment_transactions.find_one({"session_id": sid2})
    assert tx2["status"] == "paid" and tx2.get("result_id"), tx2
    track_ticket(tx2["result_id"])
    assert len(payables(tx2["result_id"])) == 1


def test_complete_catches_generic_exception():
    p = _payments()
    _, uid = register()
    sid = _fake_tx(uid, "table", {"bogus": True})  # KeyError inside _fulfil
    run(p._complete(sid))
    tx = DB.payment_transactions.find_one({"session_id": sid})
    assert tx["status"] == "failed" and tx["error"] == "Booking could not be completed" and tx["needs_refund"]
    assert credit(uid) == 5.0
    run(p._complete(sid))  # idempotent
    assert credit(uid) == 5.0


def test_cancel_unknown_and_status_unknown():
    tok, _ = register()
    r = requests.post(f"{API}/payments/cancel/cs_test_unknown_{uuid.uuid4().hex[:6]}", headers=h(tok))
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = requests.get(f"{API}/payments/status/cs_test_unknown", headers=h(tok))
    assert r.status_code == 404 and r.json()["detail"] == "Payment not found"


# --- credit-only checkout whose fulfilment fails -> 409 and credit refunded (in-process, _fulfil forced to fail)
def test_credit_only_checkout_failure_refunds_and_409(monkeypatch):
    p = _payments()
    from fastapi import HTTPException
    _, uid = register(credit=100)

    async def boom(tx, sid):
        raise HTTPException(409, "TEST_ table just taken")
    monkeypatch.setattr(p, "_fulfil", boom)
    user = DB.users.find_one({"id": uid}, {"_id": 0})
    with pytest.raises(HTTPException) as e:
        run(p.create_checkout(p.CheckoutIn(kind="ticket", origin_url=BASE_URL, event_id=full_id(EV_OPEN)), user))
    assert e.value.status_code == 409 and e.value.detail == "TEST_ table just taken"
    assert credit(uid) == 100.0
    tx = DB.payment_transactions.find_one({"user_id": uid})
    assert tx["status"] == "failed" and tx["needs_refund"] is False and tx["credit_refunded"] is True
