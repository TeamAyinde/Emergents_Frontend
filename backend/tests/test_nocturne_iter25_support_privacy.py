"""Iteration 25: public privacy/support pages, member problem reports (create/list/rate-limit), admin triage + push."""
import asyncio
import json
import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "reports": []}
SENT = []


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register():
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_i25_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ I25 User", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def report(u, category="bug", message="TEST_ something broke", context=None):
    body = {"category": category, "message": message}
    if context is not None:
        body["context"] = context
    r = requests.post(f"{API}/support/reports", json=body, headers=h(u))
    if r.status_code == 201:
        C["reports"].append(r.json()["id"])
    return r


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    DB.support_reports.delete_many({"id": {"$in": C["reports"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def admin():
    return login("admin@nocturne.app", "AdminPass123!")


@pytest.fixture(scope="module")
def guest():
    return login("guest@nocturne.app", "GuestPass123!")


# --- Public legal pages -------------------------------------------------------------
class TestLegalPages:
    def test_privacy_public_html(self):
        r = requests.get(f"{API}/legal/privacy")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        t = r.text
        for s in ["Privacy Policy", "What we collect", "How we use it", "Who we share it with", "Your choices &amp; rights",
                  "<h2>Age</h2>", "18", "<h2>Contact</h2>", "Nocturne"]:
            assert s in t, s

    def test_support_public_html(self):
        r = requests.get(f"{API}/legal/support")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "Common questions" in r.text and 'href="/api/legal/privacy"' in r.text and "Report a problem" in r.text


# --- Member reports -----------------------------------------------------------------
class TestReports:
    def test_unauth_401(self):
        r = requests.post(f"{API}/support/reports", json={"category": "bug", "message": "hello there"})
        assert r.status_code == 401
        assert requests.get(f"{API}/support/reports/mine").status_code == 401

    def test_validation_422(self):
        u = register()
        assert report(u, category="nope").status_code == 422
        assert report(u, message="abc").status_code == 422
        assert report(u, message="x" * 2001).status_code == 422
        assert report(u, context="c" * 81).status_code == 422

    def test_create_and_mine_only_own(self):
        a, b = register(), register()
        r = report(a, category="concierge", message="  TEST_ concierge never replied  ", context="concierge")
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["status"] == "open" and d["category"] == "concierge" and d["context"] == "concierge"
        assert d["message"] == "TEST_ concierge never replied"
        assert d["user_id"] == a["user"]["id"] and d["user_email"] == a["user"]["email"] and d["user_name"] == "TEST_ I25 User"
        assert d["resolved_at"] is None and "_id" not in d
        assert report(b, category="payment", message="TEST_ b report").status_code == 201
        mine = requests.get(f"{API}/support/reports/mine", headers=h(a)).json()
        assert [m["id"] for m in mine] == [d["id"]]
        assert DB.support_reports.find_one({"id": d["id"]})["user_id"] == a["user"]["id"]

    def test_all_categories(self):
        u = register()
        for c in ("bug", "payment", "booking", "concierge", "account", "other"):
            assert report(u, category=c, message=f"TEST_ {c} report").status_code == 201

    def test_rate_limit_429(self):
        u = register()
        codes = [report(u, message=f"TEST_ spam {i}").status_code for i in range(11)]
        assert codes[:10] == [201] * 10, codes
        assert codes[10] == 429, codes


# --- Admin triage -------------------------------------------------------------------
class TestAdmin:
    def test_non_admin_403(self, guest):
        assert requests.get(f"{API}/admin/reports", headers=h(guest)).status_code == 403
        assert requests.put(f"{API}/admin/reports/x", json={"status": "resolved"}, headers=h(guest)).status_code == 403

    def test_filter_resolve_reopen(self, admin):
        u = register()
        rid = report(u, message="TEST_ admin flow").json()["id"]
        ids = lambda s: [x["id"] for x in requests.get(f"{API}/admin/reports", params={"status": s}, headers=h(admin)).json()]
        assert rid in ids("open") and rid not in ids("resolved") and rid in ids("all")
        r = requests.put(f"{API}/admin/reports/{rid}", json={"status": "resolved"}, headers=h(admin))
        assert r.status_code == 200 and r.json()["status"] == "resolved" and r.json()["resolved_at"]
        assert rid in ids("resolved") and rid not in ids("open")
        mine = requests.get(f"{API}/support/reports/mine", headers=h(u)).json()
        assert mine[0]["status"] == "resolved"
        r = requests.put(f"{API}/admin/reports/{rid}", json={"status": "open"}, headers=h(admin))
        assert r.status_code == 200 and r.json()["status"] == "open" and r.json()["resolved_at"] is None
        assert rid in ids("open")

    def test_404_and_422(self, admin):
        assert requests.put(f"{API}/admin/reports/nope-{uuid.uuid4()}", json={"status": "resolved"}, headers=h(admin)).status_code == 404
        assert requests.get(f"{API}/admin/reports", params={"status": "x"}, headers=h(admin)).status_code == 422
        u = register()
        rid = report(u).json()["id"]
        assert requests.put(f"{API}/admin/reports/{rid}", json={"status": "closed"}, headers=h(admin)).status_code == 422


# --- Push (in-process, send_push monkeypatched) -------------------------------------
class TestPush:
    def test_push_admins_on_create_and_member_on_resolve(self, admin):
        sys.path.insert(0, "/app/backend")
        from conftest import run
        import server  # noqa: F401
        from routes import push, support

        async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
            SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

        async def drain():
            for _ in range(20):
                if not push._tasks:
                    return
                await asyncio.gather(*list(push._tasks), return_exceptions=True)

        orig = push.send_push
        push.send_push = fake_send
        try:
            u = register()
            user = DB.users.find_one({"id": u["user"]["id"]}, {"_id": 0})

            async def flow():
                out = await support.create_report(support.ReportIn(category="booking", message="TEST_ push flow"), user)
                C["reports"].append(out.id)
                await drain()
                await support.set_report_status(out.id, support.ReportStatusIn(status="resolved"), admin["user"])
                await drain()
                return out
            out = run(flow())
        finally:
            push.send_push = orig
        admin_ids = {a["id"] for a in DB.users.find({"role": "admin"}, {"id": 1})}
        new = [s for s in SENT if s["key"] == f"report-{out.id}"]
        done = [s for s in SENT if s["key"] == f"report-done-{out.id}"]
        assert len(new) == 1 and set(new[0]["recipients"]) <= admin_ids and admin["user"]["id"] in new[0]["recipients"]
        assert new[0]["data"]["action_url"] == "/admin/reports" and "booking" in new[0]["data"]["title"]
        assert len(done) == 1 and done[0]["recipients"] == [u["user"]["id"]] and done[0]["data"]["action_url"] == "/support"


# --- Store name ---------------------------------------------------------------------
def test_app_json_name():
    cfg = json.load(open("/app/frontend/app.json"))["expo"]
    assert cfg["name"] == "Nocturne" and cfg["slug"] == "frontend"
    src = open("/app/frontend/app/payout-settings.tsx").read()
    assert "Coming soon" not in src and "Payouts sent by our team" in src
