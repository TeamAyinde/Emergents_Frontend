"""Iteration 22: staff email invites, deal results, door guest search, night summary trends."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import run
from test_nocturne_iter20_live_deals import call  # drains push/email background tasks

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "events": [], "tickets": [], "requests": [], "venues": [], "staff": [], "payables": []}
SENT, MAILS = [], []
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register(role="guest", name="TEST_ I22 User", email=None):
    r = requests.post(f"{API}/auth/register", json={
        "email": email or f"test_i22_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def mk_venue(owner_id):
    doc = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": f"TEST_ Venue {uuid.uuid4().hex[:4]}", "owner_id": owner_id,
           "city": "Los Angeles", "created_at": NOW()}
    DB.venues.insert_one(dict(doc))
    C["venues"].append(doc["id"])
    return doc


def mk_event(owner, venue=None, **kw):
    doc = {"id": str(uuid.uuid4()), "title": f"TEST_ I22 {uuid.uuid4().hex[:4]}", "venue_id": (venue or {}).get("id", "TEST_venue"),
           "venue_name": (venue or {}).get("name", "TEST_ Venue"), "city": "Los Angeles", "date": NOW() + timedelta(hours=5),
           "price": 0, "tags": [], "tickets_sold": 0, "created_at": NOW(), "min_level": "bronze", "approval_required": False,
           "capacity": 20, "plus_one_limit": 7, "tables": [], "created_by": owner, "image_url": ""}
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


def mk_request(ev, uid, qty=1):
    doc = {"id": str(uuid.uuid4()), "event_id": ev["id"], "event_title": ev["title"], "user_id": uid, "user_name": "TEST_",
           "user_level": "bronze", "quantity": qty, "kind": "waitlist", "status": "pending", "note": "",
           "promoter_code": None, "created_at": NOW()}
    DB.event_requests.insert_one(dict(doc))
    C["requests"].append(doc["id"])
    return doc


def mk_payable(record_id, amount, venue_id):
    doc = {"id": str(uuid.uuid4()), "venue_id": venue_id, "venue_name": "TEST_", "amount": amount, "source": "ticket",
           "record_id": record_id, "status": "owed", "created_at": NOW()}
    DB.venue_payables.insert_one(dict(doc))
    C["payables"].append(doc["id"])


@pytest.fixture(scope="module")
def venue():
    return login("venue@nocturne.app", "VenuePass123!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for t in DB.tickets.find({"user_id": {"$in": C["users"]}}, {"id": 1}):
        C["tickets"].append(t["id"])
    for s in DB.door_staff.find({"user_id": {"$in": C["users"]}}, {"id": 1}):
        C["staff"].append(s["id"])
    DB.door_staff.update_many({"id": {"$in": C["staff"]}}, {"$set": {"active": False}})
    DB.door_staff.delete_many({"id": {"$in": C["staff"]}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.event_requests.delete_many({"id": {"$in": C["requests"]}})
    DB.venue_payables.delete_many({"id": {"$in": C["payables"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.points_ledger.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def mods():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from routes import alerts, push, notify, staff
    from services import emailer

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    async def fake_mail(*, to, subject, html):
        emailer._assert_safe_email(subject, html)
        MAILS.append({"to": to, "subject": subject, "html": html})
        return "fake"

    orig_p, orig_m = push.send_push, emailer.send_email
    push.send_push, emailer.send_email = fake_send, fake_mail
    yield {"alerts": alerts, "push": push, "notify": notify, "staff": staff}
    push.send_push, emailer.send_email = orig_p, orig_m


# ---------- Staff email invites ----------
class TestStaffInvites:
    def test_invite_unknown_email_then_register_claims(self, venue):
        v = mk_venue(venue["user"]["id"])
        email = f"test_i22_inv_{uuid.uuid4().hex[:6]}@nocturne.app"
        r = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": email.upper()}, headers=h(venue))
        assert r.status_code == 201, r.text
        d = r.json()
        C["staff"].append(d["id"])
        assert d["status"] == "invited" and d["user_id"] is None and d["email"] == email and d["name"] == email
        lst = requests.get(f"{API}/host/staff", headers=h(venue)).json()
        assert any(x["id"] == d["id"] and x["status"] == "invited" for x in lst)
        # duplicate pending invite -> 409; self -> 400
        assert requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": email}, headers=h(venue)).status_code == 409
        assert requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": "venue@nocturne.app"}, headers=h(venue)).status_code == 400
        # invited-but-unregistered: row exists with user_id None -> no one gets access
        ev = mk_event(venue["user"]["id"], v)
        t = mk_ticket(ev, register()["user"]["id"])
        # register with that email -> invite becomes active
        s = register(name="TEST_ Ivy Invite", email=email)
        row = DB.door_staff.find_one({"id": d["id"]})
        assert row["user_id"] == s["user"]["id"] and row["status"] == "active" and row["name"] == "TEST_ Ivy Invite"
        duty = requests.get(f"{API}/staff/duty", headers=h(s)).json()
        assert duty["venues"] == [v["name"]] and ev["id"] in [e["id"] for e in duty["events"]], duty
        r = requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(s))
        assert r.status_code == 200 and r.json()["checked_in"] is True, r.text
        lst = requests.get(f"{API}/host/staff", headers=h(venue)).json()
        assert any(x["id"] == d["id"] and x["status"] == "active" and x["user_id"] == s["user"]["id"] for x in lst)

    def test_removed_invite_not_claimed(self, venue):
        v = mk_venue(venue["user"]["id"])
        email = f"test_i22_rm_{uuid.uuid4().hex[:6]}@nocturne.app"
        d = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": email}, headers=h(venue)).json()
        C["staff"].append(d["id"])
        assert requests.delete(f"{API}/host/staff/{d['id']}", headers=h(venue)).status_code == 200
        s = register(email=email)
        assert DB.door_staff.find_one({"id": d["id"]})["user_id"] is None
        assert requests.get(f"{API}/staff/duty", headers=h(s)).json() == {"venues": [], "events": []}

    def test_invite_email_content(self, mods):
        MAILS.clear()
        run(mods["staff"]._invite_email("test_i22_x@nocturne.app", "TEST_ <Club>", "Vic"))
        assert len(MAILS) == 1, MAILS
        m = MAILS[0]
        assert m["to"] == "test_i22_x@nocturne.app" and "TEST_ <Club>" in m["subject"]
        assert "TEST_ &lt;Club&gt;" in m["html"] and "test_i22_x@nocturne.app" in m["html"]
        print("INVITE HTML has sign-up link:", "/sign-up?email=" in m["html"])


# ---------- Deal results ----------
class TestDealResults:
    def test_buyers_tickets_revenue(self, venue):
        w1, w2, other = register(), register(), register()
        ev = mk_event(venue["user"]["id"], price=40.0)
        mk_request(ev, w1["user"]["id"], qty=2)
        mk_request(ev, w2["user"]["id"], qty=1)
        r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20, "hours": 2}, headers=h(venue))
        assert r.status_code == 200, r.text
        assert (r.json()["buyers"], r.json()["tickets"], r.json()["revenue"]) == (0, 0, 0.0)
        stored = DB.events.find_one({"id": ev["id"]})["deal"]
        inside = stored["sent_at"] + timedelta(minutes=5)
        mk_ticket(ev, w1["user"]["id"], qty=2, total_paid=30.0, credit_used=10.5, created_at=inside)
        mk_ticket(ev, w1["user"]["id"], qty=1, total_paid=20.0, created_at=inside)
        mk_ticket(ev, w2["user"]["id"], qty=1, total_paid=99.0, created_at=stored["sent_at"] - timedelta(minutes=5))  # before deal
        mk_ticket(ev, w2["user"]["id"], qty=1, total_paid=99.0, created_at=stored["expires_at"] + timedelta(minutes=5))  # after expiry
        mk_ticket(ev, other["user"]["id"], qty=4, total_paid=500.0, created_at=inside)  # not waitlisted
        live = requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(venue)).json()
        d = live["deal"]
        assert (d["buyers"], d["tickets"], d["revenue"]) == (1, 3, 60.5), d


# ---------- Guest search ----------
class TestGuestSearch:
    def test_search_access_and_matching(self, venue):
        v = mk_venue(venue["user"]["id"])
        ev = mk_event(venue["user"]["id"], v)
        a = register(name="TEST_ Zelda Quixote")
        b = register(name="TEST_ Bob (Regex.*) Smith")
        t1 = mk_ticket(ev, a["user"]["id"], qty=2)
        t2 = mk_ticket(ev, b["user"]["id"], checked_in=True, checked_in_at=NOW())
        url = f"{API}/host/events/{ev['id']}/guests"
        r = requests.get(url, params={"q": "zELDa quix"}, headers=h(venue))
        assert r.status_code == 200, r.text
        hits = r.json()
        assert [x["ticket_id"] for x in hits] == [t1["id"]] and hits[0]["quantity"] == 2 and hits[0]["checked_in"] is False
        assert set(hits[0]) >= {"ticket_id", "name", "email", "quantity", "checked_in", "checked_in_at"}
        # by email
        assert [x["ticket_id"] for x in requests.get(url, params={"q": a["user"]["email"][:14].upper()}, headers=h(venue)).json()] == [t1["id"]]
        # regex special chars
        rr = requests.get(url, params={"q": "(Regex.*)"}, headers=h(venue))
        assert rr.status_code == 200 and [x["ticket_id"] for x in rr.json()] == [t2["id"]] and rr.json()[0]["checked_in_at"]
        assert requests.get(url, params={"q": "Z.*Q"}, headers=h(venue)).json() == []
        assert requests.get(url, params={"q": "[("}, headers=h(venue)).status_code == 200
        # short query
        assert requests.get(url, params={"q": "z"}, headers=h(venue)).json() == []
        # admin ok; guest / promoter forbidden
        adm = login("admin@nocturne.app", "AdminPass123!")
        assert requests.get(url, params={"q": "zelda"}, headers=h(adm)).status_code == 200
        assert requests.get(url, params={"q": "zelda"}, headers=h(login("guest@nocturne.app", "GuestPass123!"))).status_code == 403
        assert requests.get(url, params={"q": "zelda"}, headers=h(login("promoter@nocturne.app", "PromoterPass123!"))).status_code == 403
        # door staff ok
        s = register(name="TEST_ Door Sid")
        sd = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": s["user"]["email"]}, headers=h(venue)).json()
        C["staff"].append(sd["id"])
        assert requests.get(url, params={"q": "zelda"}, headers=h(s)).status_code == 200
        assert requests.get(f"{API}/host/events/{uuid.uuid4()}/guests", params={"q": "zelda"}, headers=h(venue)).status_code == 404


# ---------- Summary trends ----------
class TestSummaryTrends:
    def test_summary_baseline_and_change(self, venue, mods):
        own = venue["user"]["id"]
        v = mk_venue(own)
        g = register()["user"]["id"]
        prevs = []
        for i in range(5):  # 5 previous; only latest 4 count
            e = mk_event(own, v, date=NOW() - timedelta(days=7 * (i + 1)))
            prevs.append(e)
            arrived = 10 if i == 4 else 4  # oldest is outlier and must be excluded
            t = mk_ticket(e, g, qty=8, checked_in=False)
            DB.tickets.update_one({"id": t["id"]}, {"$set": {"quantity": 8}})
            ti = mk_ticket(e, g, qty=arrived, checked_in=True, checked_in_at=e["date"] + timedelta(hours=1))
            mk_payable(ti["id"], 100.0, v["id"])
        ev = mk_event(own, v, date=NOW() - timedelta(hours=12))
        tk = mk_ticket(ev, g, qty=5, checked_in=True, checked_in_at=NOW() - timedelta(hours=11))
        mk_ticket(ev, g, qty=1)
        mk_payable(tk["id"], 150.0, v["id"])
        r = requests.get(f"{API}/host/events/{ev['id']}/summary", headers=h(venue))
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["compared"] == 4, s
        assert s["night"]["arrived"] == 5 and s["night"]["sold"] == 6 and s["night"]["revenue"] == 150.0
        assert s["baseline"]["arrived"] == 4 and s["baseline"]["revenue"] == 100.0, s["baseline"]
        assert s["change"]["arrived"] == 25 and s["change"]["revenue"] == 50, s["change"]
        assert "show_rate" in s["change"] and s["peak"]
        # trend line + html
        evdoc = DB.events.find_one({"id": ev["id"]}, {"_id": 0})
        rep = run(mods["alerts"].night_report(evdoc))
        line = mods["alerts"].trend_line(rep)
        assert "+25% guests" in line and "+50% revenue" in line and "last 4 nights" in line, line
        html = mods["alerts"].summary_html(evdoc, rep)
        assert "Last 4 avg" in html and "+25%" in html
        # first event: no baseline
        first = mk_event(own, mk_venue(own), date=NOW() - timedelta(hours=12))
        f = requests.get(f"{API}/host/events/{first['id']}/summary", headers=h(venue)).json()
        assert f["baseline"] is None and f["compared"] == 0 and f["change"] == {}
        # access
        assert requests.get(f"{API}/host/events/{ev['id']}/summary", headers=h(login("guest@nocturne.app", "GuestPass123!"))).status_code == 403
        assert requests.get(f"{API}/host/events/{ev['id']}/summary", headers=h(register("venue_owner"))).status_code == 403
        assert requests.get(f"{API}/host/events/{ev['id']}/summary", headers=h(login("admin@nocturne.app", "AdminPass123!"))).status_code == 200
        # push includes trend; mark other prevs summary_sent so only ours is picked up from this venue
        for p in prevs:
            DB.events.update_one({"id": p["id"]}, {"$set": {"summary_sent": True}})
        win = {"date": {"$gte": NOW() - timedelta(hours=37), "$lte": NOW()}, "summary_sent": {"$ne": True}, "id": {"$nin": C["events"]}}
        untouched = [e["id"] for e in DB.events.find(win, {"id": 1})]
        SENT.clear(); MAILS.clear()
        try:
            call(mods, mods["alerts"].send_night_summaries())
        finally:  # don't leave summary flags on non-test events
            DB.events.update_many({"id": {"$in": untouched}}, {"$unset": {"summary_sent": ""}})
        mine = [p for p in SENT if p["key"] == f"summary-{ev['id']}"]
        assert len(mine) == 1, SENT
        msg = mine[0]["data"]["message"]
        assert "+25% guests" in msg and "vs your last 4 nights" in msg, mine[0]
