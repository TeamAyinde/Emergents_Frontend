"""Iteration 24: monthly report CSV download (GET /api/host/report.csv) + deal leaderboard used by the DealCard tip."""
import csv
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
LA = ZoneInfo("America/Los_Angeles")
C = {"users": [], "events": [], "tickets": [], "venues": [], "payables": [], "feedback": [], "tables": []}
MONTH = "2025-11"
M0 = datetime(2025, 11, 1, tzinfo=timezone.utc)
HEADER = ["Month", "Venue", "Date", "Event", "Tickets sold", "Guests in", "Show-up %", "No-shows", "Tables booked",
          "Ticket & table revenue (USD)", "Avg rating", "Ratings"]


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def register(role="guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_i24_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": "TEST_ I24 User", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    u = r.json()
    C["users"].append(u["user"]["id"])
    return u


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def mk_venue(owner_id, name):
    doc = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": name, "owner_id": owner_id, "city": "Los Angeles", "state": "CA",
           "category": "Nightclub", "image_url": "", "rating": 4.5, "price_range": "$$", "description": "TEST_",
           "min_level": "bronze", "created_at": M0}
    DB.venues.insert_one(dict(doc))
    C["venues"].append(doc["id"])
    return doc


def mk_event(owner, venue, date, title, **kw):
    doc = {"id": str(uuid.uuid4()), "title": title, "venue_id": venue["id"], "venue_name": venue["name"], "city": "Los Angeles",
           "date": date, "price": 30, "tags": [], "tickets_sold": 0, "created_at": date - timedelta(days=5), "min_level": "bronze",
           "approval_required": False, "capacity": 50, "plus_one_limit": 5, "tables": [], "created_by": owner, "image_url": "",
           "summary_sent": True}
    doc.update(kw)
    DB.events.insert_one(dict(doc))
    C["events"].append(doc["id"])
    return doc


def mk_ticket(ev, uid, qty, created, checked=False, paid=0.0):
    tid = str(uuid.uuid4())
    DB.tickets.insert_one({"id": tid, "event_id": ev["id"], "event_title": ev["title"], "event_date": ev["date"],
                           "venue_name": ev["venue_name"], "user_id": uid, "promoter_id": None, "quantity": qty,
                           "total_paid": paid, "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0,
                           "venue_share": 0.0, "checked_in": checked, "checked_in_at": ev["date"] if checked else None,
                           "created_at": created})
    C["tickets"].append(tid)
    return tid


def mk_payable(venue, record_id, amount, created):
    pid = str(uuid.uuid4())
    DB.venue_payables.insert_one({"id": pid, "venue_id": venue["id"], "record_id": record_id, "amount": amount,
                                  "kind": "ticket", "status": "pending", "created_at": created})
    C["payables"].append(pid)


def mk_feedback(venue, ev, uid, rating, created):
    fid = str(uuid.uuid4())
    DB.feedback.insert_one({"id": fid, "venue_id": venue["id"], "event_id": ev["id"], "user_id": uid, "rating": rating,
                            "created_at": created})
    C["feedback"].append(fid)


def parse(text):
    return list(csv.reader(io.StringIO(text)))


@pytest.fixture(scope="module")
def venue():
    return login("venue@nocturne.app", "VenuePass123!")


@pytest.fixture(scope="module")
def admin():
    return login("admin@nocturne.app", "AdminPass123!")


@pytest.fixture(scope="module")
def guest():
    return login("guest@nocturne.app", "GuestPass123!")


@pytest.fixture(scope="module")
def seeded(venue):
    owner = venue["user"]["id"]
    other = register("venue_owner")
    va = mk_venue(owner, "TEST_ I24 AAA Lounge")
    vo = mk_venue(other["user"]["id"], "TEST_ I24 Other Owner Club")
    g = [f"TEST_g{i}" for i in range(4)]
    # Nov 8 05:00 UTC == Nov 7 21:00 LA
    e1 = mk_event(owner, va, datetime(2025, 11, 8, 5, 0, tzinfo=timezone.utc), "TEST_ I24 Night One")
    e2 = mk_event(owner, va, datetime(2025, 11, 20, 6, 30, tzinfo=timezone.utc), "TEST_ I24 Night Two, \"quoted\"")
    eout = mk_event(owner, va, datetime(2025, 10, 20, 6, 0, tzinfo=timezone.utc), "TEST_ I24 October Night")
    eo = mk_event(other["user"]["id"], vo, datetime(2025, 11, 10, 6, 0, tzinfo=timezone.utc), "TEST_ I24 Other Night")
    t1 = mk_ticket(e1, g[0], 2, M0 + timedelta(days=2), checked=True, paid=60)
    t2 = mk_ticket(e1, g[1], 1, M0 + timedelta(days=3), checked=False, paid=30)
    t3 = mk_ticket(e2, g[2], 3, M0 + timedelta(days=10), checked=True, paid=90)
    mk_ticket(eout, g[3], 1, M0 - timedelta(days=15), checked=True, paid=30)
    mk_ticket(eo, g[3], 4, M0 + timedelta(days=5), checked=True, paid=120)
    tb = str(uuid.uuid4())
    DB.table_bookings.insert_one({"id": tb, "event_id": e2["id"], "user_id": g[0], "status": "confirmed", "created_at": M0 + timedelta(days=11)})
    C["tables"].append(tb)
    for rid, amt, d in ((t1, 48.0, 2), (t2, 24.0, 3), (t3, 72.0, 10), (tb, 100.0, 11)):
        mk_payable(va, rid, amt, M0 + timedelta(days=d))
    mk_feedback(va, e1, g[0], 5, M0 + timedelta(days=8))
    mk_feedback(va, e1, g[1], 4, M0 + timedelta(days=8))
    mk_feedback(va, e2, g[2], 3, M0 + timedelta(days=21))
    return {"va": va, "vo": vo, "e1": e1, "e2": e2, "other": other}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.table_bookings.delete_many({"id": {"$in": C["tables"]}})
    DB.venue_payables.delete_many({"id": {"$in": C["payables"]}})
    DB.feedback.delete_many({"id": {"$in": C["feedback"]}})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


# ---------- report.csv: access + validation ----------

class TestReportCsvAccess:
    def test_unauthenticated(self):
        r = requests.get(f"{API}/host/report.csv?month={MONTH}")
        assert r.status_code in (401, 403)

    def test_guest_forbidden(self, guest):
        r = requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(guest))
        assert r.status_code == 403

    @pytest.mark.parametrize("bad", ["2025-13", "nov", "2025/11", "11-2025"])
    def test_bad_month(self, venue, bad):
        r = requests.get(f"{API}/host/report.csv", params={"month": bad}, headers=h(venue))
        assert r.status_code == 400
        assert "Month must look like" in r.json()["detail"]

    def test_default_month_is_current(self, venue):
        r = requests.get(f"{API}/host/report.csv", headers=h(venue))
        assert r.status_code == 200
        label = datetime.now(timezone.utc).strftime("%Y-%m")
        assert f'filename="nocturne-report-{label}.csv"' in r.headers["content-disposition"]
        assert parse(r.text)[0] == HEADER


# ---------- report.csv: contents ----------

class TestReportCsvContent:
    def test_headers_and_rows(self, venue, seeded):
        r = requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(venue))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.headers["content-disposition"] == f'attachment; filename="nocturne-report-{MONTH}.csv"'
        rows = parse(r.text)
        assert rows[0] == HEADER
        mine = [x for x in rows[1:] if x[1] == seeded["va"]["name"]]
        ev_rows = [x for x in mine if x[2] != "TOTAL"]
        assert [x[3] for x in ev_rows] == [seeded["e1"]["title"], seeded["e2"]["title"]]  # October event excluded, sorted by date
        one, two = ev_rows
        assert one == [MONTH, seeded["va"]["name"], "2025-11-07 21:00", seeded["e1"]["title"], "3", "2", "66.7", "1", "0", "72.00", "4.5", "2"]
        assert two == [MONTH, seeded["va"]["name"], "2025-11-19 22:30", seeded["e2"]["title"], "3", "3", "100.0", "0", "1", "172.00", "3.0", "1"]
        assert mine[-1][2] == "TOTAL"

    def test_owner_only_sees_own_venues(self, venue, seeded):
        rows = parse(requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(venue)).text)
        assert not any(x[1] == seeded["vo"]["name"] for x in rows)
        assert not any(x[3] == "TEST_ I24 Other Night" for x in rows)

    def test_total_matches_host_report(self, venue, seeded):
        rows = parse(requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(venue)).text)
        tot = next(x for x in rows if x[1] == seeded["va"]["name"] and x[2] == "TOTAL")
        rep = requests.get(f"{API}/host/report?month={MONTH}", headers=h(venue)).json()
        cur = next(r for r in rep if r["venue_id"] == seeded["va"]["id"])["current"]
        assert cur["events"] == 2 and cur["sold"] == 6 and cur["arrived"] == 5
        assert tot[3].startswith(f"{cur['events']} events")
        assert int(tot[4]) == cur["sold"] and int(tot[5]) == cur["arrived"]
        assert float(tot[6]) == cur["show_rate"]
        assert int(tot[7]) == cur["sold"] - cur["arrived"]
        assert float(tot[9]) == cur["revenue"] == 244.0
        assert float(tot[10]) == cur["rating"] == 4.0
        assert int(tot[11]) == cur["ratings"] == 3

    def test_admin_sees_all_venues(self, admin, seeded):
        r = requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(admin))
        assert r.status_code == 200
        rows = parse(r.text)
        names = {x[1] for x in rows[1:]}
        assert seeded["va"]["name"] in names and seeded["vo"]["name"] in names
        other = [x for x in rows if x[1] == seeded["vo"]["name"] and x[2] != "TOTAL"]
        assert other[0][4] == "4" and other[0][5] == "4"
        # every venue gets a TOTAL row
        totals = {x[1] for x in rows[1:] if x[2] == "TOTAL"}
        assert names == totals

    def test_other_owner_sees_only_theirs(self, seeded):
        rows = parse(requests.get(f"{API}/host/report.csv?month={MONTH}", headers=h(seeded["other"])).text)
        assert {x[1] for x in rows[1:]} == {seeded["vo"]["name"]}


# ---------- deal leaderboard (feeds DealCard tip) ----------

class TestDealLeaderboardTip:
    def test_best_level_first(self, venue, seeded):
        now = datetime.now(timezone.utc)
        owner = venue["user"]["id"]
        w = [f"TEST_w{i}" for i in range(4)]
        for pct, users, buyers in ((20, w, w[:1]), (30, w[:2], w[:2])):
            sent = now - timedelta(days=3)
            pe = mk_event(owner, seeded["va"], now - timedelta(days=2), f"TEST_ I24 Deal {pct}",
                          deal={"pct": pct, "user_ids": users, "sent_at": sent, "expires_at": sent + timedelta(hours=2)})
            for b in buyers:
                mk_ticket(pe, b, 2, sent + timedelta(minutes=15), paid=60.0)
        r = requests.get(f"{API}/host/deals/leaderboard", headers=h(venue))
        assert r.status_code == 200
        data = r.json()
        assert [d["pct"] for d in data] == [30, 20]
        assert data[0]["conversion"] == 100.0 and data[0]["revenue"] == 120.0 and data[0]["buyers"] == 2
        assert data[1]["conversion"] == 25.0
        # other owner sees none
        assert requests.get(f"{API}/host/deals/leaderboard", headers=h(seeded["other"])).json() == []

    def test_guest_forbidden(self, guest):
        assert requests.get(f"{API}/host/deals/leaderboard", headers=h(guest)).status_code == 403
