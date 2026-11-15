"""Iteration 21: deal expiry timer + party limit, door staff access, morning-after night summary, 'summary' email pref."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import grant_credit
from test_nocturne_iter20_live_deals import call  # shared helper: drains push/email background tasks

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
C = {"users": [], "events": [], "tickets": [], "requests": [], "venues": [], "staff": [], "tables": [], "payables": []}
SENT, MAILS = [], []
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register(role="guest", name="TEST_ I21 User"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_i21_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
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
    doc = {"id": str(uuid.uuid4()), "title": f"TEST_ I21 {uuid.uuid4().hex[:4]}", "venue_id": (venue or {}).get("id", "TEST_venue"),
           "venue_name": (venue or {}).get("name", "TEST_ Venue"), "city": "Los Angeles", "date": NOW() + timedelta(hours=5),
           "price": 0, "tags": [], "tickets_sold": 0, "created_at": NOW(), "min_level": "bronze", "approval_required": False,
           "capacity": 10, "plus_one_limit": 7, "tables": [], "created_by": owner, "image_url": ""}
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
    DB.event_requests.delete_many({"user_id": {"$in": C["users"]}, "event_id": {"$in": C["events"]}})
    DB.payment_transactions.delete_many({"user_id": {"$in": C["users"]}})
    DB.venue_payables.delete_many({"$or": [{"id": {"$in": C["payables"]}}, {"record_id": {"$in": C["tickets"]}}]})
    DB.table_bookings.delete_many({"id": {"$in": C["tables"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.points_ledger.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def mods():
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from routes import alerts, push, notify
    from services import emailer

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    async def fake_mail(*, to, subject, html):
        emailer._assert_safe_email(subject, html)
        MAILS.append({"to": to, "subject": subject, "html": html})
        return "fake"

    orig_p, orig_m = push.send_push, emailer.send_email
    push.send_push, emailer.send_email = fake_send, fake_mail
    yield {"alerts": alerts, "push": push, "notify": notify}
    push.send_push, emailer.send_email = orig_p, orig_m


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) if "+" not in s and not s.endswith("Z") \
        else datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- Deal expiry timer ----------
class TestDealTimer:
    def test_hours_validation(self, venue):
        ev = mk_event(venue["user"]["id"])
        mk_request(ev, register()["user"]["id"])
        for bad in (0, 3, 12, -1):
            r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20, "hours": bad}, headers=h(venue))
            assert r.status_code == 400, (bad, r.text)
        assert "deal" not in DB.events.find_one({"id": ev["id"]})

    def test_default_two_hours_and_user_qty(self, venue):
        w1, w2 = register(), register()
        ev = mk_event(venue["user"]["id"], date=NOW() + timedelta(hours=6))
        mk_request(ev, w1["user"]["id"], qty=3)
        mk_request(ev, w2["user"]["id"], qty=1)
        t0 = NOW()
        r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20}, headers=h(venue))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["expired"] is False and d["sent_to"] == 2
        exp = _dt(d["expires_at"])
        assert abs((exp - (t0 + timedelta(hours=2))).total_seconds()) < 60, d
        stored = DB.events.find_one({"id": ev["id"]})["deal"]
        assert stored["user_qty"] == {w1["user"]["id"]: 3, w2["user"]["id"]: 1}
        md = requests.get(f"{API}/events/{ev['id']}/my-deal", headers=h(w1)).json()
        assert md["pct"] == 20 and md["qty"] == 3 and md["expires_at"]

    def test_expiry_capped_at_event_start(self, venue):
        ev = mk_event(venue["user"]["id"], date=NOW() + timedelta(hours=3))
        mk_request(ev, register()["user"]["id"])
        r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 10, "hours": 8}, headers=h(venue))
        assert r.status_code == 200, r.text
        assert abs((_dt(r.json()["expires_at"]) - ev["date"]).total_seconds()) < 2, r.json()

    def test_expired_deal_my_deal_and_live(self, venue):
        w = register()
        ev = mk_event(venue["user"]["id"])
        mk_request(ev, w["user"]["id"], qty=2)
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 30, "hours": 1}, headers=h(venue)).status_code == 200
        DB.events.update_one({"id": ev["id"]}, {"$set": {"deal.expires_at": NOW() - timedelta(minutes=1)}})
        assert requests.get(f"{API}/events/{ev['id']}/my-deal", headers=h(w)).json() == {"pct": 0, "qty": 0, "expires_at": None}
        live = requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(venue)).json()
        assert live["deal"]["expired"] is True and live["deal"]["pct"] == 30


# ---------- Deal party limit + expiry in pricing ----------
class TestDealPricingLimit:
    def _checkout(self, u, ev, qty):
        body = {"kind": "ticket", "origin_url": BASE_URL, "event_id": ev["id"], "quantity": qty}
        r = requests.post(f"{API}/payments/checkout", json=body, headers=h(u))
        if r.status_code == 503:
            pytest.skip("Stripe unavailable")
        assert r.status_code == 200, r.text
        return r.json()["amount"]

    def test_checkout_discount_only_for_allowed_qty(self, venue):
        g = register()
        ev = mk_event(venue["user"]["id"], price=40.0, capacity=20, tickets_sold=2)
        mk_request(ev, g["user"]["id"], qty=2)
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 50}, headers=h(venue)).status_code == 200
        assert self._checkout(g, ev, 1) == 23.0    # 20 + 3
        assert self._checkout(g, ev, 2) == 46.0    # 40 + 6
        assert self._checkout(g, ev, 3) == 92.0    # (40+40+20... 120-40=80) + 12

    def test_expired_deal_full_price(self, venue):
        g = register()
        ev = mk_event(venue["user"]["id"], price=40.0, capacity=20, tickets_sold=2)
        mk_request(ev, g["user"]["id"], qty=2)
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 50}, headers=h(venue)).status_code == 200
        DB.events.update_one({"id": ev["id"]}, {"$set": {"deal.expires_at": NOW() - timedelta(seconds=5)}})
        assert self._checkout(g, ev, 2) == 92.0    # 80 + 12, no discount

    def test_join_with_credit_partial_discount(self, venue):
        g = register()
        grant_credit(g["user"]["id"], 500)
        ev = mk_event(venue["user"]["id"], price=50.0, capacity=20, tickets_sold=2)
        mk_request(ev, g["user"]["id"], qty=1)
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20}, headers=h(venue)).status_code == 200
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 3}, headers=h(g))
        assert r.status_code == 200, r.text
        t = r.json()["ticket"]
        # 150 - 10 = 140 base, fee 21 -> 161
        assert t["platform_fee"] == 21.0 and t["credit_used"] == 161.0, t
        assert DB.tickets.find_one({"id": t["id"]})["venue_share"] == 140.0

    def test_deal_not_reused_on_second_purchase(self, venue):
        """Party limit should cover the guest's waitlist quantity in total, not per purchase."""
        g = register()
        grant_credit(g["user"]["id"], 500)
        ev = mk_event(venue["user"]["id"], price=50.0, capacity=20, tickets_sold=2)
        mk_request(ev, g["user"]["id"], qty=1)
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20}, headers=h(venue)).status_code == 200
        a = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(g))
        b = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(g))
        assert a.status_code == 200, a.text
        assert a.json()["ticket"]["credit_used"] == 46.0
        if b.status_code == 200:
            assert b.json()["ticket"]["credit_used"] == 57.5, f"deal applied twice: {b.json()['ticket']}"


# ---------- Door staff ----------
class TestDoorStaff:
    @pytest.fixture(scope="class")
    def setup(self, venue):
        v = mk_venue(venue["user"]["id"])
        other_v = mk_venue("TEST_someone_else")
        staff = register(name="TEST_ Door Dan")
        return {"v": v, "other": other_v, "staff": staff}

    def test_add_staff_validation(self, venue, setup):
        v, s = setup["v"], setup["staff"]
        url = f"{API}/host/staff"
        assert requests.post(url, json={"venue_id": setup["other"]["id"], "email": s["user"]["email"]}, headers=h(venue)).status_code == 403
        assert requests.post(url, json={"venue_id": v["id"], "email": f"nobody_{uuid.uuid4().hex[:6]}@x.io"}, headers=h(venue)).status_code == 404
        assert requests.post(url, json={"venue_id": v["id"], "email": "venue@nocturne.app"}, headers=h(venue)).status_code == 400
        g = login("guest@nocturne.app", "GuestPass123!")
        p = login("promoter@nocturne.app", "PromoterPass123!")
        assert requests.post(url, json={"venue_id": v["id"], "email": s["user"]["email"]}, headers=h(g)).status_code == 403
        assert requests.post(url, json={"venue_id": v["id"], "email": s["user"]["email"]}, headers=h(p)).status_code == 403
        assert requests.get(url, headers=h(g)).status_code == 403

    def test_add_list_duplicate(self, venue, setup):
        v, s = setup["v"], setup["staff"]
        r = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": s["user"]["email"].upper()}, headers=h(venue))
        assert r.status_code == 201, r.text
        d = r.json()
        C["staff"].append(d["id"])
        setup["sid"] = d["id"]
        assert d["venue_id"] == v["id"] and d["venue_name"] == v["name"] and d["user_id"] == s["user"]["id"] and d["name"] == "TEST_ Door Dan"
        r2 = requests.post(f"{API}/host/staff", json={"venue_id": v["id"], "email": s["user"]["email"]}, headers=h(venue))
        assert r2.status_code == 409
        lst = requests.get(f"{API}/host/staff", headers=h(venue)).json()
        assert any(x["id"] == d["id"] for x in lst)
        a = login("admin@nocturne.app", "AdminPass123!")
        assert any(x["id"] == d["id"] for x in requests.get(f"{API}/host/staff", headers=h(a)).json())

    def test_duty_lists_venue_events(self, venue, setup):
        v, s = setup["v"], setup["staff"]
        own = venue["user"]["id"]
        recent = mk_event(own, v, date=NOW() - timedelta(hours=2))
        future = mk_event(own, v, date=NOW() + timedelta(hours=4))
        old = mk_event(own, v, date=NOW() - timedelta(hours=13))
        elsewhere = mk_event(own, setup["other"], date=NOW() + timedelta(hours=1))
        setup.update(recent=recent, future=future, elsewhere=elsewhere)
        d = requests.get(f"{API}/staff/duty", headers=h(s)).json()
        assert d["venues"] == [v["name"]]
        ids = [e["id"] for e in d["events"]]
        assert ids == [recent["id"], future["id"]], d
        assert old["id"] not in ids and elsewhere["id"] not in ids
        plain = register()
        assert requests.get(f"{API}/staff/duty", headers=h(plain)).json() == {"venues": [], "events": []}

    def test_staff_checkin_and_live_scope(self, venue, setup):
        s = setup["staff"]
        g = register()["user"]["id"]
        t_ok = mk_ticket(setup["future"], g)
        t_no = mk_ticket(setup["elsewhere"], g)
        r = requests.post(f"{API}/tickets/{t_ok['id'][:8]}/checkin", headers=h(s))
        assert r.status_code == 200 and r.json()["checked_in"] is True, r.text
        assert DB.tickets.find_one({"id": t_ok["id"]})["checked_in_at"] is not None
        assert requests.post(f"{API}/tickets/{t_no['id']}/checkin", headers=h(s)).status_code == 403
        assert DB.tickets.find_one({"id": t_no["id"]})["checked_in"] is False
        live = requests.get(f"{API}/host/events/{setup['future']['id']}/live", headers=h(s))
        assert live.status_code == 200, live.text
        assert live.json()["is_staff_view"] is True and live.json()["deal"] is None and live.json()["checked_in"] == 1
        assert requests.get(f"{API}/host/events/{setup['elsewhere']['id']}/live", headers=h(s)).status_code == 403
        mk_request(setup["future"], g)
        assert requests.post(f"{API}/host/events/{setup['future']['id']}/deal", json={"pct": 20}, headers=h(s)).status_code == 403
        owner_live = requests.get(f"{API}/host/events/{setup['future']['id']}/live", headers=h(venue)).json()
        assert owner_live["is_staff_view"] is False

    def test_plain_guest_and_promoter_checkin_unchanged(self, setup):
        g = register()
        p = login("promoter@nocturne.app", "PromoterPass123!")
        t1 = mk_ticket(setup["elsewhere"], g["user"]["id"])
        t2 = mk_ticket(setup["elsewhere"], g["user"]["id"])
        assert requests.post(f"{API}/tickets/{t1['id']}/checkin", headers=h(g)).status_code == 403
        assert requests.post(f"{API}/tickets/{t1['id']}/checkin", headers=h(p)).status_code == 200
        a = login("admin@nocturne.app", "AdminPass123!")
        assert requests.post(f"{API}/tickets/{t2['id']}/checkin", headers=h(a)).status_code == 200
        assert requests.post(f"{API}/tickets/{t2['id']}/checkin", headers=h(a)).status_code == 400

    def test_remove_staff_revokes_access(self, venue, setup):
        s, sid = setup["staff"], setup["sid"]
        other_owner = register("venue_owner")
        assert requests.delete(f"{API}/host/staff/{sid}", headers=h(other_owner)).status_code in (403, 404)
        r = requests.delete(f"{API}/host/staff/{sid}", headers=h(venue))
        assert r.status_code == 200 and r.json() == {"ok": True}
        row = DB.door_staff.find_one({"id": sid})
        assert row["active"] is False and row.get("removed_at")
        assert requests.delete(f"{API}/host/staff/{sid}", headers=h(venue)).status_code == 404
        assert all(x["id"] != sid for x in requests.get(f"{API}/host/staff", headers=h(venue)).json())
        t = mk_ticket(setup["future"], register()["user"]["id"])
        assert requests.post(f"{API}/tickets/{t['id']}/checkin", headers=h(s)).status_code == 403
        assert requests.get(f"{API}/host/events/{setup['future']['id']}/live", headers=h(s)).status_code == 403
        assert requests.get(f"{API}/staff/duty", headers=h(s)).json()["events"] == []
        # can be re-added after removal
        r2 = requests.post(f"{API}/host/staff", json={"venue_id": setup["v"]["id"], "email": s["user"]["email"]}, headers=h(venue))
        assert r2.status_code == 201, r2.text
        C["staff"].append(r2.json()["id"])


# ---------- Night summary ----------
class TestNightSummary:
    def test_night_stats_and_send_once(self, mods):
        owner = register("venue_owner", name="TEST_ Olivia Owner")
        creator = register("promoter", name="TEST_ Carl Creator")
        DB.users.update_one({"id": creator["user"]["id"]}, {"$set": {"email_prefs.summary": False}})
        v = mk_venue(owner["user"]["id"])
        ev = mk_event(creator["user"]["id"], v, date=NOW() - timedelta(hours=12), capacity=50)
        young = mk_event(creator["user"]["id"], v, date=NOW() - timedelta(hours=5))
        stale = mk_event(creator["user"]["id"], v, date=NOW() - timedelta(hours=40))
        done = mk_event(creator["user"]["id"], v, date=NOW() - timedelta(hours=20), summary_sent=True)
        g = register()["user"]["id"]
        peak_at = (NOW() - timedelta(hours=11)).replace(minute=10, second=0, microsecond=0)
        t1 = mk_ticket(ev, g, qty=2, checked_in=True, checked_in_at=peak_at)
        t2 = mk_ticket(ev, g, qty=2, checked_in=True, checked_in_at=peak_at + timedelta(minutes=20))
        t3 = mk_ticket(ev, g, qty=1, checked_in=True, checked_in_at=peak_at + timedelta(hours=1))
        mk_ticket(ev, g, qty=3)
        tb = {"id": str(uuid.uuid4()), "event_id": ev["id"], "table_id": "TEST_t1", "status": "confirmed", "user_id": g, "created_at": NOW()}
        tb2 = {"id": str(uuid.uuid4()), "event_id": ev["id"], "table_id": "TEST_t2", "status": "cancelled", "user_id": g, "created_at": NOW()}
        DB.table_bookings.insert_many([dict(tb), dict(tb2)])
        C["tables"] += [tb["id"], tb2["id"]]
        mk_payable(t1["id"], 40.0, v["id"])
        mk_payable(t2["id"], 25.5, v["id"])
        mk_payable(tb["id"], 200.0, v["id"])
        mk_payable(tb2["id"], 999.0, v["id"])  # cancelled booking must not count
        mk_payable(str(uuid.uuid4()), 77.0, v["id"])  # unrelated record

        evdoc = DB.events.find_one({"id": ev["id"]}, {"_id": 0})
        s = call(mods, mods["alerts"].night_stats(evdoc))
        exp_peak = peak_at.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%-I %p").lower()
        assert (s["sold"], s["arrived"], s["no_shows"], s["tables"], s["revenue"]) == (8, 5, 3, 1, 265.5), s
        assert s["peak"] == (exp_peak, 4), s

        SENT.clear(); MAILS.clear()
        n = call(mods, mods["alerts"].send_night_summaries())
        assert n >= 1
        assert DB.events.find_one({"id": ev["id"]})["summary_sent"] is True
        for e in (young, stale):
            assert "summary_sent" not in DB.events.find_one({"id": e["id"]})
        mine = [p for p in SENT if p["key"] == f"summary-{ev['id']}"]
        assert len(mine) == 1, SENT
        assert set(mine[0]["recipients"]) == {owner["user"]["id"], creator["user"]["id"]}
        assert mine[0]["data"]["action_url"] == f"/host/event/{ev['id']}"
        assert "5/8" in mine[0]["data"]["message"] and "$265.50" in mine[0]["data"]["message"], mine[0]
        assert not [p for p in SENT if p["key"] == f"summary-{done['id']}"]
        mails = [m for m in MAILS if ev["title"] in m["subject"]]
        assert [m["to"] for m in mails] == [owner["user"]["email"]], MAILS
        assert "$265.50" in mails[0]["html"] and "5 of 8" in mails[0]["html"]

        SENT.clear(); MAILS.clear()
        call(mods, mods["alerts"].send_night_summaries())
        assert not [p for p in SENT if p["key"] == f"summary-{ev['id']}"]
        assert not [m for m in MAILS if ev["title"] in m["subject"]]

    def test_summary_pref_roundtrip(self):
        u = register("venue_owner")
        r = requests.get(f"{API}/me/email-prefs", headers=h(u))
        assert r.status_code == 200 and r.json()["summary"] is True, r.text
        r = requests.put(f"{API}/me/email-prefs", json={"summary": False}, headers=h(u))
        assert r.status_code == 200 and r.json()["summary"] is False
        assert requests.get(f"{API}/me/email-prefs", headers=h(u)).json()["summary"] is False
