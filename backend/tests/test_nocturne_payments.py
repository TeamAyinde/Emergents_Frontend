"""Nocturne iteration 7: Stripe Checkout (tickets/tables/reservations/membership), credit path, cancel/refund,
402 on direct paid endpoints, host approval -> pay, Google session 401, admin payouts / withdrawals, /payments/done.
Uses only TEST_ users created here; all created data removed by id at module teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ORIGIN = BASE_URL
ADMIN = ("admin@nocturne.app", "AdminPass123!")
VENUE = ("venue@nocturne.app", "VenuePass123!")
GUEST = ("guest@nocturne.app", "GuestPass123!")
PROMOTER_EMAIL = "promoter@nocturne.app"

C = {"users": [], "sessions": [], "tickets": [], "requests": [], "withdrawals": []}
EV_SOLD = {}
PROMO_WALLET = {"delta": 0.0}
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {creds[0]}")
    return r.json()["access_token"]


def register(role="guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": "TEST_ Payments", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": ORIGIN, **body}, headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].append(r.json()["session_id"])
    return r


def ev(title):
    for e in requests.get(f"{API}/events").json():
        if e["title"] == title:
            return e
    pytest.skip(f"event {title} missing")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for s in C["sessions"]:
        tx = DB.payment_transactions.find_one({"session_id": s})
        if tx and tx.get("result_id"):
            DB.venue_payables.delete_many({"record_id": tx["result_id"]})
            DB.tickets.delete_one({"id": tx["result_id"]})
            DB.table_bookings.delete_one({"id": tx["result_id"]})
            DB.reservations.delete_one({"id": tx["result_id"]})
        DB.payment_transactions.delete_one({"session_id": s})
    for eid, q in EV_SOLD.items():
        DB.events.update_one({"id": eid}, {"$inc": {"tickets_sold": -q}})
    for r in C["requests"]:
        DB.event_requests.delete_one({"id": r})
    for w in C["withdrawals"]:
        DB.withdrawals.delete_one({"id": w})
    if PROMO_WALLET["delta"]:
        DB.users.update_one({"email": PROMOTER_EMAIL}, {"$inc": {"wallet_balance": -PROMO_WALLET["delta"]}})
    for uid in C["users"]:
        DB.points_ledger.delete_many({"user_id": uid})
        DB.membership_payments.delete_many({"user_id": uid})
        tids = [t["id"] for t in DB.tickets.find({"user_id": uid}, {"id": 1})]
        DB.venue_payables.delete_many({"record_id": {"$in": tids}})
        DB.tickets.delete_many({"user_id": uid})
        DB.users.delete_one({"id": uid})


# ---- Checkout creation + server-side pricing ----
class TestCheckout:
    def test_ticket_checkout_stripe_url_and_price(self):
        tok, _ = register()
        e = ev("Velvet Sessions w/ DJ Nyx")
        r = checkout(tok, kind="ticket", event_id=e["id"], quantity=2, promoter_code="MARCO1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("https://checkout.stripe.com"), d
        assert d["session_id"].startswith("cs_") and d["amount"] == round(e["price"] * 2 * 1.15, 2)
        st = requests.get(f"{API}/payments/status/{d['session_id']}", headers=h(tok))
        assert st.status_code == 200 and st.json()["status"] == "pending", st.text
        other, _ = register()
        assert requests.get(f"{API}/payments/status/{d['session_id']}", headers=h(other)).status_code == 404

    def test_return_url_and_origin_validation(self):
        tok, _ = register()
        e = ev("Velvet Sessions w/ DJ Nyx")
        assert checkout(tok, kind="ticket", event_id=e["id"], return_url="exp://192.168.1.2/--/payment-result").status_code == 200
        assert checkout(tok, kind="ticket", event_id=e["id"], return_url="https://evil.com").status_code == 400
        r = requests.post(f"{API}/payments/checkout", json={"kind": "ticket", "event_id": e["id"], "origin_url": "javascript:x"}, headers=h(tok))
        assert r.status_code == 400

    def test_ticket_validation(self):
        tok, _ = register()
        assert checkout(tok, kind="ticket", event_id=ev("Industry Fridays")["id"]).status_code == 409  # approval
        assert checkout(tok, kind="ticket", event_id=ev("Cinematic Supper Series")["id"]).status_code == 403  # silver
        assert checkout(tok, kind="ticket", event_id="nope").status_code == 404
        assert checkout(tok, kind="ticket", event_id=ev("Rooftop Reverie")["id"], quantity=3).status_code == 409  # cap 2

    def test_membership_checkout_and_rules(self):
        tok, _ = register()
        r = checkout(tok, kind="membership", level="silver")
        assert r.status_code == 200 and r.json()["amount"] == 49.0 and "checkout.stripe.com" in r.json()["url"]
        assert checkout(tok, kind="membership", level="platinum").status_code == 400
        vtok = login(VENUE)
        assert checkout(vtok, kind="membership", level="gold").status_code == 400

    def test_table_and_reservation_checkout(self):
        tok, u = register()
        DB.users.update_one({"id": u["id"]}, {"$set": {"level": "silver"}})
        e = ev("Midnight Gold — Grand Opening")
        r = checkout(tok, kind="table", event_id=e["id"], table_id="T1", party_size=4)
        assert r.status_code == 200, r.text
        assert r.json()["amount"] == 480.0  # 400 min spend + 20% silver fee
        assert checkout(tok, kind="table", event_id=e["id"], table_id="V1", party_size=2).status_code == 403
        assert checkout(tok, kind="table", event_id=e["id"], table_id="T1", party_size=9).status_code == 400
        vid = next(v["id"] for v in requests.get(f"{API}/venues").json() if v.get("min_level", "bronze") == "bronze")
        r = checkout(tok, kind="reservation", venue_id=vid, date=future(), party_size=2, service_type="table")
        assert r.status_code == 200, r.text
        assert r.json()["amount"] == 240.0  # 200 + 20%
        assert checkout(tok, kind="reservation", venue_id=vid, party_size=2, service_type="table").status_code == 400
        assert checkout(tok, kind="reservation", venue_id=vid, date=future(), party_size=2, service_type="x").status_code == 400


# ---- Credit path: fully paid with reward credit -> fulfilment end-to-end ----
class TestCreditPath:
    def test_credit_ticket_fulfilment(self):
        tok, u = register()
        DB.users.update_one({"id": u["id"]}, {"$set": {"credit_balance": 1000.0}})
        promo_before = DB.users.find_one({"email": PROMOTER_EMAIL})["wallet_balance"]
        e = ev("Velvet Sessions w/ DJ Nyx")
        r = checkout(tok, kind="ticket", event_id=e["id"], quantity=2, promoter_code="MARCO1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["paid_with_credit"] is True and d["amount"] == 0 and d["result_id"]
        EV_SOLD[e["id"]] = EV_SOLD.get(e["id"], 0) + 2
        tickets = requests.get(f"{API}/tickets/mine", headers=h(tok)).json()
        t = next(t for t in tickets if t["id"] == d["result_id"])
        assert t["quantity"] == 2 and t["credit_used"] == 184.0 and t["total_paid"] == 0
        assert DB.users.find_one({"id": u["id"]})["credit_balance"] == 816.0
        pay = DB.venue_payables.find_one({"record_id": d["result_id"]})
        assert pay and pay["amount"] == 160.0 and pay["status"] == "owed" and pay["venue_id"] == e["venue_id"]
        promo_after = DB.users.find_one({"email": PROMOTER_EMAIL})["wallet_balance"]
        PROMO_WALLET["delta"] += round(promo_after - promo_before, 2)
        assert round(promo_after - promo_before, 2) == round(24 * 0.4, 2)
        st = requests.get(f"{API}/payments/status/{d['session_id']}", headers=h(tok)).json()
        assert st["status"] == "paid" and st["result_id"] == d["result_id"]
        assert checkout(tok, kind="ticket", event_id=e["id"]).status_code == 400  # already has ticket

    def test_partial_credit_then_cancel_refunds(self):
        tok, u = register()
        DB.users.update_one({"id": u["id"]}, {"$set": {"credit_balance": 10.0}})
        e = ev("Velvet Sessions w/ DJ Nyx")
        r = checkout(tok, kind="ticket", event_id=e["id"])
        assert r.status_code == 200 and r.json()["amount"] == 82.0, r.text
        assert DB.users.find_one({"id": u["id"]})["credit_balance"] == 0
        tx = DB.payment_transactions.find_one({"session_id": r.json()["session_id"]})
        assert requests.post(f"{API}/payments/cancel/{tx['id']}", headers=h(tok)).status_code == 200
        assert DB.users.find_one({"id": u["id"]})["credit_balance"] == 10.0
        # second cancel must not double-refund
        requests.post(f"{API}/payments/cancel/{r.json()['session_id']}", headers=h(tok))
        assert DB.users.find_one({"id": u["id"]})["credit_balance"] == 10.0
        st = requests.get(f"{API}/payments/status/{r.json()['session_id']}", headers=h(tok)).json()
        assert st["status"] == "cancelled"


# ---- Direct endpoints now demand payment ----
class TestDirect402:
    def test_direct_paid_endpoints_402(self):
        tok, u = register()
        e = ev("Velvet Sessions w/ DJ Nyx")
        assert requests.post(f"{API}/tickets/purchase", json={"event_id": e["id"], "quantity": 1}, headers=h(tok)).status_code == 402
        vid = next(v["id"] for v in requests.get(f"{API}/venues").json() if v.get("min_level", "bronze") == "bronze")
        assert requests.post(f"{API}/reservations", json={"venue_id": vid, "date": future(), "party_size": 2, "service_type": "table"},
                             headers=h(tok)).status_code == 402
        assert requests.post(f"{API}/membership/upgrade", json={"level": "silver"}, headers=h(tok)).status_code == 402
        j = requests.post(f"{API}/events/{e['id']}/join", json={"quantity": 1}, headers=h(tok))
        assert j.status_code == 200 and j.json()["result"] == "payment_required", j.text
        DB.users.update_one({"id": u["id"]}, {"$set": {"level": "silver"}})
        mg = ev("Midnight Gold — Grand Opening")
        assert requests.post(f"{API}/events/{mg['id']}/tables/T2/book", json={"party_size": 2}, headers=h(tok)).status_code == 402
        # iteration 10: Bronze is a paid monthly plan for 'member' tier, so a direct switch needs checkout (402)
        r = requests.post(f"{API}/membership/upgrade", json={"level": "bronze"}, headers=h(tok))
        assert r.status_code == 402, r.text


# ---- Host approval no longer issues ticket for paid event ----
class TestApprovalThenPay:
    def test_approve_then_checkout_uses_request_qty(self):
        tok, u = register()
        e = ev("Industry Fridays")
        j = requests.post(f"{API}/events/{e['id']}/join", json={"quantity": 2}, headers=h(tok))
        if (j.json() or {}).get("request"):
            C["requests"].append(j.json()["request"]["id"])
        assert j.status_code == 200 and j.json()["result"] == "pending", j.text
        rid = j.json()["request"]["id"]
        C["requests"].append(rid)
        a = requests.post(f"{API}/host/requests/{rid}", json={"action": "approve"}, headers=h(login(VENUE)))
        assert a.status_code == 200 and a.json()["status"] == "approved", a.text
        assert DB.tickets.find_one({"user_id": u["id"], "event_id": e["id"]}) is None
        r = checkout(tok, kind="ticket", event_id=e["id"], quantity=1)
        assert r.status_code == 200, r.text
        assert r.json()["amount"] == round(e["price"] * 2 * 1.15, 2)


# ---- Auth ----
class TestAuth:
    def test_google_bogus_session_401_and_password_login(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "bogus_123"})
        assert r.status_code == 401
        assert login(GUEST)


# ---- Admin payouts / withdrawals / host payouts ----
class TestPayouts:
    def test_withdraw_pending_admin_queue_mark_paid(self):
        ptok, pu = register("promoter")
        DB.users.update_one({"id": pu["id"]}, {"$set": {"wallet_balance": 50.0}})
        r = requests.post(f"{API}/promoter/withdraw", json={"amount": 20}, headers=h(ptok))
        assert r.status_code == 200 and r.json()["status"] == "pending", r.text
        w = DB.withdrawals.find_one({"user_id": pu["id"]})
        C["withdrawals"].append(w["id"])
        atok = login(ADMIN)
        p = requests.get(f"{API}/admin/payouts", headers=h(atok))
        assert p.status_code == 200, p.text
        d = p.json()
        assert {"card_payments_total", "venues_owed_total", "venues", "withdrawals", "refunds_needed"} <= d.keys()
        assert any(x["id"] == w["id"] and x["status"] == "pending" for x in d["withdrawals"])
        assert requests.post(f"{API}/admin/withdrawals/{w['id']}/paid", headers=h(atok)).status_code == 200
        assert requests.post(f"{API}/admin/withdrawals/{w['id']}/paid", headers=h(atok)).status_code == 404
        assert DB.withdrawals.find_one({"id": w["id"]})["status"] == "paid"
        assert requests.get(f"{API}/admin/payouts", headers=h(ptok)).status_code == 403

    def test_venue_settle_and_host_payouts(self):
        tok, u = register()
        DB.users.update_one({"id": u["id"]}, {"$set": {"credit_balance": 500.0}})
        e = ev("Industry Fridays")  # The Ember Room — owned by venue@nocturne.app
        j = requests.post(f"{API}/events/{e['id']}/join", json={"quantity": 1}, headers=h(tok))
        rid = j.json()["request"]["id"]
        C["requests"].append(rid)
        vtok = login(VENUE)
        requests.post(f"{API}/host/requests/{rid}", json={"action": "approve"}, headers=h(vtok))
        before = requests.get(f"{API}/host/payouts", headers=h(vtok)).json()
        # credit covers -> approve issues ticket directly (no money due)
        t = DB.tickets.find_one({"user_id": u["id"], "event_id": e["id"]})
        if t:
            C["tickets"].append(t["id"])
            EV_SOLD[e["id"]] = EV_SOLD.get(e["id"], 0) + 1
        atok = login(ADMIN)
        venues = requests.get(f"{API}/admin/payouts", headers=h(atok)).json()["venues"]
        print("host payouts", before, "admin venues", venues)
        assert set(before.keys()) >= {"owed", "paid"}
        s = requests.post(f"{API}/admin/payouts/venues/{e['venue_id']}/settle", headers=h(atok))
        assert s.status_code == 200 and "settled" in s.json()
        assert requests.get(f"{API}/host/payouts", headers=h(tok)).status_code == 403


# ---- Native return bounce page ----
class TestDone:
    def test_done_redirect_and_invalid(self):
        r = requests.get(f"{API}/payments/done", params={"r": "exp://x", "session_id": "cs_1"})
        assert r.status_code == 200 and "exp://x?session_id=cs_1" in r.text and "refresh" in r.text
        assert requests.get(f"{API}/payments/done", params={"r": "https://evil"}).status_code == 400
        c = requests.get(f"{API}/payments/done", params={"r": "exp://x", "cancelled": "1", "tx": "abc"})
        assert "cancelled=1" in c.text
