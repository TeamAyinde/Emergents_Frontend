"""Iteration 17: POST /api/register-push validation + fire-and-forget push hooks never break the main action.
All test data is TEST_-prefixed and removed by id at module teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import grant_credit

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "requests": [], "tickets": [], "messages": [], "threads": [], "reservations": [], "sessions": [], "bookings": []}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return r.json()


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for t in DB.tickets.find({"$or": [{"id": {"$in": C["tickets"]}}, {"user_id": {"$in": C["users"]}}]}):
        DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
        DB.tickets.delete_one({"id": t["id"]})
    DB.event_requests.delete_many({"id": {"$in": C["requests"]}})
    DB.concierge_messages.delete_many({"member_id": {"$in": C["users"]}})
    DB.concierge_threads.delete_many({"member_id": {"$in": C["users"]}})
    DB.reservations.delete_many({"id": {"$in": C["reservations"]}})
    DB.table_bookings.delete_many({"id": {"$in": C["bookings"]}})
    DB.venue_payables.delete_many({"record_id": {"$in": C["reservations"] + C["bookings"] + C["tickets"]}})
    DB.payment_transactions.delete_many({"$or": [{"session_id": {"$in": C["sessions"]}}, {"user_id": {"$in": C["users"]}}]})
    DB.points_ledger.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def member():
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_push_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Push", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    grant_credit(u["user"]["id"], 20000)
    return u


@pytest.fixture(scope="module")
def owner():
    return login("venue@nocturne.app", "VenuePass123!")


@pytest.fixture(scope="module")
def admin():
    return login("admin@nocturne.app", "AdminPass123!")


# register-push validation
class TestRegisterPush:
    def test_requires_auth(self):
        r = requests.post(f"{API}/register-push", json={"user_id": "x", "platform": "ios", "device_token": "t"})
        assert r.status_code in (401, 403), r.text

    def test_other_user_403(self, member):
        r = requests.post(f"{API}/register-push", json={"user_id": "someone-else", "platform": "ios", "device_token": "t"}, headers=h(member))
        assert r.status_code == 403 and "own device" in r.json()["detail"]

    def test_bad_platform_400(self, member):
        r = requests.post(f"{API}/register-push", json={"user_id": member["user"]["id"], "platform": "web", "device_token": "t"}, headers=h(member))
        assert r.status_code == 400 and "android or ios" in r.json()["detail"]

    def test_missing_field_422(self, member):
        r = requests.post(f"{API}/register-push", json={"user_id": member["user"]["id"], "platform": "ios"}, headers=h(member))
        assert r.status_code == 422

    def test_valid_body_reaches_relay(self, member):
        # preview key is a placeholder -> relay 401 -> 500 'EMERGENT_PUSH_KEY missing or invalid' (expected in preview)
        r = requests.post(f"{API}/register-push", json={"user_id": member["user"]["id"], "platform": "android", "device_token": "TEST_tok"}, headers=h(member))
        assert r.status_code in (201, 500), r.text
        if r.status_code == 500:
            assert r.json()["detail"] == "EMERGENT_PUSH_KEY missing or invalid"
        else:
            assert r.json() == {"status": "registered"}


# push hooks are fire-and-forget: main action still succeeds
class TestPushHooks:
    def test_join_pending_then_approve(self, member, owner):
        ev = next((e for e in requests.get(f"{API}/events").json() if e["title"] == "Industry Fridays"), None)
        if not ev:
            pytest.skip("Industry Fridays not seeded")
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1, "note": "TEST_push"}, headers=h(member))
        assert r.status_code == 200 and r.json()["result"] == "pending", r.text
        rid = r.json()["request"]["id"]
        C["requests"].append(rid)
        r = requests.post(f"{API}/host/requests/{rid}", json={"action": "approve"}, headers=h(owner))
        assert r.status_code == 200 and r.json()["status"] == "approved", r.text
        mine = requests.get(f"{API}/tickets/mine", headers=h(member)).json()
        C["tickets"] += [t["id"] for t in mine if t["event_id"] == ev["id"]]

    def test_admin_concierge_reply(self, member, admin):
        r = requests.post(f"{API}/concierge/messages", json={"text": "TEST_ push ping"}, headers=h(member))
        assert r.status_code == 201
        r = requests.post(f"{API}/admin/concierge/{member['user']['id']}/messages", json={"text": "TEST_ reply"}, headers=h(admin))
        assert r.status_code == 201 and r.json()["sender"] == "concierge", r.text
        assert requests.get(f"{API}/concierge/unread", headers=h(member)).json()["unread"] >= 1  # auto-welcome + reply

    def test_reservation_save(self, member):
        venues = requests.get(f"{API}/venues").json()
        vid = next((v["id"] for v in venues if v.get("min_level", "bronze") == "bronze"), None) or pytest.skip("no bronze venue")
        date = (datetime.now(timezone.utc) + timedelta(days=12)).isoformat()
        r = requests.post(f"{API}/payments/checkout", json={"kind": "reservation", "origin_url": BASE_URL, "venue_id": vid, "date": date,
                                                             "party_size": 2, "service_type": "table", "notes": "TEST_push"}, headers=h(member))
        assert r.status_code == 200 and r.json()["paid_with_credit"] is True, r.text
        C["reservations"].append(r.json()["result_id"]); C["sessions"].append(r.json()["session_id"])
        assert any(x["id"] == r.json()["result_id"] for x in requests.get(f"{API}/reservations/mine", headers=h(member)).json())

    def test_table_booking_save(self, member):
        ev = next((e for e in requests.get(f"{API}/events").json() if e["title"] == "Velvet Sessions w/ DJ Nyx"), None)
        if not ev:
            pytest.skip("Velvet Sessions not seeded")
        free = [t for t in requests.get(f"{API}/events/{ev['id']}/tables").json() if not t["booked"] and t["min_level"] == "bronze"]
        if not free:
            pytest.skip("no free bronze table")
        t = free[-1]
        r = requests.post(f"{API}/payments/checkout", json={"kind": "table", "origin_url": BASE_URL, "event_id": ev["id"],
                                                             "table_id": t["id"], "party_size": 2}, headers=h(member))
        assert r.status_code == 200 and r.json()["paid_with_credit"] is True, r.text
        C["bookings"].append(r.json()["result_id"]); C["sessions"].append(r.json()["session_id"])
        assert any(b["id"] == r.json()["result_id"] for b in requests.get(f"{API}/table-bookings/mine", headers=h(member)).json())
