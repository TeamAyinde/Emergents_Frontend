"""Nocturne API regression tests (iteration 2): auth/tier rules, catalog, tickets, check-in, promoter wallet, reservations.
All created data is tracked by id and removed at module teardown (promoter wallet restored)."""
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

GUEST = ("guest@nocturne.app", "GuestPass123!")
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
VENUE = ("venue@nocturne.app", "VenuePass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")

CREATED = {"users": [], "events": [], "tickets": [], "reservations": [], "withdrawal_users": []}
WALLET_DELTA = {"promoter": 0.0}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed for {creds[0]}: {r.status_code} {r.text}")
    return r.json()


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for t in db.tickets.find({"id": {"$in": CREATED["tickets"]}}):
        db.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
    db.tickets.delete_many({"id": {"$in": CREATED["tickets"]}})
    db.reservations.delete_many({"id": {"$in": CREATED["reservations"]}})
    db.events.delete_many({"id": {"$in": CREATED["events"]}})
    db.users.delete_many({"id": {"$in": CREATED["users"]}})
    # withdrawals are now recorded (iteration 3): remove the ones this run created
    for uid, since in CREATED["withdrawal_users"]:
        db.withdrawals.delete_many({"user_id": uid, "created_at": {"$gte": since}})
    if WALLET_DELTA["promoter"]:
        db.users.update_one({"email": PROMOTER[0]}, {"$inc": {"wallet_balance": -round(WALLET_DELTA["promoter"], 2)}})


@pytest.fixture(scope="module")
def guest():
    return login(GUEST)


@pytest.fixture(scope="module")
def promoter():
    return login(PROMOTER)


@pytest.fixture(scope="module")
def venue_owner():
    return login(VENUE)


@pytest.fixture(scope="module")
def event():
    # bronze test users can only buy bronze-gated events (membership levels, iteration 4)
    r = requests.get(f"{API}/events")
    assert r.status_code == 200 and len(r.json()) > 0
    return next(e for e in r.json() if e.get("min_level", "bronze") == "bronze")


def bronze_venue_id():
    return next(v for v in requests.get(f"{API}/venues").json() if v.get("min_level", "bronze") == "bronze")["id"]


def register(role="guest", tier=None):
    body = {"email": f"TEST_{role}_{uuid.uuid4().hex[:6]}@example.com", "password": "Passw0rd!", "full_name": f"TEST {role}", "role": role}
    if tier:
        body["membership_tier"] = tier
    r = requests.post(f"{API}/auth/register", json=body)
    if r.status_code == 201:
        CREATED["users"].append(r.json()["user"]["id"])
    return r


def buy(tok, event_id, qty=1, code=None):
    body = {"event_id": event_id, "quantity": qty}
    if code:
        body["promoter_code"] = code
    r = requests.post(f"{API}/tickets/purchase", json=body, headers=h(tok))
    if r.status_code == 201:
        CREATED["tickets"].append(r.json()["id"])
    return r


# --- Auth & membership tiers ---
class TestAuth:
    def test_login_all_seeded(self):
        for c, role in [(GUEST, "guest"), (PROMOTER, "promoter"), (VENUE, "venue_owner"), (ADMIN, "admin")]:
            d = login(c)
            assert d["access_token"] and d["user"]["role"] == role and "password_hash" not in d["user"]

    def test_login_wrong_password_and_me(self, guest):
        assert requests.post(f"{API}/auth/login", json={"email": GUEST[0], "password": "nope"}).status_code == 401
        assert requests.get(f"{API}/auth/me").status_code == 401
        r = requests.get(f"{API}/auth/me", headers=h(guest["access_token"]))
        assert r.status_code == 200 and r.json()["email"] == GUEST[0]

    def test_register_self_serve_tiers(self):
        for tier in ["free_girl", "trial_male", "member"]:
            r = register("guest", tier)
            assert r.status_code == 201, r.text
            assert r.json()["user"]["membership_tier"] == tier

    def test_register_paid_tiers_rejected(self):
        for tier in ["premium", "corporate", "venue", "bogus"]:
            assert register("guest", tier).status_code == 400, tier

    def test_register_venue_owner_forced_venue_tier(self):
        r = register("venue_owner", "corporate")
        assert r.status_code == 201, r.text
        assert r.json()["user"]["membership_tier"] == "venue"

    def test_register_admin_and_duplicate(self):
        assert register("admin").status_code == 400
        r = register("promoter")
        assert r.status_code == 201
        dup = requests.post(f"{API}/auth/register", json={"email": r.json()["user"]["email"], "password": "Passw0rd!", "full_name": "x"})
        assert dup.status_code == 409


# --- Venues / Events ---
class TestCatalog:
    def test_venues_search_and_regex_escape(self):
        vs = requests.get(f"{API}/venues").json()
        v = vs[0]
        s = requests.get(f"{API}/venues", params={"q": v["name"][:3]})
        assert s.status_code == 200 and any(x["id"] == v["id"] for x in s.json())
        for q in ["(", "[", "*", ".*"]:
            r = requests.get(f"{API}/venues", params={"q": q})
            assert r.status_code == 200 and r.json() == [], q
        assert requests.get(f"{API}/venues/does-not-exist").status_code == 404

    def test_events_have_filterable_tags(self):
        evs = requests.get(f"{API}/events").json()
        tags = {t for e in evs for t in e["tags"]}
        print("event tags:", tags)
        assert {"VIP", "DJ", "Open Bar"} & tags


# --- Tickets ---
class TestTickets:
    def test_purchase_with_marco1(self, guest, promoter, event):
        before = requests.get(f"{API}/auth/me", headers=h(promoter["access_token"])).json()["wallet_balance"]
        r = buy(guest["access_token"], event["id"], 2, "marco1")
        assert r.status_code == 201, r.text
        t = r.json()
        base = event["price"] * 2
        assert t["platform_fee"] == pytest.approx(round(base * 0.15, 2), abs=0.01)
        assert t["total_paid"] == pytest.approx(round(base * 1.15, 2), abs=0.01)
        assert t["promoter_earning"] == pytest.approx(round(t["platform_fee"] * 0.4, 2), abs=0.01)
        assert t["promoter_id"] == promoter["user"]["id"]
        WALLET_DELTA["promoter"] += t["promoter_earning"]
        after = requests.get(f"{API}/auth/me", headers=h(promoter["access_token"])).json()["wallet_balance"]
        assert after == pytest.approx(before + t["promoter_earning"], abs=0.02)
        assert any(x["id"] == t["id"] for x in requests.get(f"{API}/tickets/mine", headers=h(guest["access_token"])).json())

    def test_quantity_bounds(self, guest, event):
        # seeded events have plus_one_limit 3 -> max 4 per guest; 8 is now rejected by design
        for q in [0, -1, 9, 100, 8, 5]:
            assert buy(guest["access_token"], event["id"], q).status_code == 400, q
        assert buy(guest["access_token"], event["id"], 4).status_code == 201

    def test_past_event_rejected(self, guest, venue_owner):
        vid = bronze_venue_id()
        body = {"title": "TEST_PastEvent", "venue_id": vid, "date": future(-2), "price": 10, "image_url": "https://example.com/x.jpg", "description": "TEST"}
        assert requests.post(f"{API}/events", json=body, headers=h(guest["access_token"])).status_code == 403
        r = requests.post(f"{API}/events", json=body, headers=h(venue_owner["access_token"]))
        assert r.status_code == 400, r.text
        assert buy(guest["access_token"], "nope").status_code == 404

    def test_self_referral_no_earnings(self, promoter, event):
        before = requests.get(f"{API}/auth/me", headers=h(promoter["access_token"])).json()["wallet_balance"]
        r = buy(promoter["access_token"], event["id"], 1, "MARCO1")
        assert r.status_code == 201, r.text
        assert r.json()["promoter_id"] is None and r.json()["promoter_earning"] == 0
        after = requests.get(f"{API}/auth/me", headers=h(promoter["access_token"])).json()["wallet_balance"]
        assert after == pytest.approx(before, abs=0.001)


    def test_withdraw_validation_and_atomic(self, promoter):
        tok = promoter["access_token"]
        bal = requests.get(f"{API}/auth/me", headers=h(tok)).json()["wallet_balance"]
        for amt in [bal + 1000, 2, 1.5, -5, 0]:
            assert requests.post(f"{API}/promoter/withdraw", json={"amount": amt}, headers=h(tok)).status_code == 400, amt
        if bal >= 3:
            CREATED["withdrawal_users"].append((promoter["user"]["id"], datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)))
            r = requests.post(f"{API}/promoter/withdraw", json={"amount": 3}, headers=h(tok))
            assert r.status_code == 200 and r.json() == {"withdrawn": 3, "fee": 2.0, "net": 1.0}
            WALLET_DELTA["promoter"] -= 3
            assert requests.get(f"{API}/auth/me", headers=h(tok)).json()["wallet_balance"] == pytest.approx(bal - 3, abs=0.01)


# --- Check-in ---
class TestCheckin:
    def test_short_code_checkin(self, guest, promoter, event):
        t = buy(guest["access_token"], event["id"]).json()
        short = "#" + t["id"][:8].upper()
        assert requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(guest["access_token"])).status_code == 403
        c = requests.post(f"{API}/tickets/{short}/checkin", headers=h(promoter["access_token"]))
        # NOTE: '#' in a URL path is a fragment; clients must URL-encode it. Test raw short code too.
        if c.status_code != 200:
            print("raw '#' path status:", c.status_code)
            c = requests.post(f"{API}/tickets/%23{t['id'][:8].upper()}/checkin", headers=h(promoter["access_token"]))
        assert c.status_code == 200, c.text
        assert c.json()["checked_in"] is True and c.json()["id"] == t["id"]
        again = requests.post(f"{API}/tickets/{t['id'][:8].lower()}/checkin", headers=h(promoter["access_token"]))
        assert again.status_code == 400

    def test_full_id_checkin_and_double(self, guest, promoter, event):
        t = buy(guest["access_token"], event["id"]).json()
        assert requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(promoter["access_token"])).status_code == 200
        assert requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(promoter["access_token"])).status_code == 400
        mine = [x for x in requests.get(f"{API}/tickets/mine", headers=h(guest["access_token"])).json() if x["id"] == t["id"]]
        assert mine[0]["checked_in"] is True

    def test_unknown_or_too_short(self, promoter):
        for code in ["nope", "zzzzzzzz", "abc"]:
            assert requests.post(f"{API}/tickets/{code}/checkin", headers=h(promoter["access_token"])).status_code == 404, code


# --- Promoter stats / withdraw ---
class TestPromoter:
    def test_stats_and_leaderboard(self, guest, promoter):
        s = requests.get(f"{API}/promoter/stats", headers=h(promoter["access_token"]))
        assert s.status_code == 200
        d = s.json()
        assert d["referral_code"] == "MARCO1" and d["tickets_sold"] >= 2 and d["rank"] >= 1
        assert requests.get(f"{API}/promoter/stats", headers=h(guest["access_token"])).status_code == 403
        lb = requests.get(f"{API}/promoter/leaderboard")
        assert lb.status_code == 200 and any(x["user_id"] == promoter["user"]["id"] for x in lb.json())

    def test_withdraw_guest_role(self, guest):
        # iteration_1 asked to restrict withdraw to promoter-type roles
        r = requests.post(f"{API}/promoter/withdraw", json={"amount": 5}, headers=h(guest["access_token"]))
        print("guest withdraw status:", r.status_code, r.text)
        assert r.status_code in (400, 403)


# --- Reservations ---
class TestReservations:
    @pytest.mark.parametrize("svc,price", [("table", 200.0), ("booth", 400.0), ("bottle", 800.0)])
    def test_server_side_price(self, guest, svc, price):
        vid = bronze_venue_id()
        body = {"venue_id": vid, "date": future(), "party_size": 4, "service_type": svc, "base_price": 1, "notes": "TEST_res"}
        r = requests.post(f"{API}/reservations", json=body, headers=h(guest["access_token"]))
        assert r.status_code == 201, r.text
        d = r.json()
        CREATED["reservations"].append(d["id"])
        assert d["base_price"] == price and d["platform_fee"] == round(price * 0.25, 2) and d["total"] == round(price * 1.25, 2)  # bronze 25% concierge fee
        assert any(x["id"] == d["id"] for x in requests.get(f"{API}/reservations/mine", headers=h(guest["access_token"])).json())

    def test_validation(self, guest):
        vid = bronze_venue_id()
        base = {"venue_id": vid, "date": future(), "party_size": 4, "service_type": "table", "base_price": 200}
        tok = h(guest["access_token"])
        assert requests.post(f"{API}/reservations", json={**base, "service_type": "x"}, headers=tok).status_code == 400
        for p in [0, -3, 31]:
            assert requests.post(f"{API}/reservations", json={**base, "party_size": p}, headers=tok).status_code == 400, p
        assert requests.post(f"{API}/reservations", json={**base, "venue_id": "nope"}, headers=tok).status_code == 404
        assert requests.post(f"{API}/reservations", json=base).status_code == 401

    def test_base_price_optional(self, guest):
        # base_price is ignored server-side, so clients should not be forced to send it
        vid = bronze_venue_id()
        r = requests.post(f"{API}/reservations", json={"venue_id": vid, "date": future(), "party_size": 2, "service_type": "table"},
                          headers=h(guest["access_token"]))
        if r.status_code == 201:
            CREATED["reservations"].append(r.json()["id"])
        print("no base_price status:", r.status_code)
        assert r.status_code == 201
