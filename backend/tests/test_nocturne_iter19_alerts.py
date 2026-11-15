"""Iteration 19: door rush (check-in milestones), waitlist spot alerts, VIP table upsell, weekly promoter recap,
push-prefs door_rush/table_offers. Push relay monkeypatched in-process (routes.push.send_push).
All data TEST_-prefixed and removed by id at module teardown; settings doc promoter_recap restored."""
import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import run

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "events": [], "tickets": [], "requests": [], "bookings": []}
SENT = []
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def register(role="guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_al_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": "TEST_ Alerts User", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def mk_event(**kw):
    doc = {"id": str(uuid.uuid4()), "title": f"TEST_ Alerts {uuid.uuid4().hex[:4]}", "venue_id": None,
           "venue_name": "TEST_ Venue", "city": "Los Angeles", "date": NOW() + timedelta(hours=5), "price": 0,
           "tags": [], "tickets_sold": 0, "created_at": NOW(), "min_level": "bronze", "approval_required": False,
           "capacity": 100, "plus_one_limit": 7, "tables": [], "created_by": None, "image_url": ""}
    doc.update(kw)
    DB.events.insert_one(dict(doc))
    C["events"].append(doc["id"])
    return doc


def mk_ticket(ev, uid, qty=1, **kw):
    doc = {"id": str(uuid.uuid4()), "event_id": ev["id"], "event_title": ev["title"], "event_date": ev["date"],
           "venue_name": ev["venue_name"], "user_id": uid, "promoter_id": None, "quantity": qty, "total_paid": 0.0,
           "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
           "checked_in": False, "created_at": NOW()}
    doc.update(kw)
    DB.tickets.insert_one(dict(doc))
    C["tickets"].append(doc["id"])
    return doc


def mk_request(ev, uid, qty=1, kind="waitlist"):
    doc = {"id": str(uuid.uuid4()), "event_id": ev["id"], "event_title": ev["title"], "user_id": uid,
           "user_name": "TEST_", "user_level": "bronze", "quantity": qty, "kind": kind, "status": "pending",
           "note": "", "promoter_code": None, "created_at": NOW()}
    DB.event_requests.insert_one(dict(doc))
    C["requests"].append(doc["id"])
    return doc


TABLES = [{"id": "T1", "name": "T1", "section": "Main", "capacity": 6, "min_spend": 300.0, "x": 10, "y": 10, "min_level": "bronze"},
          {"id": "V1", "name": "V1", "section": "VIP", "capacity": 8, "min_spend": 900.0, "x": 50, "y": 50, "min_level": "gold"}]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    saved = DB.settings.find_one({"_id": "promoter_recap"})
    yield
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.event_requests.delete_many({"id": {"$in": C["requests"]}})
    DB.table_bookings.delete_many({"id": {"$in": C["bookings"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.points_ledger.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})
    if saved is None:
        DB.settings.delete_one({"_id": "promoter_recap"})
    else:
        DB.settings.replace_one({"_id": "promoter_recap"}, saved, upsert=True)


@pytest.fixture(scope="module")
def mods():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from routes import alerts, push

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    orig = push.send_push
    push.send_push = fake_send
    yield alerts, push
    push.send_push = orig


async def _drain(push):
    while push._tasks:
        await asyncio.gather(*list(push._tasks), return_exceptions=True)


def call(mods, coro):
    async def go():
        r = await coro
        await _drain(mods[1])
        return r
    return run(go())


def keys():
    return [s["key"] for s in SENT]


# ---------- Push prefs ----------
class TestPushPrefs:
    def test_defaults_and_partial_update(self):
        u = register()
        r = requests.get(f"{API}/me/push-prefs", headers=h(u))
        assert r.status_code == 200
        d = r.json()
        assert d["door_rush"] is True and d["table_offers"] is True
        assert set(d) == {"event_night", "updates", "concierge", "sales", "door_rush", "table_offers"}
        r = requests.put(f"{API}/me/push-prefs", headers=h(u), json={"door_rush": False})
        assert r.status_code == 200 and r.json()["door_rush"] is False and r.json()["table_offers"] is True
        r = requests.put(f"{API}/me/push-prefs", headers=h(u), json={"table_offers": False})
        g = requests.get(f"{API}/me/push-prefs", headers=h(u)).json()
        assert g == {"event_night": True, "updates": True, "concierge": True, "sales": True,
                     "door_rush": False, "table_offers": False}

    def test_requires_auth(self):
        assert requests.get(f"{API}/me/push-prefs").status_code in (401, 403)


# ---------- Door rush ----------
class TestDoorRush:
    def test_checkin_endpoint_fast_and_ok(self):
        host = register("venue_owner")
        g = register()
        ev = mk_event(created_by=host["user"]["id"])
        t = mk_ticket(ev, g["user"]["id"], qty=2)
        t0 = time.time()
        r = requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(host))
        dt = time.time() - t0
        assert r.status_code == 200, r.text
        assert r.json()["checked_in"] is True
        assert dt < 3, f"check-in slow {dt:.2f}s"
        r2 = requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(host))
        assert r2.status_code == 400

    def test_first_and_milestones(self, mods):
        alerts, _ = mods
        host = register("venue_owner")
        hid = host["user"]["id"]
        ev = mk_event(created_by=hid, capacity=200)
        g = register()["user"]["id"]
        mk_ticket(ev, g, qty=2, checked_in=True)
        SENT.clear()
        call(mods, alerts.door_rush(ev["id"], 2, 2))
        assert keys() == [f"door-{ev['id']}-first"], SENT
        assert SENT[0]["recipients"] == [hid]
        assert "1%" in SENT[0]["data"]["message"]
        assert SENT[0]["data"]["action_url"] == f"/host/event/{ev['id']}"
        # 2 -> 20 : no milestone
        mk_ticket(ev, g, qty=18, checked_in=True)
        SENT.clear()
        call(mods, alerts.door_rush(ev["id"], 18, 20))
        assert SENT == []
        # 20 -> 26 crosses 25
        mk_ticket(ev, g, qty=6, checked_in=True)
        call(mods, alerts.door_rush(ev["id"], 6, 26))
        assert keys() == [f"door-{ev['id']}-1"]
        assert SENT[0]["data"]["title"] == "26 guests in"
        # 26 -> 60 crosses 50 (mark 2)
        mk_ticket(ev, g, qty=34, checked_in=True)
        SENT.clear()
        call(mods, alerts.door_rush(ev["id"], 34, 60))
        assert keys() == [f"door-{ev['id']}-2"]

    def test_venue_owner_and_creator_both_notified(self, mods):
        alerts, _ = mods
        venue = DB.venues.find_one({"owner_id": {"$exists": True}}, {"_id": 0, "id": 1, "owner_id": 1})
        if not venue:
            pytest.skip("no venue")
        creator = register("promoter")["user"]["id"]
        ev = mk_event(venue_id=venue["id"], created_by=creator)
        mk_ticket(ev, register()["user"]["id"], checked_in=True)
        SENT.clear()
        call(mods, alerts.door_rush(ev["id"], 1, 1))
        assert len(SENT) == 1 and set(SENT[0]["recipients"]) == {venue["owner_id"], creator}

    def test_muted_host_skipped(self, mods):
        alerts, _ = mods
        host = register("venue_owner")
        requests.put(f"{API}/me/push-prefs", headers=h(host), json={"door_rush": False})
        ev = mk_event(created_by=host["user"]["id"])
        mk_ticket(ev, register()["user"]["id"], checked_in=True)
        SENT.clear()
        call(mods, alerts.door_rush(ev["id"], 1, 1))
        assert SENT == []


# ---------- Waitlist spots ----------
class TestWaitlistSpots:
    def test_spot_alerts(self, mods):
        alerts, _ = mods
        ev = mk_event(date=NOW() + timedelta(days=2), capacity=10, tickets_sold=8)
        ok = mk_request(ev, register()["user"]["id"], qty=2)
        too_big = mk_request(ev, register()["user"]["id"], qty=3)
        has_ticket_uid = register()["user"]["id"]
        mk_ticket(ev, has_ticket_uid)
        has_ticket = mk_request(ev, has_ticket_uid, qty=1)
        appr = mk_event(date=NOW() + timedelta(days=2), capacity=10, tickets_sold=0, approval_required=True)
        appr_req = mk_request(appr, register()["user"]["id"], qty=1)
        past = mk_event(date=NOW() - timedelta(hours=3), capacity=10, tickets_sold=0)
        past_req = mk_request(past, register()["user"]["id"], qty=1)
        SENT.clear()
        n = call(mods, alerts.send_waitlist_spots())
        ks = keys()
        assert f"spot-{ok['id']}" in ks
        for r in (too_big, has_ticket, appr_req, past_req):
            assert f"spot-{r['id']}" not in ks
        s = next(x for x in SENT if x["key"] == f"spot-{ok['id']}")
        assert s["data"]["action_url"] == f"/event/{ev['id']}" and s["recipients"] == [ok["user_id"]]
        assert n >= 1
        assert DB.event_requests.find_one({"id": ok["id"]})["spot_alert_sent"] is True
        assert DB.event_requests.find_one({"id": too_big["id"]}).get("spot_alert_sent") is None
        SENT.clear()
        call(mods, alerts.send_waitlist_spots())
        assert f"spot-{ok['id']}" not in keys()  # only once


# ---------- Table upsell ----------
class TestTableOffers:
    def test_offers(self, mods):
        alerts, _ = mods
        ev = mk_event(tables=TABLES)
        g_ok = register()["user"]["id"]
        t_ok = mk_ticket(ev, g_ok)
        g_booked = register()["user"]["id"]
        t_booked = mk_ticket(ev, g_booked)
        b = {"id": str(uuid.uuid4()), "event_id": ev["id"], "table_id": "T1-x", "user_id": g_booked,
             "status": "confirmed", "created_at": NOW()}
        DB.table_bookings.insert_one(dict(b))
        C["bookings"].append(b["id"])
        soon = mk_event(date=NOW() + timedelta(hours=1), tables=TABLES)
        t_soon = mk_ticket(soon, register()["user"]["id"])
        gold_only = mk_event(tables=[TABLES[1]])
        t_gold = mk_ticket(gold_only, register()["user"]["id"])
        no_tables = mk_event()
        t_none = mk_ticket(no_tables, register()["user"]["id"])
        SENT.clear()
        call(mods, alerts.send_table_offers())
        ks = keys()
        assert f"upsell-{t_ok['id']}" in ks
        for t in (t_booked, t_soon, t_gold, t_none):
            assert f"upsell-{t['id']}" not in ks
        s = next(x for x in SENT if x["key"] == f"upsell-{t_ok['id']}")
        assert s["data"]["action_url"] == f"/event/{ev['id']}"
        assert "1 table left from $300" in s["data"]["message"], s["data"]["message"]
        assert DB.tickets.find_one({"id": t_ok["id"]})["table_offer_sent"] is True
        SENT.clear()
        call(mods, alerts.send_table_offers())
        assert f"upsell-{t_ok['id']}" not in keys()

    def test_all_booked_and_muted(self, mods):
        alerts, _ = mods
        ev = mk_event(tables=[TABLES[0]])
        other = register()["user"]["id"]
        b = {"id": str(uuid.uuid4()), "event_id": ev["id"], "table_id": "T1", "user_id": other,
             "status": "confirmed", "created_at": NOW()}
        DB.table_bookings.insert_one(dict(b))
        C["bookings"].append(b["id"])
        t1 = mk_ticket(ev, register()["user"]["id"])
        ev2 = mk_event(tables=TABLES)
        mu = register()
        requests.put(f"{API}/me/push-prefs", headers=h(mu), json={"table_offers": False})
        t2 = mk_ticket(ev2, mu["user"]["id"])
        SENT.clear()
        call(mods, alerts.send_table_offers())
        assert f"upsell-{t1['id']}" not in keys() and f"upsell-{t2['id']}" not in keys()


# ---------- Weekly promoter recap ----------
class TestPromoterRecap:
    def test_force_recap(self, mods):
        alerts, _ = mods
        p = register("promoter")["user"]["id"]
        quiet = register("promoter")["user"]["id"]
        ev = mk_event(date=NOW() + timedelta(days=3))
        mk_ticket(ev, register()["user"]["id"], qty=3, promoter_id=p, promoter_earning=12.5)
        SENT.clear()
        n = call(mods, alerts.send_promoter_recap(force=True))
        by = {s["recipients"][0]: s for s in SENT}
        assert p in by and quiet in by
        assert n == DB.users.count_documents({"role": "promoter"})
        m = by[p]["data"]["message"]
        assert m.startswith("Last week: 3 guests · $12.50 earned · #") and "this month" in m, m
        assert by[quiet]["data"]["message"].startswith("Quiet week")
        assert by[p]["data"]["action_url"] == "/(tabs)/promote"
        assert by[p]["key"].startswith(f"recap-{NOW().strftime('%G-W%V')}-")

    def test_schedule_gate_and_once_per_week(self, mods, monkeypatch):
        alerts, _ = mods
        sunday = datetime(2020, 1, 5, 18, tzinfo=timezone.utc)
        monday_early = datetime(2020, 1, 6, 10, tzinfo=timezone.utc)
        monday = datetime(2020, 1, 6, 17, tzinfo=timezone.utc)
        for t in (sunday, monday_early):
            monkeypatch.setattr(alerts, "_now", lambda t=t: t)
            SENT.clear()
            assert call(mods, alerts.send_promoter_recap()) == 0 and SENT == []
        monkeypatch.setattr(alerts, "_now", lambda: monday)
        SENT.clear()
        assert call(mods, alerts.send_promoter_recap()) >= 1
        assert DB.settings.find_one({"_id": "promoter_recap"})["week"] == "2020-W02"
        SENT.clear()
        assert call(mods, alerts.send_promoter_recap()) == 0 and SENT == []
