"""Nocturne iteration 5: concierge chat, table map, join/approval/waitlist, guest list, host studio.
All created data is tracked by id and removed at module teardown; seeded users reset to bronze / wallet 0."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
GUEST = ("guest@nocturne.app", "GuestPass123!")
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
VENUE = ("venue@nocturne.app", "VenuePass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")
C = {"tickets": [], "bookings": [], "requests": [], "messages": [], "thread_members": set(), "venues": [], "events": []}
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {creds[0]}: {r.status_code}")
    return r.json()


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


def future(days=10):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def ev_by(title, venue=None):
    for e in requests.get(f"{API}/events").json():
        if e["title"] == title and (venue is None or e["venue_name"] == venue):
            return e
    pytest.skip(f"event {title} not found")


def track_join(r):
    d = r.json()
    if d.get("ticket"):
        C["tickets"].append(d["ticket"]["id"])
    if d.get("request"):
        C["requests"].append(d["request"]["id"])
    return d


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for t in DB.tickets.find({"$or": [{"id": {"$in": C["tickets"]}}, {"event_id": {"$in": C["events"]}}]}):
        DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
        DB.tickets.delete_one({"id": t["id"]})
    # tickets issued by host approval: find by request -> event/user created after test start
    DB.table_bookings.delete_many({"id": {"$in": C["bookings"]}})
    DB.event_requests.delete_many({"id": {"$in": C["requests"]}})
    DB.concierge_messages.delete_many({"id": {"$in": C["messages"]}})
    for m in C["thread_members"]:
        if DB.concierge_messages.count_documents({"member_id": m}) == 0:
            DB.concierge_threads.delete_one({"member_id": m})
    DB.events.delete_many({"id": {"$in": C["events"]}})
    DB.venues.delete_many({"id": {"$in": C["venues"]}})
    DB.users.update_many({"email": {"$in": [GUEST[0], PROMOTER[0], VENUE[0], ADMIN[0]]}},
                         {"$set": {"level": "bronze", "wallet_balance": 0}})
    DB.events.update_many({"title": "Rooftop Reverie"}, {"$set": {"capacity": 2}})


@pytest.fixture(scope="module")
def guest():
    return login(GUEST)


@pytest.fixture(scope="module")
def promoter():
    DB.users.update_one({"email": PROMOTER[0]}, {"$set": {"level": "silver"}})
    return login(PROMOTER)


@pytest.fixture(scope="module")
def owner():
    return login(VENUE)


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN)


def msg_ids(u):
    for m in requests.get(f"{API}/concierge/messages", headers=h(u)).json():
        C["messages"].append(m["id"])
        C["thread_members"].add(m["member_id"])


# Concierge chat
class TestConcierge:
    def test_first_message_auto_welcome_and_unread(self, guest):
        r = requests.post(f"{API}/concierge/messages", json={"text": "TEST_ need a table Friday"}, headers=h(guest))
        assert r.status_code == 201, r.text
        assert r.json()["sender"] == "member"
        C["messages"].append(r.json()["id"]); C["thread_members"].add(r.json()["member_id"])
        assert requests.get(f"{API}/concierge/unread", headers=h(guest)).json()["unread"] == 1
        msgs = requests.get(f"{API}/concierge/messages", headers=h(guest)).json()
        msg_ids(guest)
        assert [m["sender"] for m in msgs] == ["member", "concierge"]
        assert "Welcome" in msgs[1]["text"]
        assert requests.get(f"{API}/concierge/unread", headers=h(guest)).json()["unread"] == 0
        r2 = requests.post(f"{API}/concierge/messages", json={"text": "TEST_ second"}, headers=h(guest))
        C["messages"].append(r2.json()["id"])
        assert len(requests.get(f"{API}/concierge/messages", headers=h(guest)).json()) == 3  # no second welcome
        assert requests.post(f"{API}/concierge/messages", json={"text": ""}, headers=h(guest)).status_code == 422
        assert requests.post(f"{API}/concierge/messages", json={"text": "   "}, headers=h(guest)).status_code == 400

    def test_admin_threads_order_and_reply(self, guest, owner, admin):
        r = requests.post(f"{API}/concierge/messages", json={"text": "TEST_ gold owner ask"}, headers=h(owner))
        assert r.status_code == 201
        msg_ids(owner)
        assert requests.get(f"{API}/admin/concierge/threads", headers=h(guest)).status_code == 403
        th = requests.get(f"{API}/admin/concierge/threads", headers=h(admin)).json()
        mine = [t for t in th if t["member_id"] in C["thread_members"]]
        assert mine[0]["member_level"] == "gold" and mine[0]["unread"] >= 1, mine
        gid = guest["user"]["id"]
        gthread = next(t for t in th if t["member_id"] == gid)
        assert gthread["unread"] == 2 and gthread["member_level"] == "bronze"
        assert requests.get(f"{API}/admin/concierge/{gid}/messages", headers=h(guest)).status_code == 403
        msgs = requests.get(f"{API}/admin/concierge/{gid}/messages", headers=h(admin)).json()
        assert len(msgs) == 3
        th = requests.get(f"{API}/admin/concierge/threads", headers=h(admin)).json()
        assert next(t for t in th if t["member_id"] == gid)["unread"] == 0
        # read threads go after unread ones
        idx = {t["member_id"]: i for i, t in enumerate(th)}
        assert idx[owner["user"]["id"]] < idx[gid]
        rep = requests.post(f"{API}/admin/concierge/{gid}/messages", json={"text": "TEST_ done, T1 held"}, headers=h(admin))
        assert rep.status_code == 201 and rep.json()["sender"] == "concierge"
        C["messages"].append(rep.json()["id"])
        assert requests.get(f"{API}/concierge/unread", headers=h(guest)).json()["unread"] == 1
        assert requests.post(f"{API}/admin/concierge/nope/messages", json={"text": "x"}, headers=h(admin)).status_code == 404
        msg_ids(owner)


# Table map
class TestTables:
    def test_tables_and_booking_rules(self, guest, owner, promoter):
        ev = ev_by("Velvet Sessions w/ DJ Nyx")
        tables = requests.get(f"{API}/events/{ev['id']}/tables").json()
        assert len(tables) == 8
        byid = {t["id"]: t for t in tables}
        assert byid["V1"]["min_level"] == "silver" and byid["S1"]["min_level"] == "silver" and byid["T1"]["min_level"] == "bronze"
        url = f"{API}/events/{ev['id']}/tables"
        assert requests.post(f"{url}/T1/book", json={"party_size": 7}, headers=h(guest)).status_code == 400
        assert requests.post(f"{url}/V1/book", json={"party_size": 2}, headers=h(guest)).status_code == 403
        assert requests.post(f"{url}/ZZ/book", json={"party_size": 2}, headers=h(guest)).status_code == 404
        r = requests.post(f"{url}/T1/book", json={"party_size": 4}, headers=h(guest))
        assert r.status_code == 201, r.text
        b = r.json(); C["bookings"].append(b["id"])
        assert b["platform_fee"] == round(byid["T1"]["min_spend"] * 0.25, 2)
        assert b["total"] == round(byid["T1"]["min_spend"] + b["platform_fee"], 2)
        dup = requests.post(f"{url}/T1/book", json={"party_size": 2}, headers=h(owner))
        assert dup.status_code == 409, dup.text
        r = requests.post(f"{url}/V1/book", json={"party_size": 8}, headers=h(owner))
        assert r.status_code == 201; C["bookings"].append(r.json()["id"])
        assert r.json()["platform_fee"] == round(byid["V1"]["min_spend"] * 0.15, 2)
        r = requests.post(f"{url}/T2/book", json={"party_size": 2}, headers=h(promoter))
        assert r.status_code == 201; C["bookings"].append(r.json()["id"])
        assert r.json()["platform_fee"] == round(byid["T2"]["min_spend"] * 0.20, 2)
        booked = {t["id"]: t["booked"] for t in requests.get(url).json()}
        assert booked["T1"] and booked["V1"] and booked["T2"] and not booked["T3"]
        mine = requests.get(f"{API}/table-bookings/mine", headers=h(guest)).json()
        assert any(m["table_id"] == "T1" and m["event_id"] == ev["id"] for m in mine)


# Join: ticket / pending / waitlisted
class TestJoin:
    def test_join_ticket_and_limits(self, guest):
        ev = ev_by("Velvet Sessions w/ DJ Nyx")
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 5}, headers=h(guest))
        assert r.status_code == 400
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 2}, headers=h(guest))
        assert r.status_code == 200 and track_join(r)["result"] == "ticket"
        g = requests.get(f"{API}/events/{ev['id']}/guests", headers=h(guest)).json()
        assert g["visible"] and g["count"] >= 2 and any(n.startswith(guest["user"]["full_name"].split()[0]) for n in g["names"])
        assert requests.get(f"{API}/events/{ev['id']}/guests").status_code in (401, 403)

    def test_approval_event_pending(self, guest):
        ev = ev_by("Industry Fridays")
        r = requests.post(f"{API}/tickets/purchase", json={"event_id": ev["id"], "quantity": 1}, headers=h(guest))
        assert r.status_code == 409
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 2, "note": "TEST_"}, headers=h(guest))
        assert r.status_code == 200 and track_join(r)["result"] == "pending"
        assert requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(guest)).status_code == 400
        mine = requests.get(f"{API}/event-requests/mine", headers=h(guest)).json()
        assert any(m["event_id"] == ev["id"] and m["status"] == "pending" and m["kind"] == "approval" for m in mine)

    def test_waitlist_when_full(self, guest, promoter):
        ev = ev_by("Rooftop Reverie")
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 2}, headers=h(guest))
        assert r.status_code == 200 and track_join(r)["result"] == "ticket"
        r = requests.post(f"{API}/tickets/purchase", json={"event_id": ev["id"], "quantity": 1}, headers=h(promoter))
        assert r.status_code == 409
        r = requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1}, headers=h(promoter))
        assert r.status_code == 200 and track_join(r)["result"] == "waitlisted"
        assert r.json()["request"]["kind"] == "waitlist"


# Host studio
class TestHost:
    def test_host_venues(self, owner, guest, promoter):
        names = {v["name"] for v in requests.get(f"{API}/host/venues", headers=h(owner)).json()}
        assert names == {"Mirage Lounge", "Club Noire", "Harbor House", "The Ember Room"}, names
        assert requests.get(f"{API}/host/venues", headers=h(guest)).status_code == 403
        body = {"name": "TEST_Venue", "city": "Los Angeles", "category": "Lounge", "image_url": "http://x.com/a.jpg"}
        assert requests.post(f"{API}/host/venues", json=body, headers=h(owner)).status_code == 400
        body["image_url"] = "https://images.unsplash.com/photo-1"
        r = requests.post(f"{API}/host/venues", json=body, headers=h(owner))
        assert r.status_code == 201; C["venues"].append(r.json()["id"])
        assert requests.post(f"{API}/host/venues", json=body, headers=h(promoter)).status_code == 403

    def test_host_events_and_decisions(self, owner, guest, promoter, admin):
        if_ev = ev_by("Industry Fridays"); rr = ev_by("Rooftop Reverie")
        evs = {e["id"]: e for e in requests.get(f"{API}/host/events", headers=h(owner)).json()}
        assert if_ev["id"] in evs and evs[if_ev["id"]]["pending_requests"] >= 1 and evs[if_ev["id"]]["approval_required"]
        assert all(e["venue_name"] in {"Mirage Lounge", "Club Noire", "Harbor House", "The Ember Room", "TEST_Venue"} for e in evs.values())
        det = requests.get(f"{API}/host/events/{if_ev['id']}", headers=h(owner)).json()
        req = next(r for r in det["requests"] if r["id"] in C["requests"])
        assert requests.post(f"{API}/host/requests/{req['id']}", json={"action": "approve"}, headers=h(promoter)).status_code == 403
        assert requests.post(f"{API}/host/requests/{req['id']}", json={"action": "maybe"}, headers=h(owner)).status_code == 400
        r = requests.post(f"{API}/host/requests/{req['id']}", json={"action": "approve"}, headers=h(owner))
        assert r.status_code == 200 and r.json()["status"] == "approved"
        assert requests.post(f"{API}/host/requests/{req['id']}", json={"action": "decline"}, headers=h(owner)).status_code == 400
        det = requests.get(f"{API}/host/events/{if_ev['id']}", headers=h(owner)).json()
        t = [g for g in det["guests"] if g["quantity"] == 2]
        assert t, det["guests"]
        C["tickets"] += [g["ticket_id"] for g in det["guests"]]
        assert requests.get(f"{API}/events/{if_ev['id']}").json()["tickets_sold"] == if_ev["tickets_sold"] + 2
        # waitlist approve grows capacity
        det = requests.get(f"{API}/host/events/{rr['id']}", headers=h(owner)).json()
        wl = next(r for r in det["requests"] if r["kind"] == "waitlist" and r["id"] in C["requests"])
        assert requests.post(f"{API}/host/requests/{wl['id']}", json={"action": "approve"}, headers=h(owner)).status_code == 200
        after = requests.get(f"{API}/events/{rr['id']}").json()
        assert after["tickets_sold"] == 3 and after["capacity"] == 3, after
        det = requests.get(f"{API}/host/events/{rr['id']}", headers=h(owner)).json()
        C["tickets"] += [g["ticket_id"] for g in det["guests"]]
        assert requests.get(f"{API}/host/events/{rr['id']}", headers=h(guest)).status_code == 403

    def test_create_event_validation_and_tables(self, owner, admin, guest):
        venues = {v["name"]: v for v in requests.get(f"{API}/venues").json()}
        base = {"title": "TEST_HostNight", "venue_id": venues["Mirage Lounge"]["id"], "date": future(),
                "price": 30, "image_url": "https://images.unsplash.com/photo-2", "description": "TEST",
                "min_level": "bronze", "capacity": 50, "plus_one_limit": 1, "table_min_spend": 500,
                "approval_required": True, "guest_list_visible": False}
        other = dict(base, venue_id=venues["Palm Pavilion"]["id"])
        assert requests.post(f"{API}/events", json=other, headers=h(owner)).status_code == 403
        assert requests.post(f"{API}/events", json=dict(base, image_url="http://x"), headers=h(owner)).status_code == 400
        assert requests.post(f"{API}/events", json=dict(base, price=-1), headers=h(owner)).status_code == 400
        assert requests.post(f"{API}/events", json=dict(base, min_level="platinum"), headers=h(owner)).status_code == 400
        assert requests.post(f"{API}/events", json=base, headers=h(guest)).status_code == 403
        r = requests.post(f"{API}/events", json=base, headers=h(owner))
        assert r.status_code == 201, r.text
        e = r.json(); C["events"].append(e["id"])
        tables = requests.get(f"{API}/events/{e['id']}/tables").json()
        assert len(tables) == 8 and next(t for t in tables if t["id"] == "S1")["min_spend"] == 2000
        g = requests.get(f"{API}/events/{e['id']}/guests", headers=h(guest)).json()
        assert g["visible"] is False and g["names"] == []
        assert requests.post(f"{API}/events/{e['id']}/join", json={"quantity": 3}, headers=h(guest)).status_code == 400
        r = requests.post(f"{API}/events/{e['id']}/join", json={"quantity": 2}, headers=h(guest))
        assert track_join(r)["result"] == "pending"
        r = requests.post(f"{API}/host/requests/{r.json()['request']['id']}", json={"action": "decline"}, headers=h(owner))
        assert r.json()["status"] == "declined"
        r = requests.post(f"{API}/events", json=dict(base, table_min_spend=None, title="TEST_NoTables"), headers=h(owner))
        C["events"].append(r.json()["id"])
        assert requests.get(f"{API}/events/{r.json()['id']}/tables").json() == []
        # admin can create at any venue; owner cannot manage it
        r = requests.post(f"{API}/events", json=other, headers=h(admin))
        assert r.status_code == 201; C["events"].append(r.json()["id"])
        assert requests.get(f"{API}/host/events/{r.json()['id']}", headers=h(owner)).status_code == 403
        assert requests.get(f"{API}/host/events/{r.json()['id']}", headers=h(admin)).status_code == 200
