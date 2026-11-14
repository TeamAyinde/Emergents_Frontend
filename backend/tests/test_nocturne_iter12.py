"""Iteration 12: monthly promoter leaderboard + $100 winner bonus, spotlight eligibility/daily cap, gift memberships.
Only TEST_ data is created; everything is removed / reverted by id at teardown."""
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
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
GUEST = ("guest@nocturne.app", "GuestPass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")
C = {"users": [], "sessions": set(), "tickets": [], "spotlights": [], "gifts": [], "award_month": None}
NOW = datetime.now(timezone.utc)
LAST_MONTH = (NOW.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
LAST_MONTH_DT = (NOW.replace(day=1) - timedelta(days=3))


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(role="guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": f"TEST_ Iter12 {role}", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].add(r.json()["session_id"])
    return r


def seed_ticket(event_id, promoter_id, qty=1, created_at=None, earning=1.0):
    tid = f"TEST_{uuid.uuid4()}"
    DB.tickets.insert_one({"id": tid, "event_id": event_id, "event_title": "TEST_", "event_date": NOW, "venue_name": "TEST_",
                           "user_id": f"TEST_{uuid.uuid4()}", "promoter_id": promoter_id, "quantity": qty, "total_paid": 0,
                           "credit_used": 0, "platform_fee": 0, "promoter_earning": earning, "venue_share": 0,
                           "payment_session": None, "checked_in": False, "created_at": created_at or NOW})
    C["tickets"].append(tid)
    return tid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in C["sessions"]:
        try:
            requests.post(f"{API}/payments/cancel/{sid}", timeout=10)
        except Exception:
            pass
    DB.payment_transactions.delete_many({"session_id": {"$in": list(C["sessions"])}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.tickets.delete_many({"user_id": {"$in": C["users"]}})
    DB.spotlights.delete_many({"id": {"$in": C["spotlights"]}})
    DB.gifts.delete_many({"buyer_id": {"$in": C["users"]}})
    DB.leaderboard_awards.delete_many({"user_id": {"$in": C["users"]}})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def promoter():
    tok = login(PROMOTER)
    me = requests.get(f"{API}/auth/me", headers=h(tok)).json()
    return tok, me


@pytest.fixture(scope="module")
def event():
    evs = requests.get(f"{API}/events").json()
    assert evs
    return evs[-1]


# ---------- Monthly leaderboard + winner bonus ----------

def test_leaderboard_shape_current_month():
    r = requests.get(f"{API}/promoter/leaderboard/monthly")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["month"] == NOW.strftime("%Y-%m") and d["bonus"] == 100
    assert isinstance(d["entries"], list)


def test_leaderboard_counts_only_promoters_and_this_month(event):
    _, p = register("promoter")
    _, g = register("guest")
    seed_ticket(event["id"], p["id"], qty=3, earning=2.5)
    seed_ticket(event["id"], g["id"], qty=50)  # not a promoter -> must not be listed
    seed_ticket(event["id"], p["id"], qty=40, created_at=NOW - timedelta(days=75))  # two months ago -> not counted
    d = requests.get(f"{API}/promoter/leaderboard/monthly").json()
    rows = {e["user_id"]: e for e in d["entries"]}
    assert g["id"] not in rows
    assert rows[p["id"]]["guests"] == 3 and rows[p["id"]]["earnings"] == 2.5
    assert rows[p["id"]]["full_name"] == p["full_name"]


def test_last_month_winner_awarded_once(event):
    if DB.leaderboard_awards.find_one({"_id": LAST_MONTH}):
        pytest.skip("last month already awarded (real data) — cannot seed a winner")
    _, w = register("promoter")
    C["award_month"] = LAST_MONTH
    seed_ticket(event["id"], w["id"], qty=500, created_at=LAST_MONTH_DT)
    for _ in range(3):
        d = requests.get(f"{API}/promoter/leaderboard/monthly").json()
    assert d["last_winner"]["full_name"] == w["full_name"] and d["last_winner"]["guests"] == 500
    assert d["last_winner"]["bonus"] == 100 and d["last_winner"]["month"] == LAST_MONTH
    assert DB.users.find_one({"id": w["id"]})["wallet_balance"] == 100
    assert DB.leaderboard_awards.count_documents({"_id": LAST_MONTH}) == 1
    assert w["id"] not in {e["user_id"] for e in d["entries"]}  # last month's tickets not in this month


# ---------- Spotlight eligibility ----------

def test_spotlight_ineligible_without_own_code_ticket(promoter, event):
    tok, _ = promoter
    assert not DB.tickets.find_one({"event_id": event["id"], "promoter_id": promoter[1]["id"]})
    r = requests.get(f"{API}/spotlight/eligibility/{event['id']}", headers=h(tok))
    assert r.status_code == 200
    d = r.json()
    assert d["eligible"] is False and "guest" in d["reason"].lower()


def test_spotlight_checkout_blocked_403_when_ineligible(promoter, event):
    r = checkout(promoter[0], kind="spotlight", event_id=event["id"], plan="3days")
    assert r.status_code == 403 and "guest" in r.json()["detail"].lower()


def test_spotlight_guest_not_eligible(event):
    d = requests.get(f"{API}/spotlight/eligibility/{event['id']}", headers=h(login(GUEST))).json()
    assert d["eligible"] is False and d["remaining_today"] == 0


def test_spotlight_admin_exempt(event):
    d = requests.get(f"{API}/spotlight/eligibility/{event['id']}", headers=h(login(ADMIN))).json()
    assert d["eligible"] is True


def test_spotlight_eligible_after_real_marco1_ticket(promoter, event):
    """Real ticket checkout (credit path) by a TEST_ guest with code MARCO1."""
    tok, me = promoter
    gtok, g = register("guest")
    grant_credit(g["id"], 5000)
    set_level(g["id"], "gold")
    wallet_before = DB.users.find_one({"id": me["id"]}).get("wallet_balance", 0)
    r = checkout(gtok, kind="ticket", event_id=event["id"], quantity=1, promoter_code="MARCO1")
    assert r.status_code == 200, r.text
    t = DB.tickets.find_one({"user_id": g["id"], "event_id": event["id"]})
    assert t and t["promoter_id"] == me["id"]
    # revert promoter wallet commission from this TEST_ ticket
    earned = t.get("promoter_earning", 0)
    if earned:
        DB.users.update_one({"id": me["id"]}, {"$inc": {"wallet_balance": -earned}})
    assert round(DB.users.find_one({"id": me["id"]}).get("wallet_balance", 0), 2) == round(wallet_before, 2)
    d = requests.get(f"{API}/spotlight/eligibility/{event['id']}", headers=h(tok)).json()
    assert d["eligible"] is True and d["remaining_today"] == 2


def test_spotlight_checkout_ok_when_eligible(promoter, event):
    r = checkout(promoter[0], kind="spotlight", event_id=event["id"], plan="3days")
    assert r.status_code == 200 and r.json()["amount"] == 39.0


def test_spotlight_daily_cap(promoter, event):
    tok, me = promoter
    for _ in range(2):
        sid = f"TEST_{uuid.uuid4()}"
        DB.spotlights.insert_one({"id": sid, "event_id": f"TEST_{uuid.uuid4()}", "user_id": me["id"], "plan": "3days",
                                  "amount": 0, "until": NOW, "created_at": datetime.now(timezone.utc)})
        C["spotlights"].append(sid)
    d = requests.get(f"{API}/spotlight/eligibility/{event['id']}", headers=h(tok)).json()
    assert d["eligible"] is False and d["remaining_today"] == 0 and "Daily limit reached" in d["reason"]
    r = checkout(tok, kind="spotlight", event_id=event["id"], plan="week")
    assert r.status_code == 403 and "Daily limit reached" in r.json()["detail"]
    DB.spotlights.delete_many({"id": {"$in": C["spotlights"]}})


# ---------- Gift memberships ----------

def test_gift_checkout_gold_amount():
    tok, _ = register("guest")
    r = checkout(tok, kind="gift", level="gold", recipient_email="TEST_Friend@Example.com", note="  hi  ")
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 149 and r.json()["url"]
    tx = DB.payment_transactions.find_one({"session_id": r.json()["session_id"]})
    assert tx["payload"]["recipient_email"] == "test_friend@example.com" and tx["payload"]["note"] == "hi"


def test_gift_silver_amount():
    tok, _ = register("guest")
    assert checkout(tok, kind="gift", level="silver").json()["amount"] == 49


def test_gift_bronze_400_invalid_email_422():
    tok, _ = register("guest")
    assert checkout(tok, kind="gift", level="bronze").status_code == 400
    assert checkout(tok, kind="gift", level="gold", recipient_email="not-an-email").status_code == 422


def test_gift_full_flow_redeem():
    btok, b = register("guest")
    sid = checkout(btok, kind="gift", level="gold", note="TEST_ note").json()["session_id"]
    tx = simulate_paid(sid)
    assert tx["status"] == "paid" and tx["result_id"]
    mine = requests.get(f"{API}/gifts/mine", headers=h(btok)).json()
    assert len(mine) == 1 and mine[0]["code"].startswith("GIFT-") and len(mine[0]["code"]) == 11
    code = mine[0]["code"]
    assert mine[0]["level"] == "gold" and mine[0]["redeemed"] is False and mine[0]["days"] == 30
    # own code -> 400
    assert requests.post(f"{API}/gifts/redeem", json={"code": code}, headers=h(btok)).status_code == 400
    rtok, r_user = register("guest")
    r = requests.post(f"{API}/gifts/redeem", json={"code": code.lower()}, headers=h(rtok))
    assert r.status_code == 200, r.text
    until = datetime.fromisoformat(r.json()["until"].replace("Z", "+00:00"))
    until = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
    assert r.json()["level"] == "gold"
    assert timedelta(days=29, hours=23) < until - datetime.now(timezone.utc) <= timedelta(days=30)
    me = requests.get(f"{API}/auth/me", headers=h(rtok)).json()
    assert me["level"] == "gold"
    mine = requests.get(f"{API}/gifts/mine", headers=h(btok)).json()
    assert mine[0]["redeemed"] is True and mine[0]["redeemed_by_name"] == r_user["full_name"]
    # again -> 409
    ztok, _ = register("guest")
    assert requests.post(f"{API}/gifts/redeem", json={"code": code}, headers=h(ztok)).status_code == 409
    assert requests.post(f"{API}/gifts/redeem", json={"code": "GIFT-ZZZZZZ"}, headers=h(ztok)).status_code == 404


def test_gift_redeem_unauth_401():
    assert requests.post(f"{API}/gifts/redeem", json={"code": "GIFT-ZZZZZZ"}).status_code == 401


def _paid_gift(level):
    btok, _ = register("guest")
    sid = checkout(btok, kind="gift", level=level).json()["session_id"]
    simulate_paid(sid)
    return requests.get(f"{API}/gifts/mine", headers=h(btok)).json()[0]["code"]


def test_gift_same_level_stacks():
    a, b = _paid_gift("gold"), _paid_gift("gold")
    rtok, _ = register("guest")
    requests.post(f"{API}/gifts/redeem", json={"code": a}, headers=h(rtok))
    r = requests.post(f"{API}/gifts/redeem", json={"code": b}, headers=h(rtok)).json()
    until = datetime.fromisoformat(r["until"].replace("Z", "+00:00"))
    until = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
    assert r["level"] == "gold" and until - datetime.now(timezone.utc) > timedelta(days=59)


def test_gift_lower_level_does_not_shorten_existing_gold():
    """Gold stacked to ~60d, then a Silver gift is redeemed: the Gold end date must not move earlier."""
    a, b, s = _paid_gift("gold"), _paid_gift("gold"), _paid_gift("silver")
    rtok, ru = register("guest")
    for c in (a, b):
        requests.post(f"{API}/gifts/redeem", json={"code": c}, headers=h(rtok))
    before = DB.users.find_one({"id": ru["id"]})["gift_until"].replace(tzinfo=timezone.utc)
    r = requests.post(f"{API}/gifts/redeem", json={"code": s}, headers=h(rtok))
    # a lower gift adds nothing: refused so the code stays usable for someone else
    assert r.status_code == 400
    after = DB.users.find_one({"id": ru["id"]})["gift_until"].replace(tzinfo=timezone.utc)
    assert after == before, f"gold changed from {before} to {after}"
    assert DB.gifts.find_one({"code": s})["redeemed"] is False
