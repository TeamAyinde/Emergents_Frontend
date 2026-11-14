"""Iteration 11: Gold yearly subscription ($1,490/yr), promoter Event Spotlight ($39/3d, $79/7d),
venue earnings dashboard (/api/host/earnings). Only TEST_ data is created; restored/removed by id at teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import certifi
import pytest
import requests
import stripe
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import simulate_paid

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
VENUE = ("venue@nocturne.app", "VenuePass123!")
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
GUEST = ("guest@nocturne.app", "GuestPass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")
C = {"users": [], "sessions": set(), "events": [], "payables": [], "spot_restore": {}, "tickets": []}

_raw = (os.environ.get("STRIPE_API_KEY") or "").strip()
_OWN = _raw.startswith(("sk_", "rk_")) and "emergent" not in _raw
stripe.api_key = _raw if _OWN else "sk_test_emergent"
if not _OWN:
    stripe.api_base = "https://integrations.emergentagent.com/stripe"
stripe.ca_bundle_path = certifi.where()


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(tier="member"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Iter11", "membership_tier": tier, "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]["id"]


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].add(r.json()["session_id"])
    return r


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in C["sessions"]:
        try:
            requests.post(f"{API}/payments/cancel/{sid}", timeout=10)
        except Exception:
            pass
    DB.payment_transactions.delete_many({"session_id": {"$in": list(C["sessions"])}})
    DB.spotlights.delete_many({"user_id": {"$in": C["users"]}})
    for eid, orig in C["spot_restore"].items():
        DB.spotlights.delete_many({"event_id": eid, "created_at": {"$gte": orig["t"]}})
        if orig["until"] is None:
            DB.events.update_one({"id": eid}, {"$unset": {"spotlight_until": "", "spotlight_by": ""}})
        else:
            DB.events.update_one({"id": eid}, {"$set": {"spotlight_until": orig["until"], "spotlight_by": orig["by"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.venue_payables.delete_many({"id": {"$in": C["payables"]}})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def promoter_tok():
    return login(PROMOTER)


@pytest.fixture(scope="module")
def future_event():
    r = requests.get(f"{API}/events")
    assert r.status_code == 200 and r.json()
    # pick the last (lowest-ranked) event so pinning it to the top is observable
    ev = r.json()[-1]
    # iteration 12 rule: promoters can only spotlight events they've brought >=1 guest to (seed a TEST_ ticket)
    pid = DB.users.find_one({"email": PROMOTER[0]})["id"]
    tid = f"TEST_{uuid.uuid4()}"
    DB.tickets.insert_one({"id": tid, "event_id": ev["id"], "user_id": f"TEST_{uuid.uuid4()}", "promoter_id": pid,
                           "quantity": 1, "promoter_earning": 0.0, "created_at": datetime.now(timezone.utc) - timedelta(days=400)})
    C["tickets"].append(tid)
    return ev


# ---------- Gold yearly subscription ----------

def test_gold_yearly_checkout_amount_and_interval():
    tok, _ = register()
    r = checkout(tok, kind="membership", level="gold", interval="year")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount"] == 1490.0 and d["url"]
    tx = DB.payment_transactions.find_one({"session_id": d["session_id"]}, {"_id": 0})
    assert tx["payload"] == {"level": "gold", "interval": "year"}
    assert "$1,490/year" in tx["label"]
    s = stripe.checkout.Session.retrieve(d["session_id"])
    assert s.mode == "subscription"
    assert s.amount_total == 149000


def test_gold_yearly_line_item_recurring_year():
    tok, _ = register()
    d = checkout(tok, kind="membership", level="gold", interval="year").json()
    try:
        s = stripe.checkout.Session.retrieve(d["session_id"], expand=["line_items"])
        price = s.line_items.data[0].price
        assert price.recurring.interval == "year"
        assert price.unit_amount == 149000
    except stripe.StripeError as e:
        pytest.skip(f"proxy cannot list line items: {e}")


@pytest.mark.parametrize("level", ["silver", "bronze"])
def test_yearly_non_gold_rejected(level):
    tok, _ = register()
    r = checkout(tok, kind="membership", level=level, interval="year")
    assert r.status_code == 400 and "Gold" in r.json()["detail"]


def test_bad_interval_422():
    tok, _ = register()
    assert checkout(tok, kind="membership", level="gold", interval="week").status_code == 422


def test_gold_monthly_still_149():
    tok, _ = register()
    r = checkout(tok, kind="membership", level="gold")
    assert r.status_code == 200 and r.json()["amount"] == 149.0


def test_yearly_and_monthly_dont_close_each_other_when_switching():
    # a new gold checkout (any interval) closes the earlier open gold checkout
    tok, _ = register()
    a = checkout(tok, kind="membership", level="gold").json()["session_id"]
    checkout(tok, kind="membership", level="gold", interval="year")
    assert DB.payment_transactions.find_one({"session_id": a})["status"] == "cancelled"


# ---------- Spotlight ----------

@pytest.mark.parametrize("plan,amount", [("3days", 39.0), ("week", 79.0)])
def test_spotlight_checkout_amount(promoter_tok, future_event, plan, amount):
    r = checkout(promoter_tok, kind="spotlight", event_id=future_event["id"], plan=plan)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == amount and r.json()["url"]
    tx = DB.payment_transactions.find_one({"session_id": r.json()["session_id"]}, {"_id": 0})
    assert tx["kind"] == "spotlight" and tx["credit_used"] == 0


@pytest.mark.parametrize("creds", [GUEST, VENUE])
def test_spotlight_non_promoter_403(future_event, creds):
    r = checkout(login(creds), kind="spotlight", event_id=future_event["id"], plan="3days")
    assert r.status_code == 403


def test_spotlight_bad_plan_400(promoter_tok, future_event):
    assert checkout(promoter_tok, kind="spotlight", event_id=future_event["id"], plan="month").status_code == 400


def test_spotlight_unknown_event_404(promoter_tok):
    assert checkout(promoter_tok, kind="spotlight", event_id="nope", plan="3days").status_code == 404


def test_spotlight_past_event_400(promoter_tok, future_event):
    src = DB.events.find_one({"id": future_event["id"]}, {"_id": 0})
    past = {**src, "id": str(uuid.uuid4()), "title": "TEST_ past event",
            "date": datetime.now(timezone.utc) - timedelta(days=2)}
    past.pop("spotlight_until", None)
    DB.events.insert_one(past)
    C["events"].append(past["id"])
    r = checkout(promoter_tok, kind="spotlight", event_id=past["id"], plan="3days")
    assert r.status_code == 400 and "already happened" in r.json()["detail"]


def test_spotlight_paid_pins_event_first(promoter_tok, future_event):
    eid = future_event["id"]
    ev = DB.events.find_one({"id": eid}, {"_id": 0})
    C["spot_restore"][eid] = {"until": ev.get("spotlight_until"), "by": ev.get("spotlight_by"),
                             "t": datetime.now(timezone.utc) - timedelta(seconds=1)}
    sid = checkout(promoter_tok, kind="spotlight", event_id=eid, plan="3days").json()["session_id"]
    tx = simulate_paid(sid)
    assert tx["status"] == "paid" and tx["result_id"], tx
    upd = DB.events.find_one({"id": eid}, {"_id": 0})
    until = upd["spotlight_until"].replace(tzinfo=timezone.utc)
    assert timedelta(days=2, hours=23) < until - datetime.now(timezone.utc) <= timedelta(days=3)
    assert DB.spotlights.find_one({"id": tx["result_id"]})["plan"] == "3days"
    evs = requests.get(f"{API}/events").json()
    assert evs[0]["id"] == eid and evs[0]["spotlight"] is True
    assert sum(1 for e in evs if e["spotlight"]) == 1
    assert requests.get(f"{API}/events/{eid}").json()["spotlight"] is True


def test_spotlight_extends_from_current_end(promoter_tok, future_event):
    eid = future_event["id"]
    before = DB.events.find_one({"id": eid})["spotlight_until"]
    sid = checkout(promoter_tok, kind="spotlight", event_id=eid, plan="week").json()["session_id"]
    simulate_paid(sid)
    after = DB.events.find_one({"id": eid})["spotlight_until"]
    assert abs((after - before) - timedelta(days=7)) < timedelta(seconds=5)


# ---------- Venue earnings ----------

def test_earnings_shape_and_sums():
    tok = login(VENUE)
    venues = requests.get(f"{API}/host/venues", headers=h(tok)).json()
    base = requests.get(f"{API}/host/earnings", headers=h(tok)).json()
    vid = venues[0]["id"]
    now = datetime.now(timezone.utc)
    rows = [("ticket", "owed", 40.0), ("table", "owed", 250.5), ("reservation", "paid", 100.0)]
    for i, (src, st, amt) in enumerate(rows):
        pid = f"TEST_{uuid.uuid4()}"
        C["payables"].append(pid)
        DB.venue_payables.insert_one({"id": pid, "venue_id": vid, "venue_name": venues[0]["name"], "amount": amt,
                                      "source": src, "status": st, "created_at": now + timedelta(seconds=i)})
    d = requests.get(f"{API}/host/earnings", headers=h(tok)).json()
    assert set(d) >= {"owed", "paid", "by_source", "recent"}
    assert round(d["owed"] - base["owed"], 2) == 290.5
    assert round(d["paid"] - base["paid"], 2) == 100.0
    assert d["by_source"]["table"]["amount"] >= 250.5 and d["by_source"]["table"]["count"] >= 1
    assert d["recent"][0]["source"] == "reservation" and "_id" not in d["recent"][0]
    hp = requests.get(f"{API}/host/payouts", headers=h(tok)).json()
    assert hp["owed"] == d["owed"] and hp["paid"] == d["paid"]


@pytest.mark.parametrize("creds", [GUEST, PROMOTER])
def test_earnings_forbidden(creds):
    assert requests.get(f"{API}/host/earnings", headers=h(login(creds))).status_code == 403


def test_earnings_admin_ok():
    r = requests.get(f"{API}/host/earnings", headers=h(login(ADMIN)))
    assert r.status_code == 200 and "by_source" in r.json()


def test_earnings_unauth_401():
    assert requests.get(f"{API}/host/earnings").status_code in (401, 403)
