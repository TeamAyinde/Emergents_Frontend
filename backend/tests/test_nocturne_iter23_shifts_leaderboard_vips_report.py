"""Iteration 23: door shift schedule, deal leaderboard, VIP arrival alerts, monthly venue report."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from test_nocturne_iter20_live_deals import call  # drains push/email background tasks

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "events": [], "tickets": [], "venues": [], "staff": [], "payables": [], "feedback": [], "vips": []}
S = {}
SENT, MAILS = [], []
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731
SETTINGS_PRE = DB.settings.find_one({"_id": "venue_report"})


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register(role="guest", name="TEST_ I23 User"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_i23_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def mk_venue(owner_id):
    doc = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": f"TEST_ I23 Venue {uuid.uuid4().hex[:4]}", "owner_id": owner_id,
           "city": "Los Angeles", "state": "CA", "category": "Nightclub", "image_url": "", "rating": 4.5, "price_range": "$$",
           "description": "TEST_", "min_level": "bronze", "created_at": NOW()}
    DB.venues.insert_one(dict(doc))
    C["venues"].append(doc["id"])
    return doc


def mk_event(owner, venue, **kw):
    doc = {"id": str(uuid.uuid4()), "title": f"TEST_ I23 {uuid.uuid4().hex[:4]}", "venue_id": venue["id"],
           "venue_name": venue["name"], "city": "Los Angeles", "date": NOW() + timedelta(hours=5),
           "price": 0, "tags": [], "tickets_sold": 0, "created_at": NOW(), "min_level": "bronze", "approval_required": False,
           "capacity": 20, "plus_one_limit": 7, "tables": [], "created_by": owner, "image_url": "", "summary_sent": True}
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


@pytest.fixture(scope="module")
def venue():
    return login("venue@nocturne.app", "VenuePass123!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for s in DB.door_staff.find({"$or": [{"user_id": {"$in": C["users"]}}, {"venue_id": {"$in": C["venues"]}}]}, {"id": 1}):
        C["staff"].append(s["id"])
    DB.door_staff.update_many({"id": {"$in": C["staff"]}}, {"$set": {"active": False}})
    DB.door_staff.delete_many({"id": {"$in": C["staff"]}})
    DB.venue_vips.delete_many({"venue_id": {"$in": C["venues"]}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.venue_payables.delete_many({"id": {"$in": C["payables"]}})
    DB.feedback.delete_many({"_id": {"$in": C["feedback"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})
    if SETTINGS_PRE is None:
        DB.settings.delete_one({"_id": "venue_report"})
    else:
        DB.settings.replace_one({"_id": "venue_report"}, SETTINGS_PRE)


@pytest.fixture(scope="module")
def mods():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from routes import push, notify, venueops
    from services import emailer

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    async def fake_mail(*, to, subject, html):
        MAILS.append({"to": to, "subject": subject, "html": html})
        return "fake"

    orig_p, orig_m = push.send_push, emailer.send_email
    push.send_push, emailer.send_email = fake_send, fake_mail
    yield {"push": push, "notify": notify, "venueops": venueops, "server": server}
    push.send_push, emailer.send_email = orig_p, orig_m


@pytest.fixture(scope="module")
def world(venue):
    """Seeded owner's TEST_ venue with two events, two door staff (every-night by default) and two guests."""
    v = mk_venue(venue["user"]["id"])
    e1, e2 = mk_event(venue["user"]["id"], v), mk_event(venue["user"]["id"], v, date=NOW() + timedelta(days=2))
    s1, s2 = register(name="TEST_ Door One"), register(name="TEST_ Door Two")
    ids = []
    for s in (s1, s2):
        r = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": s["user"]["email"]}, headers=h(venue))
        assert r.status_code == 201, r.text
        assert r.json()["every_night"] is True
        ids.append(r.json()["id"])
    g1, g2 = register(name="TEST_ Vera Vip"), register(name="TEST_ Norm Guest")
    return {"v": v, "e1": e1, "e2": e2, "s1": s1, "s2": s2, "sid1": ids[0], "sid2": ids[1], "g1": g1, "g2": g2}


# ---------- Door shifts ----------
class TestShifts:
    def test_list_default_every_night(self, venue, world):
        r = requests.get(f"{API}/host/events/{world['e1']['id']}/shifts", headers=h(venue))
        assert r.status_code == 200, r.text
        rows = {x["staff_id"]: x for x in r.json()}
        assert set(rows) == {world["sid1"], world["sid2"]}
        assert all(x["every_night"] and x["on_shift"] and x["status"] == "active" for x in rows.values())

    def test_off_every_night_switches_to_scheduled(self, venue, world):
        r = requests.put(f"{API}/host/events/{world['e1']['id']}/shifts/{world['sid1']}", json={"on": False}, headers=h(venue))
        assert r.status_code == 200, r.text
        assert r.json()["every_night"] is False and r.json()["on_shift"] is False
        row = DB.door_staff.find_one({"id": world["sid1"]})
        assert row["every_night"] is False and row["shift_event_ids"] == []
        # other staff untouched
        rows = {x["staff_id"]: x for x in requests.get(f"{API}/host/events/{world['e1']['id']}/shifts", headers=h(venue)).json()}
        assert rows[world["sid2"]]["on_shift"] is True and rows[world["sid1"]]["on_shift"] is False

    def test_off_shift_staff_blocked(self, world):
        hs = h(world["s1"])
        duty = requests.get(f"{API}/staff/duty", headers=hs).json()
        assert world["e1"]["id"] not in [e["id"] for e in duty["events"]]
        assert world["v"]["name"] in duty["venues"]
        t = mk_ticket(world["e1"], world["g2"]["user"]["id"])
        r = requests.post(f"{API}/tickets/{t['id']}/checkin", headers=hs)
        assert r.status_code == 403, r.text
        assert requests.get(f"{API}/host/events/{world['e1']['id']}/live", headers=hs).status_code == 403
        assert requests.get(f"{API}/host/events/{world['e1']['id']}/guests?q=te", headers=hs).status_code == 403
        assert DB.tickets.find_one({"id": t["id"]})["checked_in"] is False

    def test_assign_shift_pushes_and_grants_access(self, mods, venue, world):
        vo = mods["venueops"]
        SENT.clear()
        out = call(mods, vo.set_shift(world["e2"]["id"], world["sid1"], vo.ShiftIn(on=True), venue["user"] | {"role": "venue_owner"}))
        assert out.on_shift is True and out.every_night is False
        pushes = [p for p in SENT if world["s1"]["user"]["id"] in p["recipients"]]
        assert pushes and "New door shift" in pushes[0]["data"]["title"], SENT
        assert pushes[0]["data"].get("action_url") == "/door"
        hs = h(world["s1"])
        duty = [e["id"] for e in requests.get(f"{API}/staff/duty", headers=hs).json()["events"]]
        assert duty == [world["e2"]["id"]]
        live = requests.get(f"{API}/host/events/{world['e2']['id']}/live", headers=hs)
        assert live.status_code == 200 and live.json()["is_staff_view"] is True
        t = mk_ticket(world["e2"], world["g2"]["user"]["id"])
        r = requests.post(f"{API}/tickets/{t['id']}/checkin", headers=hs)
        assert r.status_code == 200, r.text

    def test_off_scheduled_removes_event(self, venue, world):
        r = requests.put(f"{API}/host/events/{world['e2']['id']}/shifts/{world['sid1']}", json={"on": False}, headers=h(venue))
        assert r.status_code == 200 and r.json()["on_shift"] is False
        assert DB.door_staff.find_one({"id": world["sid1"]})["shift_event_ids"] == []
        # re-assign e2 for later VIP tests
        r = requests.put(f"{API}/host/events/{world['e2']['id']}/shifts/{world['sid1']}", json={"on": True}, headers=h(venue))
        assert r.json()["on_shift"] is True

    def test_schedule_toggle_every_night(self, venue, world):
        r = requests.put(f"{API}/host/staff/{world['sid2']}/schedule", json={"every_night": False}, headers=h(venue))
        assert r.status_code == 200 and r.json() == {"every_night": False}
        listed = {s["id"]: s for s in requests.get(f"{API}/host/staff", headers=h(venue)).json()}
        assert listed[world["sid2"]]["every_night"] is False
        assert requests.get(f"{API}/staff/duty", headers=h(world["s2"])).json()["events"] == []
        r = requests.put(f"{API}/host/staff/{world['sid2']}/schedule", json={"every_night": True}, headers=h(venue))
        assert r.json() == {"every_night": True}
        duty = [e["id"] for e in requests.get(f"{API}/staff/duty", headers=h(world["s2"])).json()["events"]]
        assert world["e1"]["id"] in duty and world["e2"]["id"] in duty

    def test_owner_only(self, venue, world):
        other = register(role="venue_owner", name="TEST_ Other Owner")
        promoter = login("promoter@nocturne.app", "PromoterPass123!")
        eid = world["e1"]["id"]
        assert requests.get(f"{API}/host/events/{eid}/shifts", headers=h(promoter)).status_code == 403
        assert requests.get(f"{API}/host/events/{eid}/shifts", headers=h(other)).status_code in (403, 404)
        assert requests.put(f"{API}/host/events/{eid}/shifts/{world['sid1']}", json={"on": True}, headers=h(other)).status_code in (403, 404)
        assert requests.put(f"{API}/host/staff/{world['sid1']}/schedule", json={"every_night": True}, headers=h(other)).status_code == 404
        assert requests.put(f"{API}/host/staff/nope/schedule", json={"every_night": True}, headers=h(venue)).status_code == 404
        assert requests.put(f"{API}/host/events/{eid}/shifts/nope", json={"on": True}, headers=h(venue)).status_code == 404
        assert requests.get(f"{API}/host/events/{eid}/shifts", headers=h(world["s1"])).status_code == 403
        S["other"] = other


# ---------- VIP guests ----------
class TestVips:
    def test_flag_and_guards(self, venue, world):
        vid, uid = world["v"]["id"], world["g1"]["user"]["id"]
        r = requests.put(f"{API}/host/venues/{vid}/vips/{uid}", json={"note": "  Owner's friend  "}, headers=h(venue))
        assert r.status_code == 200 and r.json() == {"vip": True, "note": "Owner's friend"}, r.text
        other = S.get("other") or register(role="venue_owner")
        assert requests.put(f"{API}/host/venues/{vid}/vips/{uid}", json={}, headers=h(other)).status_code == 403
        assert requests.delete(f"{API}/host/venues/{vid}/vips/{uid}", headers=h(other)).status_code == 403
        assert requests.put(f"{API}/host/venues/{vid}/vips/nobody", json={}, headers=h(venue)).status_code == 404
        assert requests.put(f"{API}/host/venues/{vid}/vips/{uid}", json={}, headers=h(world["g1"])).status_code == 403

    def test_vip_shown_in_lists(self, venue, world):
        ev = world["e2"]
        tv = mk_ticket(ev, world["g1"]["user"]["id"], qty=2)
        tn = mk_ticket(ev, world["g2"]["user"]["id"])
        S.update(tv=tv, tn=tn)
        d = requests.get(f"{API}/host/events/{ev['id']}", headers=h(venue)).json()
        g = {x["ticket_id"]: x for x in d["guests"]}
        assert g[tv["id"]]["vip"] is True and g[tv["id"]]["user_id"] == world["g1"]["user"]["id"]
        assert g[tn["id"]]["vip"] is False
        hits = requests.get(f"{API}/host/events/{ev['id']}/guests?q=TEST_", headers=h(venue)).json()
        hv = next(x for x in hits if x["ticket_id"] == tv["id"])
        assert hv["vip"] is True and hv["vip_note"] == "Owner's friend" and hv["user_id"] == world["g1"]["user"]["id"]
        unchecked = [x for x in hits if not x["checked_in"]]
        assert unchecked[0]["vip"] is True  # VIPs first among not-yet-arrived
        staff_hits = requests.get(f"{API}/host/events/{ev['id']}/guests?q=vera", headers=h(world["s1"])).json()
        assert staff_hits and staff_hits[0]["user_id"] is None and staff_hits[0]["vip"] is True

    def test_vip_checkin_pushes_hosts_and_on_shift_staff(self, mods, venue, world):
        SENT.clear()
        srv = mods["server"]
        call(mods, srv.check_in(ticket_id=S["tv"]["id"], user=venue["user"] | {"role": "venue_owner"}))
        vip = [p for p in SENT if p["data"]["title"].startswith("⭐ VIP arrived")]
        assert len(vip) == 1, SENT
        p = vip[0]
        assert p["data"]["title"] == "⭐ VIP arrived: TEST_ Vera Vip (+1)"
        assert "Owner's friend" in p["data"]["message"]
        assert venue["user"]["id"] in p["recipients"]
        assert world["s1"]["user"]["id"] in p["recipients"] and world["s2"]["user"]["id"] in p["recipients"]
        live = requests.get(f"{API}/host/events/{world['e2']['id']}/live", headers=h(venue)).json()
        rec = {a.get("name"): a for a in live["recent"]}
        assert any(a["vip"] for a in live["recent"]), live["recent"]
        assert rec.get("TEST_ Vera Vip", {}).get("vip", True) is True

    def test_off_shift_staff_not_alerted_and_non_vip_silent(self, mods, venue, world):
        # s1 off e2 -> should not get VIP push; non-VIP check-in -> no VIP push at all
        requests.put(f"{API}/host/events/{world['e2']['id']}/shifts/{world['sid1']}", json={"on": False}, headers=h(venue))
        t2 = mk_ticket(world["e2"], world["g1"]["user"]["id"])
        SENT.clear()
        call(mods, mods["server"].check_in(ticket_id=t2["id"], user=venue["user"] | {"role": "venue_owner"}))
        vip = [p for p in SENT if p["data"]["title"].startswith("⭐ VIP arrived")]
        assert len(vip) == 1 and world["s1"]["user"]["id"] not in vip[0]["recipients"]
        assert world["s2"]["user"]["id"] in vip[0]["recipients"]
        SENT.clear()
        call(mods, mods["server"].check_in(ticket_id=S["tn"]["id"], user=venue["user"] | {"role": "venue_owner"}))
        assert not [p for p in SENT if "VIP" in p["data"]["title"]]

    def test_unflag(self, venue, world):
        vid, uid = world["v"]["id"], world["g1"]["user"]["id"]
        r = requests.delete(f"{API}/host/venues/{vid}/vips/{uid}", headers=h(venue))
        assert r.status_code == 200 and r.json() == {"vip": False}
        assert DB.venue_vips.find_one({"venue_id": vid, "user_id": uid})["active"] is False
        d = requests.get(f"{API}/host/events/{world['e2']['id']}", headers=h(venue)).json()
        assert not any(g["vip"] for g in d["guests"])


# ---------- Deal leaderboard ----------
class TestLeaderboard:
    def test_aggregates_and_sorts(self):
        owner = register(role="venue_owner", name="TEST_ LB Owner")
        oid = owner["user"]["id"]
        v = mk_venue(oid)
        w = [f"TEST_w{i}" for i in range(6)]
        sent = NOW() - timedelta(hours=3)
        deal = lambda pct, users: {"pct": pct, "user_ids": users, "sent_at": sent, "expires_at": sent + timedelta(hours=2)}  # noqa: E731
        a = mk_event(oid, v, deal=deal(20, w[:4]))
        b = mk_event(oid, v, deal=deal(20, w[:2]))
        c = mk_event(oid, v, deal=deal(50, w[:2]))
        mk_event(oid, v)  # no deal
        mk_ticket(a, w[0], qty=2, total_paid=40.0, created_at=sent + timedelta(minutes=10))
        mk_ticket(a, w[1], qty=1, total_paid=10.0, credit_used=5.0, created_at=sent + timedelta(minutes=20))
        mk_ticket(a, w[2], qty=1, total_paid=99.0, created_at=sent - timedelta(minutes=5))  # before deal
        mk_ticket(c, w[0], qty=1, total_paid=25.0, created_at=sent + timedelta(minutes=30))
        mk_ticket(c, w[1], qty=3, total_paid=60.0, created_at=sent + timedelta(minutes=40))
        mk_ticket(b, w[5], qty=1, total_paid=20.0, created_at=sent + timedelta(minutes=5))  # not waitlisted
        r = requests.get(f"{API}/host/deals/leaderboard", headers=h(owner))
        assert r.status_code == 200, r.text
        rows = r.json()
        assert [x["pct"] for x in rows] == [50, 20]
        assert rows[0] == {"pct": 50, "deals": 1, "sent_to": 2, "buyers": 2, "tickets": 4, "revenue": 85.0, "conversion": 100.0}
        assert rows[1] == {"pct": 20, "deals": 2, "sent_to": 6, "buyers": 2, "tickets": 3, "revenue": 55.0, "conversion": 33.3}

    def test_roles(self, venue):
        g = login("guest@nocturne.app", "GuestPass123!")
        assert requests.get(f"{API}/host/deals/leaderboard", headers=h(g)).status_code == 403
        assert requests.get(f"{API}/host/deals/leaderboard", headers=h(venue)).status_code == 200
        empty = register(role="venue_owner")
        assert requests.get(f"{API}/host/deals/leaderboard", headers=h(empty)).json() == []


# ---------- Monthly venue report ----------
class TestMonthlyReport:
    @pytest.fixture(scope="class")
    def rep(self):
        owner = register(role="venue_owner", name="TEST_ Rita Report")
        oid = owner["user"]["id"]
        v = mk_venue(oid)
        now = NOW()
        cur = now.replace(day=3, hour=20, minute=0, second=0, microsecond=0)
        prev = (cur.replace(day=1) - timedelta(days=1)).replace(day=3)
        e_cur, e_prev = mk_event(oid, v, date=cur), mk_event(oid, v, date=prev)
        mk_event(oid, v, date=cur + timedelta(days=1))
        for ev, sold, came in ((e_cur, 10, 8), (e_prev, 10, 5)):
            mk_ticket(ev, "TEST_g", qty=came, checked_in=True, checked_in_at=ev["date"], created_at=ev["date"])
            mk_ticket(ev, "TEST_g2", qty=sold - came, created_at=ev["date"])
        for amt, when in ((300.0, cur), (200.0, prev)):
            pid = str(uuid.uuid4())
            DB.venue_payables.insert_one({"id": pid, "venue_id": v["id"], "amount": amt, "status": "owed", "source": "ticket",
                                          "record_id": "TEST_", "created_at": when})
            C["payables"].append(pid)
        for rating, when in ((5, cur), (4, cur), (4, prev)):
            fid = f"TEST_fb_{uuid.uuid4().hex[:8]}"
            DB.feedback.insert_one({"_id": fid, "venue_id": v["id"], "rating": rating, "created_at": when})
            C["feedback"].append(fid)
        return {"owner": owner, "v": v, "month": cur.strftime("%Y-%m"), "cur": cur}

    def test_report_endpoint(self, rep):
        r = requests.get(f"{API}/host/report?month={rep['month']}", headers=h(rep["owner"]))
        assert r.status_code == 200, r.text
        [x] = r.json()
        assert x["venue_id"] == rep["v"]["id"] and x["month"] == rep["cur"].strftime("%B %Y")
        assert x["current"] == {"events": 2, "sold": 10, "arrived": 8, "show_rate": 80.0, "revenue": 300.0, "rating": 4.5, "ratings": 2}
        assert x["previous"]["arrived"] == 5 and x["previous"]["revenue"] == 200.0 and x["previous"]["events"] == 1
        assert x["change"] == {"arrived": 60, "revenue": 50, "show_rate": 60, "rating": 12}
        d = requests.get(f"{API}/host/report", headers=h(rep["owner"]))
        assert d.status_code == 200 and d.json()[0]["month"] == NOW().strftime("%B %Y")

    def test_report_bad_month_and_roles(self, rep):
        for m in ("2026-13", "May", "2026/05"):
            assert requests.get(f"{API}/host/report?month={m}", headers=h(rep["owner"])).status_code == 400
        g = login("guest@nocturne.app", "GuestPass123!")
        assert requests.get(f"{API}/host/report", headers=h(g)).status_code == 403

    def test_force_month_sends_push_and_email(self, mods, rep):
        MAILS.clear(), SENT.clear()
        n = call(mods, mods["venueops"].send_monthly_reports(force_month=rep["cur"]))
        assert n >= 1
        mine = [m for m in MAILS if m["to"] == rep["owner"]["user"]["email"]]
        assert len(mine) == 1 and mine[0]["subject"] == f"Your {rep['cur']:%B %Y} venue report"
        html = mine[0]["html"]
        for s in ("Guests in", "Show-up rate", "$300.00", "4.50★", "+60%", "Hi TEST_,", rep["v"]["name"]):
            assert s in html, s
        p = [x for x in SENT if rep["owner"]["user"]["id"] in x["recipients"]]
        assert p and "8 guests · $300.00" in p[0]["data"]["message"]

    def test_monthly_pref_off_skips_email(self, mods, rep):
        hs = h(rep["owner"])
        prefs = requests.get(f"{API}/me/email-prefs", headers=hs).json()
        assert prefs["monthly"] is True
        r = requests.put(f"{API}/me/email-prefs", json={"monthly": False}, headers=hs)
        assert r.status_code == 200 and r.json()["monthly"] is False
        MAILS.clear(), SENT.clear()
        call(mods, mods["venueops"].send_monthly_reports(force_month=rep["cur"]))
        assert not [m for m in MAILS if m["to"] == rep["owner"]["user"]["email"]]
        assert [x for x in SENT if rep["owner"]["user"]["id"] in x["recipients"]]  # push still goes

    def test_schedule_guard_day1_once(self, mods):
        vo = mods["venueops"]
        real = vo.datetime

        class Fake(datetime):
            at = None

            @classmethod
            def now(cls, tz=None):
                return cls.at

        vo.datetime = Fake
        try:
            DB.settings.delete_one({"_id": "venue_report"}) if SETTINGS_PRE is None else None
            Fake.at = datetime(2031, 3, 2, 17, tzinfo=timezone.utc)
            assert call(mods, vo.send_monthly_reports()) == 0  # not the 1st
            Fake.at = datetime(2031, 3, 1, 15, tzinfo=timezone.utc)
            assert call(mods, vo.send_monthly_reports()) == 0  # too early
            MAILS.clear(), SENT.clear()
            Fake.at = datetime(2031, 3, 1, 16, 5, tzinfo=timezone.utc)
            assert call(mods, vo.send_monthly_reports()) >= 1
            assert DB.settings.find_one({"_id": "venue_report"})["month"] == "2031-02"
            assert any(m["subject"] == "Your February 2031 venue report" for m in MAILS)
            assert call(mods, vo.send_monthly_reports()) == 0  # once per month
        finally:
            vo.datetime = real
