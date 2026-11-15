"""Iteration 16: venue guest ratings (from feedback), host feedback view, referral rewards (invite codes).
Uses TEST_ users only; guest (referrer) points and ledger are restored on teardown."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import grant_credit, simulate_paid

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
GUEST = ("guest@nocturne.app", "GuestPass123!")
VENUE = ("venue@nocturne.app", "VenuePass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")
MIRAGE = "b69dbf8a-41aa-404a-937e-9d80746c78db"  # owned by venue@
VELVET_SKY = "f1f73488-c9cb-4eaa-9b00-d1e549facd3c"  # no owner
HARBOR = "3556d109-1c21-4418-b7d3-d4d3ca808ed7"
EV_MIRAGE = "fc35bae2-2ac8-421e-892b-dd59914d088d"  # Velvet Sessions (bronze, $80)
EV_PALM = "63910aab-1c0e-48a2-a133-84977aab1cab"  # Private Members Social (bronze, $60)
EV_SKY = "62e67a18-5285-4874-88e8-273521eb7950"
NOW = datetime.now(timezone.utc)
C = {"users": [], "tickets": [], "sessions": [], "sold": {}}
S = {}


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(name="TEST_Iter16 Lastname", invite=None, expect=201):
    email = f"test_{uuid.uuid4().hex[:8]}@nocturne.app"
    body = {"email": email, "password": "TestPass123!", "role": "guest", "full_name": name,
            "membership_tier": "member", "marketing_opt_in": False}
    if invite is not None:
        body["invite_code"] = invite
    r = requests.post(f"{API}/auth/register", json=body)
    assert r.status_code == expect, r.text
    if expect != 201:
        return r
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def past_ticket(uid, event_id):
    ev = DB.events.find_one({"id": event_id}, {"_id": 0, "title": 1})
    tid = f"TEST_{uuid.uuid4().hex}"
    DB.tickets.insert_one({"id": tid, "event_id": event_id, "event_title": ev["title"], "venue_name": "TEST_",
                           "event_date": NOW - timedelta(days=1), "user_id": uid, "quantity": 1, "total_paid": 0.0,
                           "checked_in": False, "created_at": NOW})
    C["tickets"].append(tid)
    return tid


def venue(vid):
    r = requests.get(f"{API}/venues/{vid}")
    assert r.status_code == 200, r.text
    return r.json()


def checkout(tok, event_id):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, "kind": "ticket", "event_id": event_id},
                      headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].append(r.json()["session_id"])
    return r


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    g = DB.users.find_one({"email": GUEST[0]}, {"_id": 0, "id": 1, "points": 1})
    S["guest"] = g
    had_origin = DB.settings.find_one({"_id": "public_origin"})
    yield
    if not had_origin:  # https checkouts save public_origin; remove if it wasn't there before
        DB.settings.delete_one({"_id": "public_origin"})
    for s in C["sessions"]:
        tx = DB.payment_transactions.find_one({"session_id": s})
        if tx and tx.get("result_id"):
            t = DB.tickets.find_one({"id": tx["result_id"]})
            if t:  # issued via checkout -> tickets_sold was incremented
                DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t.get("quantity", 1)}})
            DB.venue_payables.delete_many({"record_id": tx["result_id"]})
            DB.tickets.delete_one({"id": tx["result_id"]})
        DB.payment_transactions.delete_one({"session_id": s})
    DB.feedback.delete_many({"ticket_id": {"$in": C["tickets"]}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    for uid in C["users"]:
        tids = [t["id"] for t in DB.tickets.find({"user_id": uid}, {"id": 1})]
        DB.venue_payables.delete_many({"record_id": {"$in": tids}})
        DB.tickets.delete_many({"user_id": uid})
        DB.points_ledger.delete_many({"user_id": uid})
        DB.payment_transactions.delete_many({"user_id": uid})
        DB.user_sessions.delete_many({"user_id": uid})
        DB.users.delete_one({"id": uid})
    DB.points_ledger.delete_many({"user_id": g["id"], "reason": {"$regex": "^Invited TEST_"}})
    DB.users.update_one({"id": g["id"]}, {"$set": {"points": g.get("points", 0)}})


# ---------- Venue guest ratings ----------
class TestVenueRatings:
    def test_aggregate_and_count(self):
        base = venue(MIRAGE)
        assert "guest_rating" in base and "guest_rating_count" in base
        n0 = base["guest_rating_count"]
        tok1, u1 = register("TEST_Rater One")
        tok2, u2 = register("TEST_Rater Two")
        t1, t2 = past_ticket(u1["id"], EV_MIRAGE), past_ticket(u2["id"], EV_MIRAGE)
        r = requests.post(f"{API}/feedback/{t1}", json={"rating": 5, "comment": "TEST_ great"}, headers=h(tok1))
        assert r.status_code == 200, r.text
        assert DB.feedback.find_one({"ticket_id": t1})["venue_id"] == MIRAGE
        # shown only from MIN_GUEST_RATINGS (3) reviews; the raw count is in the DB
        assert DB.feedback.count_documents({"venue_id": MIRAGE}) >= 1
        r = requests.post(f"{API}/feedback/{t2}", json={"rating": 4}, headers=h(tok2))
        assert r.status_code == 200, r.text
        t3 = past_ticket(u2["id"], EV_MIRAGE)
        assert requests.post(f"{API}/feedback/{t3}", json={"rating": 4}, headers=h(tok2)).status_code == 200
        v = venue(MIRAGE)
        assert v["guest_rating_count"] == DB.feedback.count_documents({"venue_id": MIRAGE}) >= 3
        if n0 == 0:
            assert v["guest_rating"] == 4.3  # (5+4+4)/3 = 4.333 -> 1 decimal
        lst = {x["id"]: x for x in requests.get(f"{API}/venues").json()}
        assert lst[MIRAGE]["guest_rating"] == v["guest_rating"]
        assert lst[MIRAGE]["guest_rating_count"] == v["guest_rating_count"]
        S["tok_rater"] = tok1

    def test_no_feedback_null(self):
        v = venue(HARBOR)
        if DB.feedback.count_documents({"venue_id": HARBOR}) == 0:
            assert v["guest_rating"] is None and v["guest_rating_count"] == 0
        assert isinstance(v["rating"], (int, float))  # seeded fallback still present

    def test_other_venue_feedback(self):
        tok, u = register("TEST_Sky Rater")
        t = past_ticket(u["id"], EV_SKY)
        assert requests.post(f"{API}/feedback/{t}", json={"rating": 2}, headers=h(tok)).status_code == 200
        assert DB.feedback.count_documents({"venue_id": VELVET_SKY}) >= 1
        S["sky_ticket"] = t


# ---------- Host feedback ----------
class TestHostFeedback:
    def test_owner_sees_own_only(self):
        r = requests.get(f"{API}/host/feedback", headers=h(login(*VENUE)))
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) >= {"average", "count", "items"}
        ids = {i["id"] for i in d["items"]}
        assert set(C["tickets"][:3]) <= ids
        assert S["sky_ticket"] not in ids
        it = next(i for i in d["items"] if i["id"] == C["tickets"][0])
        assert it["guest"] == "TEST_Rater" and it["rating"] == 5 and it["comment"] == "TEST_ great"
        assert "user_id" not in it and "email" not in it
        owned = [v["id"] for v in DB.venues.find({"owner_id": DB.users.find_one({"email": VENUE[0]})["id"]})]
        assert d["count"] == DB.feedback.count_documents({"venue_id": {"$in": owned}})

    def test_admin_sees_all(self):
        d = requests.get(f"{API}/host/feedback", headers=h(login(*ADMIN))).json()
        assert S["sky_ticket"] in {i["id"] for i in d["items"]}

    def test_guest_forbidden(self):
        assert requests.get(f"{API}/host/feedback", headers=h(login(*GUEST))).status_code == 403
        assert requests.get(f"{API}/host/feedback").status_code == 401


# ---------- Referral rewards ----------
class TestReferral:
    def test_unknown_code_400(self):
        r = register(invite="TEST_NOPE99", expect=400)
        assert "invite" in r.json()["detail"].lower()

    def test_blank_code_ok(self):
        tok, u = register(invite="  ")
        assert "referred_by" not in DB.users.find_one({"id": u["id"]})

    def test_register_with_code_and_reward_once(self):
        gtok = login(*GUEST)
        code = requests.get(f"{API}/auth/me", headers=h(gtok)).json()["referral_code"]
        inv0 = requests.get(f"{API}/me/invites", headers=h(gtok)).json()
        assert inv0["code"] == code and inv0["referrer_points"] == 200 and inv0["friend_points"] == 100
        gpts0 = DB.users.find_one({"email": GUEST[0]})["points"]
        tok, u = register("TEST_Friend Ref", invite=code.lower())  # case-insensitive
        doc = DB.users.find_one({"id": u["id"]})
        assert doc["referred_by"] == S["guest"]["id"]
        inv1 = requests.get(f"{API}/me/invites", headers=h(gtok)).json()
        assert inv1["invited"] == inv0["invited"] + 1 and inv1["rewarded"] == inv0["rewarded"]
        # first paid booking via credit path
        grant_credit(u["id"], 1000)
        r = checkout(tok, EV_MIRAGE)
        assert r.status_code == 200 and r.json()["paid_with_credit"], r.text
        assert DB.users.find_one({"email": GUEST[0]})["points"] == gpts0 + 200
        assert DB.points_ledger.count_documents({"user_id": S["guest"]["id"], "reason": "Invited TEST_Friend", "points": 200}) == 1
        assert DB.points_ledger.count_documents({"user_id": u["id"], "points": 100, "reason": "Welcome bonus · first night"}) == 1
        assert DB.users.find_one({"id": u["id"]})["referral_rewarded"] is True
        inv2 = requests.get(f"{API}/me/invites", headers=h(gtok)).json()
        assert inv2["rewarded"] == inv0["rewarded"] + 1 and inv2["points_earned"] == inv2["rewarded"] * 200
        # second booking: no more referral points
        r = checkout(tok, EV_PALM)
        assert r.status_code == 200, r.text
        assert DB.users.find_one({"email": GUEST[0]})["points"] == gpts0 + 200
        assert DB.points_ledger.count_documents({"user_id": u["id"], "reason": "Welcome bonus · first night"}) == 1

    def test_card_path_simulate_paid(self):
        gtok = login(*GUEST)
        code = requests.get(f"{API}/auth/me", headers=h(gtok)).json()["referral_code"]
        gpts0 = DB.users.find_one({"email": GUEST[0]})["points"]
        tok, u = register("TEST_Cardy Friend", invite=code)
        r = checkout(tok, EV_PALM)
        if r.status_code != 200 or not r.json().get("url"):
            pytest.skip(f"card checkout unavailable: {r.status_code} {r.text[:120]}")
        assert DB.users.find_one({"email": GUEST[0]})["points"] == gpts0  # unpaid: nothing yet
        tx = simulate_paid(r.json()["session_id"])
        assert tx["fulfilled"] and tx.get("result_id"), tx
        assert DB.users.find_one({"email": GUEST[0]})["points"] == gpts0 + 200
        assert DB.points_ledger.count_documents({"user_id": u["id"], "reason": "Welcome bonus · first night"}) == 1
        simulate_paid(r.json()["session_id"])  # idempotent
        assert DB.users.find_one({"email": GUEST[0]})["points"] == gpts0 + 200

    def test_non_referred_no_reward(self):
        tok, u = register("TEST_Solo Person")
        grant_credit(u["id"], 1000)
        assert checkout(tok, EV_MIRAGE).status_code == 200
        assert DB.points_ledger.count_documents({"user_id": u["id"], "reason": "Welcome bonus · first night"}) == 0
        assert not DB.users.find_one({"id": u["id"]}).get("referral_rewarded")

    def test_invites_auth(self):
        assert requests.get(f"{API}/me/invites").status_code == 401
