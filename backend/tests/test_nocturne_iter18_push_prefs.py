"""Iteration 18: push preferences (GET/PUT /api/me/push-prefs), event-night alerts (send_night_alerts),
promoter sale push (issue_ticket, kind 'sales'), notify() muting. Push relay is monkeypatched in-process.
All data TEST_-prefixed; removed by id at module teardown. Promoter wallet_balance restored to saved value."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import grant_credit, run

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "tickets": [], "inserted_tickets": []}
SENT = []  # captured send_push calls


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return r.json()


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def register(role="guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_pp_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": "TEST_ Prefs User", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    promo = DB.users.find_one({"email": "promoter@nocturne.app"}, {"_id": 0, "wallet_balance": 1})
    saved_wallet = (promo or {}).get("wallet_balance", 0.0)
    yield
    for t in DB.tickets.find({"$or": [{"id": {"$in": C["tickets"]}}, {"user_id": {"$in": C["users"]}}]}):
        if t["id"] not in C["inserted_tickets"]:
            DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
        DB.tickets.delete_one({"id": t["id"]})
    DB.venue_payables.delete_many({"record_id": {"$in": C["tickets"]}})
    DB.points_ledger.delete_many({"user_id": {"$in": C["users"]}})
    DB.payment_transactions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})
    DB.users.update_one({"email": "promoter@nocturne.app"}, {"$set": {"wallet_balance": saved_wallet}})


@pytest.fixture(scope="module")
def push_mod():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from routes import push

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    orig = push.send_push
    push.send_push = fake_send
    yield push
    push.send_push = orig


async def _drain(push):
    while push._tasks:
        await asyncio.gather(*list(push._tasks), return_exceptions=True)


@pytest.fixture(scope="module")
def member():
    return register()


# ---- GET/PUT /api/me/push-prefs ----
class TestPushPrefsAPI:
    def test_requires_auth(self):
        assert requests.get(f"{API}/me/push-prefs").status_code in (401, 403)
        assert requests.put(f"{API}/me/push-prefs", json={"sales": False}).status_code in (401, 403)

    def test_defaults_all_true(self, member):
        r = requests.get(f"{API}/me/push-prefs", headers=h(member))
        assert r.status_code == 200, r.text
        assert r.json() == {"event_night": True, "updates": True, "concierge": True, "sales": True}

    def test_partial_put_persists(self, member):
        r = requests.put(f"{API}/me/push-prefs", json={"event_night": False}, headers=h(member))
        assert r.status_code == 200, r.text
        assert r.json() == {"event_night": False, "updates": True, "concierge": True, "sales": True}
        r = requests.put(f"{API}/me/push-prefs", json={"concierge": False}, headers=h(member))
        assert r.json() == {"event_night": False, "updates": True, "concierge": False, "sales": True}
        g = requests.get(f"{API}/me/push-prefs", headers=h(member)).json()
        assert g == {"event_night": False, "updates": True, "concierge": False, "sales": True}
        doc = DB.users.find_one({"id": member["user"]["id"]}, {"_id": 0, "push_prefs": 1})
        assert doc["push_prefs"]["event_night"] is False and doc["push_prefs"]["concierge"] is False

    def test_empty_put_no_change(self, member):
        r = requests.put(f"{API}/me/push-prefs", json={}, headers=h(member))
        assert r.status_code == 200
        assert r.json()["event_night"] is False and r.json()["updates"] is True

    def test_invalid_type_422(self, member):
        r = requests.put(f"{API}/me/push-prefs", json={"sales": "nope"}, headers=h(member))
        assert r.status_code == 422

    def test_full_put_restore(self, member):
        body = {"event_night": True, "updates": True, "concierge": True, "sales": True}
        assert requests.put(f"{API}/me/push-prefs", json=body, headers=h(member)).json() == body


# ---- send_night_alerts() ----
class TestNightAlerts:
    def _ticket(self, uid, delta, title="TEST_ Night Event"):
        now = datetime.now(timezone.utc)
        tid = f"TEST_{uuid.uuid4()}"
        DB.tickets.insert_one({"id": tid, "event_id": "TEST_ev", "event_title": title, "event_date": now + delta,
                               "venue_name": "TEST_ Venue", "user_id": uid, "quantity": 1, "checked_in": False,
                               "created_at": now})
        C["tickets"].append(tid); C["inserted_tickets"].append(tid)
        return tid

    def test_alerts_window_idempotent_and_muted(self, push_mod):
        on = register(); muted = register()
        requests.put(f"{API}/me/push-prefs", json={"event_night": False}, headers=h(muted))
        t_in = self._ticket(on["user"]["id"], timedelta(minutes=90))
        t_muted = self._ticket(muted["user"]["id"], timedelta(minutes=30))
        t_far = self._ticket(on["user"]["id"], timedelta(hours=3))
        t_past = self._ticket(on["user"]["id"], timedelta(minutes=-10))
        SENT.clear()

        async def go():
            n = await push_mod.send_night_alerts()
            await _drain(push_mod)
            return n
        run(go())
        mine = [s for s in SENT if s["key"] in (f"night-{t_in}", f"night-{t_muted}")]
        assert len(mine) == 1, SENT
        s = mine[0]
        assert s["recipients"] == [on["user"]["id"]]
        assert s["data"]["action_url"] == f"/ticket/{t_in}"
        assert s["data"]["title"] == "Tonight: TEST_ Night Event"
        assert "Doors open in 1h" in s["data"]["message"] and "TEST_ Venue" in s["data"]["message"]
        assert DB.tickets.find_one({"id": t_in})["night_alert_sent"] is True
        assert DB.tickets.find_one({"id": t_muted})["night_alert_sent"] is True  # claimed but not pushed
        assert not DB.tickets.find_one({"id": t_far}).get("night_alert_sent")
        assert not DB.tickets.find_one({"id": t_past}).get("night_alert_sent")
        # second round: nothing new for these tickets
        SENT.clear()
        run(go())
        assert not [x for x in SENT if x["key"] and x["key"].startswith("night-TEST_")], SENT


# ---- notify() muting ----
class TestNotifyMute:
    def test_muted_kind_skipped(self, push_mod):
        a = register(); b = register()
        requests.put(f"{API}/me/push-prefs", json={"updates": False}, headers=h(b))
        SENT.clear()

        async def go():
            push_mod.notify([a["user"]["id"], b["user"]["id"]], "TEST_ t", "TEST_ m", "/x", key="TEST_k1", kind="updates")
            push_mod.notify([b["user"]["id"]], "TEST_ t", "TEST_ m", key="TEST_k2", kind="updates")
            push_mod.notify([b["user"]["id"]], "TEST_ t", "TEST_ m", key="TEST_k3", kind="concierge")
            await _drain(push_mod)
        run(go())
        by_key = {s["key"]: s for s in SENT}
        assert by_key["TEST_k1"]["recipients"] == [a["user"]["id"]]
        assert by_key["TEST_k1"]["data"]["action_url"] == "/x"
        assert "TEST_k2" not in by_key  # all recipients muted -> no call
        assert by_key["TEST_k3"]["recipients"] == [b["user"]["id"]]  # other kinds still on


# ---- promoter sale push ----
class TestPromoterSale:
    def _event(self):
        ev = next((e for e in requests.get(f"{API}/events").json() if e["title"] == "Velvet Sessions w/ DJ Nyx"), None)
        return ev or pytest.skip("Velvet Sessions not seeded")

    def test_http_purchase_with_code_succeeds(self):
        # real server path: relay 401 in preview must not block the purchase
        buyer = register(); grant_credit(buyer["user"]["id"], 20000)
        ev = self._event()
        r = requests.post(f"{API}/tickets/purchase", json={"event_id": ev["id"], "quantity": 1, "promoter_code": "MARCO1"}, headers=h(buyer))
        assert r.status_code == 201, r.text
        t = r.json(); C["tickets"].append(t["id"])
        promo = DB.users.find_one({"email": "promoter@nocturne.app"}, {"_id": 0, "id": 1})
        assert t["promoter_id"] == promo["id"] and t["promoter_earning"] > 0

    def test_http_join_with_code_succeeds(self):
        buyer = register(); grant_credit(buyer["user"]["id"], 20000)
        ev = self._event()
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1, "promoter_code": "MARCO1"}, headers=h(buyer))
        assert r.status_code == 200 and r.json()["result"] == "ticket", r.text
        C["tickets"].append(r.json()["ticket"]["id"])
        assert r.json()["ticket"]["promoter_id"] is not None

    def test_in_process_sales_push(self, push_mod):
        import server
        buyer = register(); grant_credit(buyer["user"]["id"], 20000)
        ev = DB.events.find_one({"title": "Velvet Sessions w/ DJ Nyx"}, {"_id": 0}) or pytest.skip("no event")
        promo = DB.users.find_one({"email": "promoter@nocturne.app"}, {"_id": 0, "id": 1})
        user = DB.users.find_one({"id": buyer["user"]["id"]}, {"_id": 0})
        SENT.clear()

        async def go():
            t = await server.issue_ticket(ev, user, 2, "marco1")
            await _drain(push_mod)
            return t
        t = run(go())
        C["tickets"].append(t.id)
        s = next((x for x in SENT if x["key"] == f"sale-{t.id}"), None)
        assert s, SENT
        assert s["recipients"] == [promo["id"]]
        assert s["data"]["action_url"] == "/(tabs)/promote"
        assert "2 tickets" in s["data"]["message"] and "to your wallet" in s["data"]["message"]

    def test_no_code_no_sales_push(self, push_mod):
        import server
        buyer = register(); grant_credit(buyer["user"]["id"], 20000)
        ev = DB.events.find_one({"title": "Velvet Sessions w/ DJ Nyx"}, {"_id": 0}) or pytest.skip("no event")
        user = DB.users.find_one({"id": buyer["user"]["id"]}, {"_id": 0})
        SENT.clear()

        async def go():
            t = await server.issue_ticket(ev, user, 1, None)
            await _drain(push_mod)
            return t
        t = run(go())
        C["tickets"].append(t.id)
        assert not [x for x in SENT if x["key"] == f"sale-{t.id}"]
