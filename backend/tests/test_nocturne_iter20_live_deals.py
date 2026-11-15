"""Iteration 20: host live door dashboard, last-minute deals (waitlist price drop + deal pricing),
promoter recap email (HTML 7-day chart, 'recap' email pref). Push relay and send_email monkeypatched in-process.
All data TEST_-prefixed and removed by id at module teardown; settings doc promoter_recap restored."""
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
C = {"users": [], "events": [], "tickets": [], "requests": [], "tx": []}
SENT, MAILS = [], []
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register(role="guest", name="TEST_ Deal Guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_dl_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


@pytest.fixture(scope="module")
def venue():
    return login("venue@nocturne.app", "VenuePass123!")


def mk_event(owner, **kw):
    doc = {"id": str(uuid.uuid4()), "title": f"TEST_ Live {uuid.uuid4().hex[:4]}", "venue_id": "TEST_venue",
           "venue_name": "TEST_ Venue", "city": "Los Angeles", "date": NOW() + timedelta(hours=5), "price": 0,
           "tags": [], "tickets_sold": 0, "created_at": NOW(), "min_level": "bronze", "approval_required": False,
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


def mk_request(ev, uid, qty=1, kind="waitlist", status="pending"):
    doc = {"id": str(uuid.uuid4()), "event_id": ev["id"], "event_title": ev["title"], "user_id": uid,
           "user_name": "TEST_", "user_level": "bronze", "quantity": qty, "kind": kind, "status": status,
           "note": "", "promoter_code": None, "created_at": NOW()}
    DB.event_requests.insert_one(dict(doc))
    C["requests"].append(doc["id"])
    return doc


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    saved = DB.settings.find_one({"_id": "promoter_recap"})
    yield
    for t in DB.tickets.find({"user_id": {"$in": C["users"]}}, {"id": 1}):
        C["tickets"].append(t["id"])
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.event_requests.delete_many({"id": {"$in": C["requests"]}})
    DB.event_requests.delete_many({"user_id": {"$in": C["users"]}, "event_id": {"$in": C["events"]}})
    DB.payment_transactions.delete_many({"user_id": {"$in": C["users"]}})
    DB.venue_payables.delete_many({"record_id": {"$in": C["tickets"]}})
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
    from routes import alerts, push, notify, hostlive
    from services import emailer

    async def fake_send(recipients, data, idempotency_key=None, _attempt=0):
        SENT.append({"recipients": list(recipients), "data": data, "key": idempotency_key})

    async def fake_mail(*, to, subject, html):
        emailer._assert_safe_email(subject, html)  # same safety gate as the real sender
        MAILS.append({"to": to, "subject": subject, "html": html})
        return "fake"

    orig_p, orig_m = push.send_push, emailer.send_email
    push.send_push, emailer.send_email = fake_send, fake_mail
    yield {"alerts": alerts, "push": push, "notify": notify, "hostlive": hostlive}
    push.send_push, emailer.send_email = orig_p, orig_m


def call(m, coro):
    async def go():
        r = await coro
        for _ in range(50):
            pending = list(m["push"]._tasks) + list(m["notify"]._tasks)
            if not pending:
                break
            await asyncio.gather(*pending, return_exceptions=True)
        return r
    return run(go())


# ---------- Host live dashboard ----------
class TestLive:
    def test_live_counts_hours_recent(self, venue):
        g1 = register(name="TEST_ Ava Stone")["user"]["id"]
        g2 = register(name="TEST_Solo")["user"]["id"]
        ev = mk_event(venue["user"]["id"], capacity=10, tickets_sold=6)
        h1 = NOW().replace(minute=5, second=0, microsecond=0) - timedelta(hours=1)
        mk_ticket(ev, g1, qty=2, checked_in=True, checked_in_at=h1)
        mk_ticket(ev, g2, qty=1, checked_in=True, checked_in_at=h1 + timedelta(minutes=20))
        mk_ticket(ev, g2, qty=3, checked_in=True, checked_in_at=h1 + timedelta(hours=1))
        mk_ticket(ev, g1, qty=1)  # not checked in
        mk_request(ev, g1)
        mk_request(ev, g2)
        mk_request(ev, g2, status="approved")
        r = requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(venue))
        assert r.status_code == 200, r.text
        d = r.json()
        assert (d["checked_in"], d["capacity"], d["tickets_sold"], d["waitlist"]) == (6, 10, 6, 2)
        assert [b["count"] for b in d["by_hour"]] == [3, 3]
        assert d["by_hour"][0]["hour"].startswith(h1.strftime("%Y-%m-%dT%H:00"))
        assert len(d["recent"]) == 3 and d["recent"][0]["quantity"] == 3
        names = {a["name"] for a in d["recent"]}
        assert names == {"TEST_ A.", "TEST_Solo"}, names
        assert d["deal"] is None

    def test_live_legacy_checkins_without_timestamp(self, venue):
        ev = mk_event(venue["user"]["id"])
        mk_ticket(ev, register()["user"]["id"], qty=4, checked_in=True)
        d = requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(venue)).json()
        assert d["checked_in"] == 4 and d["by_hour"] == [] and len(d["recent"]) == 1

    def test_live_permissions(self, venue):
        ev = mk_event(venue["user"]["id"])
        g = login("guest@nocturne.app", "GuestPass123!")
        p = login("promoter@nocturne.app", "PromoterPass123!")
        a = login("admin@nocturne.app", "AdminPass123!")
        assert requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(g)).status_code == 403
        assert requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(p)).status_code == 403
        assert requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(a)).status_code == 200
        assert requests.get(f"{API}/host/events/{ev['id']}/live").status_code in (401, 403)
        assert requests.get(f"{API}/host/events/nope-{uuid.uuid4()}/live", headers=h(a)).status_code == 404


# ---------- Last-minute deal ----------
class TestDeal:
    def test_validation(self, venue):
        own = venue["user"]["id"]
        g = register()["user"]["id"]
        ok = mk_event(own)
        mk_request(ok, g)
        u = f"{API}/host/events/{{}}/deal"
        assert requests.post(u.format(ok["id"]), json={"pct": 15}, headers=h(venue)).status_code == 400
        past = mk_event(own, date=NOW() - timedelta(hours=2))
        mk_request(past, g)
        assert requests.post(u.format(past["id"]), json={"pct": 20}, headers=h(venue)).status_code == 400
        full = mk_event(own, capacity=5, tickets_sold=5)
        mk_request(full, g)
        r = requests.post(u.format(full["id"]), json={"pct": 20}, headers=h(venue))
        assert r.status_code == 400 and "full" in r.json()["detail"]
        empty = mk_event(own)
        mk_request(empty, g, status="approved")
        r = requests.post(u.format(empty["id"]), json={"pct": 20}, headers=h(venue))
        assert r.status_code == 400 and "waitlist" in r.json()["detail"]
        guest = login("guest@nocturne.app", "GuestPass123!")
        assert requests.post(u.format(ok["id"]), json={"pct": 20}, headers=h(guest)).status_code == 403
        assert DB.events.count_documents({"id": {"$in": [ok["id"], past["id"], full["id"], empty["id"]]},
                                          "deal": {"$exists": True}}) == 0

    def test_send_deal_http_then_409_and_my_deal(self, venue):
        w1, w2, other = register(), register(), register()
        ev = mk_event(venue["user"]["id"], capacity=10, tickets_sold=4)
        mk_request(ev, w1["user"]["id"])
        mk_request(ev, w2["user"]["id"])
        r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 30}, headers=h(venue))
        assert r.status_code == 200, r.text
        assert r.json()["pct"] == 30 and r.json()["sent_to"] == 2
        stored = DB.events.find_one({"id": ev["id"]})["deal"]
        assert stored["pct"] == 30 and set(stored["user_ids"]) == {w1["user"]["id"], w2["user"]["id"]}
        assert stored["sent_at"] is not None
        r2 = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 50}, headers=h(venue))
        assert r2.status_code == 409
        assert DB.events.find_one({"id": ev["id"]})["deal"]["pct"] == 30
        live = requests.get(f"{API}/host/events/{ev['id']}/live", headers=h(venue)).json()
        assert live["deal"]["pct"] == 30 and live["deal"]["sent_to"] == 2
        md = requests.get(f"{API}/events/{ev['id']}/my-deal", headers=h(w1)).json()  # iter21: my-deal also returns qty/expires_at
        assert md["pct"] == 30 and md["qty"] == 1 and md["expires_at"]
        assert requests.get(f"{API}/events/{ev['id']}/my-deal", headers=h(other)).json() == {"pct": 0, "qty": 0, "expires_at": None}
        assert requests.get(f"{API}/events/{ev['id']}/my-deal").status_code in (401, 403)

    def test_deal_push_to_waitlist_respects_updates_pref(self, mods, venue):
        w1, w2 = register()["user"]["id"], register()["user"]["id"]
        DB.users.update_one({"id": w2}, {"$set": {"push_prefs.updates": False}})
        ev = mk_event(venue["user"]["id"])
        mk_request(ev, w1)
        mk_request(ev, w2)
        SENT.clear()
        user = DB.users.find_one({"id": venue["user"]["id"]}, {"_id": 0})
        out = call(mods, mods["hostlive"].send_deal(ev["id"], mods["hostlive"].DealIn(pct=20), user))
        assert out.sent_to == 2
        assert len(SENT) == 1 and SENT[0]["recipients"] == [w1], SENT
        assert SENT[0]["data"]["action_url"] == f"/event/{ev['id']}"
        assert SENT[0]["data"]["title"].startswith("20% off") and SENT[0]["key"] == f"deal-{ev['id']}"


# ---------- Deal pricing ----------
class TestDealPricing:
    def test_join_with_credit_discounted_only_for_deal_guest(self, venue):
        deal_g, plain = register(), register()
        for u in (deal_g, plain):
            grant_credit(u["user"]["id"], 500)
        ev = mk_event(venue["user"]["id"], price=50.0, capacity=10, tickets_sold=2)
        mk_request(ev, deal_g["user"]["id"])
        r = requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 20}, headers=h(venue))
        assert r.status_code == 200, r.text
        a = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(deal_g))
        b = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(plain))
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        ta, tb = a.json()["ticket"], b.json()["ticket"]
        assert a.json()["result"] == "ticket" and b.json()["result"] == "ticket"
        # deal guest: 50*0.8=40 + 15% fee = 46.00 ; plain: 50 + 7.50 = 57.50
        assert ta["credit_used"] == 46.0 and ta["platform_fee"] == 6.0, ta
        assert tb["credit_used"] == 57.5 and tb["platform_fee"] == 7.5, tb
        req = DB.event_requests.find_one({"event_id": ev["id"], "user_id": deal_g["user"]["id"]})
        assert req["status"] == "approved"

    def test_checkout_amount_discounted(self, venue):
        deal_g, plain = register(), register()
        ev = mk_event(venue["user"]["id"], price=40.0, capacity=10, tickets_sold=2)
        mk_request(ev, deal_g["user"]["id"])
        assert requests.post(f"{API}/host/events/{ev['id']}/deal", json={"pct": 50}, headers=h(venue)).status_code == 200
        body = {"kind": "ticket", "origin_url": BASE_URL, "event_id": ev["id"], "quantity": 1}
        a = requests.post(f"{API}/payments/checkout", json=body, headers=h(deal_g))
        b = requests.post(f"{API}/payments/checkout", json=body, headers=h(plain))
        if a.status_code == 503 or b.status_code == 503:
            pytest.skip("Stripe unavailable")
        assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
        assert a.json()["amount"] == 23.0, a.json()   # 40*0.5=20 + 3 fee
        assert b.json()["amount"] == 46.0, b.json()   # 40 + 6 fee


# ---------- Recap email ----------
class TestRecapEmail:
    def test_recap_emails_with_chart_and_pref(self, mods):
        on = register("promoter", name="TEST_ Rita Promo")
        off = register("promoter")
        DB.users.update_one({"id": off["user"]["id"]}, {"$set": {"email_prefs.recap": False}})
        ev = mk_event(None, date=NOW() + timedelta(days=3))
        buyer = register()["user"]["id"]
        mk_ticket(ev, buyer, qty=2, promoter_id=on["user"]["id"], promoter_earning=9.0, created_at=NOW() - timedelta(days=1))
        mk_ticket(ev, buyer, qty=1, promoter_id=on["user"]["id"], promoter_earning=3.0)
        MAILS.clear()
        SENT.clear()
        call(mods, mods["alerts"].send_promoter_recap(force=True))
        to = {m["to"]: m for m in MAILS}
        assert on["user"]["email"] in to and off["user"]["email"] not in to, list(to)
        m = to[on["user"]["email"]]
        assert m["subject"] == "Your week: 3 guests · $12.00 earned", m["subject"]
        assert m["html"].count('valign="bottom"') == 7
        assert "Hi TEST_," in m["html"] and "$12.00" in m["html"] and "#d4af37" in m["html"]
        assert {s["recipients"][0] for s in SENT} >= {on["user"]["id"], off["user"]["id"]}  # push still for both

    def test_recap_html_render(self, mods):
        since = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
        html = mods["alerts"].recap_html("<b>Zed</b> X", {"guests": 5, "earnings": 1234.5}, 3,
                                         {"2026-01-07": (3, 1000.0), "2026-01-09": (2, 234.5)}, since)
        assert html.count('valign="bottom"') == 7
        assert "&lt;b&gt;Zed&lt;/b&gt;" in html and "<b>Zed" not in html
        assert "<strong>#3</strong>" in html and "$1,234.50" in html and "$1,000" in html
        assert "height:110px" in html and "Keep the momentum" in html
        quiet = mods["alerts"].recap_html("Q", {"guests": 0, "earnings": 0.0}, None, {}, since)
        assert "Quiet week" in quiet and "leaderboard.</p>" in quiet and "<strong>#" not in quiet


# ---------- Email prefs ----------
class TestEmailPrefsRecap:
    def test_recap_pref_roundtrip(self):
        p = register("promoter")
        d = requests.get(f"{API}/me/email-prefs", headers=h(p)).json()
        assert d["recap"] is True
        r = requests.put(f"{API}/me/email-prefs", json={"recap": False}, headers=h(p))
        assert r.status_code == 200 and r.json()["recap"] is False and r.json()["reminders"] is True
        assert requests.get(f"{API}/me/email-prefs", headers=h(p)).json()["recap"] is False
