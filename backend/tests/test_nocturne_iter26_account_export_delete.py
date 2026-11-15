"""Iteration 26: support email on legal pages, GET /api/me/export (download my data), DELETE /api/me (delete account)."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
EMAIL = "support@ayindetechnologies.com"
PW = "TestPass123!"
C = {"users": [], "venues": [], "docs": []}  # docs: (collection, id)
SEEDED = ["guest@nocturne.app", "promoter@nocturne.app", "venue@nocturne.app", "admin@nocturne.app"]


def register(role="guest", email=None):
    email = email or f"test_i26_{uuid.uuid4().hex[:8]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": PW, "role": role, "full_name": "TEST_ I26 User",
        "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def put(coll, doc):
    doc = {"id": f"TEST_{uuid.uuid4().hex[:10]}", **doc}
    DB[coll].insert_one(dict(doc))
    C["docs"].append((coll, doc["id"]))
    return doc["id"]


def seed_member(uid):
    """Inserts one TEST_ record per collection for the user. Returns {collection: id}."""
    now = datetime.now(timezone.utc)
    ids = {}
    base = {"user_id": uid, "email": "x@test.app", "phone": "+100", "notes": "TEST_ note", "comment": "TEST_ c", "created_at": now}
    for coll in ("tickets", "table_bookings", "reservations", "payment_transactions"):
        ids[coll] = put(coll, dict(base))
    ids["event_requests_pending"] = put("event_requests", {**base, "status": "pending"})
    ids["event_requests_approved"] = put("event_requests", {**base, "status": "approved"})
    ids["support_reports"] = put("support_reports", {"user_id": uid, "message": "TEST_ report", "created_at": now})
    ids["concierge_messages"] = put("concierge_messages", {"member_id": uid, "text": "TEST_ hi", "created_at": now})
    ids["concierge_threads"] = put("concierge_threads", {"member_id": uid, "created_at": now})
    ids["points_ledger"] = put("points_ledger", {"user_id": uid, "points": 5, "created_at": now})
    ids["perk_claims"] = put("perk_claims", {"user_id": uid, "created_at": now})
    ids["door_staff"] = put("door_staff", {"user_id": uid, "venue_id": "TEST_v", "active": True})
    ids["venue_vips"] = put("venue_vips", {"user_id": uid, "venue_id": "TEST_v", "active": True, "note": "TEST_ vip"})
    return ids


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for coll, i in C["docs"]:
        DB[coll].delete_one({"id": i})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})
    DB.deleted_accounts.delete_many({"user_id": {"$in": C["users"]}})


# --- Legal pages show support email + in-app paths -----------------------------------
class TestLegal:
    @pytest.mark.parametrize("page", ["privacy", "support"])
    def test_support_email_and_paths(self, page):
        r = requests.get(f"{API}/legal/{page}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        t = r.text
        assert f'href="mailto:{EMAIL}"' in t and f">{EMAIL}</a>" in t
        assert "Download my data" in t and "Help &amp; support" in t
        assert "Delete account" in t and "Profile → Delete account" in t


# --- Export ---------------------------------------------------------------------------
class TestExport:
    def test_unauth_401(self):
        assert requests.get(f"{API}/me/export").status_code == 401
        assert requests.get(f"{API}/me/export", headers={"Authorization": "Bearer bad"}).status_code == 401

    def test_export_only_own_data(self):
        a, b = register(), register()
        ia, ib = seed_member(a["user"]["id"]), seed_member(b["user"]["id"])
        r = requests.get(f"{API}/me/export", headers=h(a))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/json")
        assert 'attachment; filename="nocturne-my-data.json"' in r.headers.get("content-disposition", "")
        d = json.loads(r.text)
        for k in ("exported_at", "account", "tickets", "table_bookings", "reservations", "event_requests",
                  "payment_transactions", "support_reports", "concierge_messages", "concierge_threads",
                  "points_ledger", "perk_claims", "door_staff"):
            assert k in d, k
        acc = d["account"]
        assert acc["id"] == a["user"]["id"] and acc["email"] == a["user"]["email"]
        assert "password_hash" not in acc and "_id" not in acc and '"_id"' not in r.text
        for coll in ("tickets", "table_bookings", "reservations", "payment_transactions", "support_reports",
                     "concierge_messages", "points_ledger", "perk_claims", "door_staff"):
            got = {x["id"] for x in d[coll]}
            assert ia[coll] in got, coll
            assert ib[coll] not in got, coll
        assert {ia["event_requests_pending"], ia["event_requests_approved"]} <= {x["id"] for x in d["event_requests"]}
        datetime.fromisoformat(d["exported_at"].replace("Z", "+00:00"))


# --- Delete ---------------------------------------------------------------------------
class TestDelete:
    def test_unauth_and_bad_confirm(self):
        assert requests.delete(f"{API}/me", json={"confirm": "DELETE"}).status_code == 401
        u = register()
        for body in ({"confirm": "nope"}, {"confirm": ""}):
            r = requests.delete(f"{API}/me", json=body, headers=h(u))
            assert r.status_code == 400 and "DELETE" in r.json()["detail"]
        assert requests.delete(f"{API}/me", json={}, headers=h(u)).status_code == 422
        assert requests.get(f"{API}/auth/me", headers=h(u)).status_code == 200  # still exists

    def test_full_delete_flow(self):
        u = register()
        uid, email = u["user"]["id"], u["user"]["email"]
        ids = seed_member(uid)
        DB.users.update_one({"id": uid}, {"$set": {"stripe_subscription_id": "sub_TEST_fake_i26"}})
        r = requests.delete(f"{API}/me", json={"confirm": " delete "}, headers=h(u))
        assert r.status_code == 200 and r.json() == {"deleted": True}, r.text
        # account gone
        assert DB.users.find_one({"id": uid}) is None
        assert requests.get(f"{API}/auth/me", headers=h(u)).status_code == 401
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": PW}).status_code == 401
        # removed
        for coll in ("support_reports", "concierge_messages", "concierge_threads", "points_ledger", "perk_claims"):
            assert DB[coll].find_one({"id": ids[coll]}) is None, coll
        # requests
        assert DB.event_requests.find_one({"id": ids["event_requests_pending"]})["status"] == "cancelled"
        assert DB.event_requests.find_one({"id": ids["event_requests_approved"]})["status"] == "approved"
        # deactivated
        ds = DB.door_staff.find_one({"id": ids["door_staff"]})
        assert ds["active"] is False and ds.get("removed_at")
        vv = DB.venue_vips.find_one({"id": ids["venue_vips"]})
        assert vv["active"] is False and vv["note"] is None
        # scrubbed but kept
        for coll in ("tickets", "table_bookings", "reservations", "payment_transactions", "event_requests"):
            key = "event_requests_approved" if coll == "event_requests" else coll
            d = DB[coll].find_one({"id": ids[key]})
            assert d is not None, coll
            assert d["user_deleted"] is True and d["user_name"] == "Deleted member", coll
            for f in ("email", "phone", "notes", "comment"):
                assert f not in d, (coll, f)
        # audit row
        audit = DB.deleted_accounts.find_one({"user_id": uid})
        assert audit and audit["role"] == "guest" and audit.get("deleted_at")
        assert "email" not in audit
        # re-register with same email
        u2 = register(email=email)
        assert u2["user"]["id"] != uid
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": PW}).status_code == 200

    def test_venue_owner_with_venue_400(self):
        u = register(role="venue_owner")
        vid = f"TEST_venue_{uuid.uuid4().hex[:8]}"
        # copy a real venue's shape so public GET /api/venues keeps validating while the TEST_ venue exists
        real = DB.venues.find_one({"id": {"$not": {"$regex": "^TEST_"}}}, {"_id": 0})
        DB.venues.insert_one({**real, "id": vid, "owner_id": u["user"]["id"], "name": "TEST_ venue i26", "rating": 0})
        C["venues"].append(vid)
        r = requests.delete(f"{API}/me", json={"confirm": "DELETE"}, headers=h(u))
        assert r.status_code == 400 and "own venues" in r.json()["detail"]
        assert DB.users.find_one({"id": u["user"]["id"]}) is not None
        DB.venues.delete_one({"id": vid})
        r = requests.delete(f"{API}/me", json={"confirm": "DELETE"}, headers=h(u))
        assert r.status_code == 200
        assert DB.users.find_one({"id": u["user"]["id"]}) is None

    def test_last_admin_400_inprocess(self):
        """Simulates 'only one admin' by patching count_documents; the seeded admin is never touched."""
        sys.path.insert(0, "/app/backend")
        from conftest import run
        import server  # noqa: F401
        from fastapi import HTTPException
        from routes import account

        fake = {"id": f"TEST_admin_{uuid.uuid4().hex[:6]}", "role": "admin", "email": "test_fake_admin@x.app"}

        class Users:
            def __init__(self, real):
                self.real = real

            async def count_documents(self, *_a, **_k):
                return 1

            def __getattr__(self, n):
                return getattr(self.real, n)

        class FakeDB:
            def __init__(self, real):
                self.real, self.users = real, Users(real.users)

            def __getattr__(self, n):
                return getattr(self.real, n)

            def __getitem__(self, n):
                return self.real[n]

        orig = account.db
        account.db = FakeDB(orig)
        try:
            with pytest.raises(HTTPException) as e:
                run(account.delete_my_account(account.DeleteIn(confirm="DELETE"), fake))
            assert e.value.status_code == 400 and "only admin" in e.value.detail
        finally:
            account.db = orig

    def test_seeded_accounts_untouched(self):
        for e in SEEDED:
            assert DB.users.find_one({"email": e}) is not None, e
