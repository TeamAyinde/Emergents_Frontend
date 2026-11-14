"""Nocturne iteration 6: reward points (earn/multipliers/redeem), ticket credit auto-apply, members perks wallet.
Uses only TEST_ users created here; all created data removed by id at module teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import grant_credit, set_level, simulate_paid

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("admin@nocturne.app", "AdminPass123!")

C = {"users": [], "sessions": [], "tickets": [], "reservations": [], "partner_bookings": [], "table_bookings": [], "requests": []}
EV_SOLD = {}
S = {}


def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def register():
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!",
        "full_name": "TEST_ Rewards", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def me(tok):
    return requests.get(f"{API}/auth/me", headers=h(tok)).json()


def rewards(tok):
    return requests.get(f"{API}/rewards", headers=h(tok)).json()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    d = db()
    for t in C["tickets"]:
        d.tickets.delete_one({"id": t})
    for eid, q in EV_SOLD.items():
        d.events.update_one({"id": eid}, {"$inc": {"tickets_sold": -q}})
    for r in C["reservations"]:
        d.reservations.delete_one({"id": r})
    for b in C["partner_bookings"]:
        d.partner_bookings.delete_one({"id": b})
    for b in C["table_bookings"]:
        d.table_bookings.delete_one({"id": b})
    for r in C["requests"]:
        d.event_requests.delete_one({"id": r})
    d.venue_payables.delete_many({"record_id": {"$in": C["tickets"] + C["reservations"] + C["table_bookings"]}})
    d.payment_transactions.delete_many({"$or": [{"session_id": {"$in": C["sessions"]}}, {"user_id": {"$in": C["users"]}}]})
    for uid in C["users"]:
        d.points_ledger.delete_many({"user_id": uid})
        d.perk_claims.delete_many({"user_id": uid})
        d.membership_payments.delete_many({"user_id": uid})
        d.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def ev():
    now = datetime.now(timezone.utc).isoformat()
    for e in requests.get(f"{API}/events").json():
        if (e.get("min_level", "bronze") == "bronze" and not e.get("approval_required") and e["price"] > 0
                and e["date"] > now and e.get("capacity", 10**6) - e.get("tickets_sold", 0) >= 4):
            return e
    pytest.skip("no bookable bronze event")


def pay(tok, **body):
    """Checkout -> (simulated) card payment -> fulfilled record id. Reward credit is applied by checkout."""
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    assert r.status_code == 200, r.text
    C["sessions"].append(r.json()["session_id"])
    if r.json()["paid_with_credit"]:
        return r.json()["result_id"]
    tx = simulate_paid(r.json()["session_id"])
    assert tx["status"] == "paid" and tx.get("result_id"), tx
    return tx["result_id"]


def buy(tok, eid, qty=1):
    assert requests.post(f"{API}/events/{eid}/join", json={"quantity": qty}, headers=h(tok)).json()["result"] == "payment_required"
    tid = pay(tok, kind="ticket", event_id=eid, quantity=qty)
    C["tickets"].append(tid)
    EV_SOLD[eid] = EV_SOLD.get(eid, 0) + qty
    return next(t for t in requests.get(f"{API}/tickets/mine", headers=h(tok)).json() if t["id"] == tid)


# Rewards GET shape + /auth/me fields for new user
def test_rewards_initial():
    tok, _ = register()
    S["tok"] = tok
    r = requests.get(f"{API}/rewards", headers=h(tok))
    assert r.status_code == 200
    d = r.json()
    assert d["points"] == 0 and d["credit_balance"] == 0 and d["multiplier"] == 1.0
    assert d["points_per_dollar_credit"] == 20 and d["history"] == []
    m = me(tok)
    assert m["points"] == 0 and m["credit_balance"] == 0
    assert requests.get(f"{API}/rewards").status_code in (401, 403)


# Redeem validation errors
def test_redeem_errors():
    tok = S["tok"]
    r = requests.post(f"{API}/rewards/redeem", json={"points": 150}, headers=h(tok))
    assert r.status_code == 400 and "100" in r.json()["detail"]
    r = requests.post(f"{API}/rewards/redeem", json={"points": 100}, headers=h(tok))
    assert r.status_code == 400 and r.json()["detail"] == "Not enough points"
    r = requests.post(f"{API}/rewards/redeem", json={"points": 50}, headers=h(tok))
    assert r.status_code == 422


# Points on join ticket (bronze 1x)
def test_points_ticket_bronze(ev):
    tok = S["tok"]
    t = buy(tok, ev["id"])
    expected = int(round(t["total_paid"] * 1.0))
    d = rewards(tok)
    assert d["points"] == expected, (d, t)
    assert d["history"][0]["points"] == expected and "Tickets" in d["history"][0]["reason"]
    assert me(tok)["points"] == expected


# Points on reservation and table booking (bronze)
def test_points_reservation_and_table():
    tok = S["tok"]
    before = rewards(tok)["points"]
    venue = next(v for v in requests.get(f"{API}/venues").json() if v.get("min_level", "bronze") == "bronze")
    rid = pay(tok, kind="reservation", venue_id=venue["id"], date=future(10), party_size=2, service_type="table")
    C["reservations"].append(rid)
    res = next(x for x in requests.get(f"{API}/reservations/mine", headers=h(tok)).json() if x["id"] == rid)
    after = rewards(tok)["points"]
    assert after - before == int(round(res["total"]))
    # table booking
    now = datetime.now(timezone.utc).isoformat()
    booked = None
    for e in requests.get(f"{API}/events").json():
        if e["date"] <= now:
            continue
        tables = requests.get(f"{API}/events/{e['id']}/tables", headers=h(tok)).json()
        for t in tables if isinstance(tables, list) else []:
            if t.get("min_level") == "bronze" and not t.get("booked") and t.get("available", True):
                rb = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, "kind": "table", "event_id": e["id"],
                                                                     "table_id": t["id"], "party_size": 2}, headers=h(tok))
                if rb.status_code == 200:
                    C["sessions"].append(rb.json()["session_id"])
                    bid = simulate_paid(rb.json()["session_id"])["result_id"]
                    booked = next(x for x in requests.get(f"{API}/table-bookings/mine", headers=h(tok)).json() if x["id"] == bid)
                    break
        if booked:
            break
    assert booked, "could not book any bronze table"
    C["table_bookings"].append(booked["id"])
    assert rewards(tok)["points"] - after == int(round(booked["total"]))
    assert rewards(tok)["points"] >= 1000  # 230 reservation + table min spend


# Redeem 100 -> $5 credit; history row; /auth/me reflects
def test_redeem_success():
    tok = S["tok"]
    p0 = rewards(tok)["points"]
    r = requests.post(f"{API}/rewards/redeem", json={"points": 100}, headers=h(tok))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["points"] == p0 - 100 and d["credit_balance"] == 5.0
    assert d["history"][0]["points"] == -100 and "$5.00" in d["history"][0]["reason"]
    m = me(tok)
    assert m["credit_balance"] == 5.0 and m["points"] == p0 - 100


# Credit auto-applied to next ticket, decremented, never negative
def test_credit_applied_to_ticket(ev):
    tok, _ = register()
    d = db()
    uid = C["users"][-1]
    d.users.update_one({"id": uid}, {"$set": {"points": 200}})
    r = requests.post(f"{API}/rewards/redeem", json={"points": 200}, headers=h(tok))
    assert r.status_code == 200 and r.json()["credit_balance"] == 10.0
    t = buy(tok, ev["id"])
    full = round(round(ev["price"] * 1.15, 2), 2)
    used = min(10.0, full)
    assert t["credit_used"] == pytest.approx(used, abs=0.02), t
    assert t["total_paid"] == pytest.approx(full - used, abs=0.02), t
    m = me(tok)
    assert m["credit_balance"] == pytest.approx(round(10.0 - used, 2), abs=0.01) and m["credit_balance"] >= 0
    # points on discounted total only
    assert m["points"] == int(round(t["total_paid"]))


# Multipliers silver 1.5x / gold 2x
@pytest.mark.parametrize("level,mult", [("silver", 1.5), ("gold", 2.0)])
def test_multiplier(ev, level, mult):
    tok, _ = register()
    assert requests.post(f"{API}/membership/upgrade", json={"level": level}, headers=h(tok)).status_code == 402
    set_level(C["users"][-1], level)  # simulated paid Stripe upgrade
    assert rewards(tok)["multiplier"] == mult
    t = buy(tok, ev["id"])
    assert rewards(tok)["points"] == int(round(t["total_paid"] * mult))


# Points on admin confirming luxe partner booking (not on request / decline)
def test_points_partner_booking_confirm():
    tok, _ = register()
    at = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}).json()["access_token"]
    partners = [p for p in requests.get(f"{API}/partners").json() if p.get("min_level", "bronze") == "bronze"]
    if not partners:
        pytest.skip("no bronze partner")
    ids = []
    for _ in range(2):
        r = requests.post(f"{API}/partner-bookings", json={"partner_id": partners[0]["id"], "date": future(14),
                                                           "units": 1, "guests": 2}, headers=h(tok))
        assert r.status_code == 201, r.text
        ids.append(r.json())
        C["partner_bookings"].append(r.json()["id"])
    assert rewards(tok)["points"] == 0
    r = requests.patch(f"{API}/admin/partner-bookings/{ids[1]['id']}", json={"status": "declined"}, headers=h(at))
    assert r.status_code == 200 and rewards(tok)["points"] == 0
    r = requests.patch(f"{API}/admin/partner-bookings/{ids[0]['id']}", json={"status": "confirmed"}, headers=h(at))
    assert r.status_code == 200
    d = rewards(tok)
    assert d["points"] == int(round(ids[0]["total"])) and "Luxe" in d["history"][0]["reason"]
    # second confirm is rejected, no double award
    r = requests.patch(f"{API}/admin/partner-bookings/{ids[0]['id']}", json={"status": "confirmed"}, headers=h(at))
    assert r.status_code == 400 and rewards(tok)["points"] == d["points"]


# Perks list: 9, locked flags by level, code empty until claimed
def test_perks_bronze():
    tok, _ = register()
    S["ptok"] = tok
    r = requests.get(f"{API}/perks", headers=h(tok))
    assert r.status_code == 200
    perks = r.json()
    assert len(perks) == 9
    for p in perks:
        assert p["code"] == "" and p["claimed"] is False
        assert p["locked"] == (p["min_level"] != "bronze")
    S["perks"] = perks


# Claim: 403 locked, returns code, idempotent; upgrade unlocks
def test_perk_claim():
    tok, perks = S["ptok"], S["perks"]
    locked = next(p for p in perks if p["locked"])
    r = requests.post(f"{API}/perks/{locked['id']}/claim", headers=h(tok))
    assert r.status_code == 403 and "membership required" in r.json()["detail"]
    open_ = next(p for p in perks if not p["locked"])
    r1 = requests.post(f"{API}/perks/{open_['id']}/claim", headers=h(tok))
    assert r1.status_code == 200 and r1.json()["code"] and r1.json()["claimed"] is True
    r2 = requests.post(f"{API}/perks/{open_['id']}/claim", headers=h(tok))
    assert r2.status_code == 200 and r2.json()["code"] == r1.json()["code"]
    uid = C["users"][-1]
    assert db().perk_claims.count_documents({"user_id": uid, "perk_id": open_["id"]}) == 1
    after = {p["id"]: p for p in requests.get(f"{API}/perks", headers=h(tok)).json()}
    assert after[open_["id"]]["code"] == r1.json()["code"]
    assert requests.post(f"{API}/perks/nope/claim", headers=h(tok)).status_code == 404
    assert requests.post(f"{API}/membership/upgrade", json={"level": "gold"}, headers=h(tok)).status_code == 402
    set_level(uid, "gold")  # simulated paid Stripe upgrade
    assert all(not p["locked"] for p in requests.get(f"{API}/perks", headers=h(tok)).json())
