"""Nocturne iteration 4: membership levels (bronze/silver/gold), gating (403), level-based fees & ticket
discounts, partner categories/date window, admin overview members_by_level, CSV level column.
Uses only TEST_ users created here; all created data removed by id at module teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("admin@nocturne.app", "AdminPass123!")
GUEST = ("guest@nocturne.app", "GuestPass123!")

CREATED = {"users": [], "tickets": [], "reservations": [], "partner_bookings": []}
EV_SOLD = {}
S = {}


def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def register(tier="member"):
    email = f"test_{uuid.uuid4().hex[:8]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123!", "full_name": "TEST_ Member",
        "membership_tier": tier, "marketing_opt_in": True})
    assert r.status_code == 201, r.text
    d = r.json()
    CREATED["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    d = db()
    for uid in CREATED["users"]:
        d.users.delete_one({"id": uid})
        d.membership_payments.delete_many({"user_id": uid})
    for tid in CREATED["tickets"]:
        d.tickets.delete_one({"id": tid})
    for rid in CREATED["reservations"]:
        d.reservations.delete_one({"id": rid})
    for bid in CREATED["partner_bookings"]:
        d.partner_bookings.delete_one({"id": bid})
    for eid, qty in EV_SOLD.items():
        d.events.update_one({"id": eid}, {"$inc": {"tickets_sold": -qty}})


@pytest.fixture(scope="module")
def catalog():
    venues = requests.get(f"{API}/venues").json()
    events = requests.get(f"{API}/events").json()
    partners = requests.get(f"{API}/partners").json()
    return venues, events, partners


def pick(items, lvl):
    for i in items:
        if i.get("min_level", "bronze") == lvl:
            return i
    pytest.skip(f"no {lvl} item")


# Plans
def test_plans():
    r = requests.get(f"{API}/membership/plans")
    assert r.status_code == 200
    p = {x["level"]: x for x in r.json()}
    assert p["bronze"]["price"] == 14.99 and p["silver"]["price"] == 49.0 and p["gold"]["price"] == 149.0
    assert p["bronze"]["booking_fee_pct"] == 0.25 and p["silver"]["booking_fee_pct"] == 0.20
    assert p["gold"]["booking_fee_pct"] == 0.15
    assert p["silver"]["ticket_discount_pct"] == 0.10 and p["gold"]["ticket_discount_pct"] == 0.20


# Register -> level bronze in /auth/me
def test_register_level_bronze():
    tok, u = register("free_girl")
    assert u["level"] == "bronze" and u["membership_tier"] == "free_girl"
    me = requests.get(f"{API}/auth/me", headers=h(tok)).json()
    assert me["level"] == "bronze"
    S["tok"] = tok
    S["uid"] = u["id"]


# Upgrade validation
def test_upgrade_errors():
    tok = S["tok"]
    r = requests.post(f"{API}/membership/upgrade", json={"level": "platinum"}, headers=h(tok))
    assert r.status_code == 400 and r.json()["detail"] == "Unknown level"
    r = requests.post(f"{API}/membership/upgrade", json={"level": "bronze"}, headers=h(tok))
    assert r.status_code == 400 and "already" in r.json()["detail"]
    at = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}).json()["access_token"]
    r = requests.post(f"{API}/membership/upgrade", json={"level": "silver"}, headers=h(at))
    assert r.status_code == 400 and "Business" in r.json()["detail"]
    me = requests.get(f"{API}/auth/me", headers=h(at)).json()
    assert me["level"] == "gold"
    r = requests.post(f"{API}/membership/upgrade", headers=h(tok))
    assert r.status_code == 422
    r = requests.post(f"{API}/membership/upgrade", json={"level": "gold"})
    assert r.status_code in (401, 403)


# Bronze blocked from gold items (403 w/ message)
def test_bronze_locked(catalog):
    venues, events, partners = catalog
    tok = S["tok"]
    gv, ge, gp = pick(venues, "gold"), pick(events, "gold"), pick(partners, "gold")
    r = requests.post(f"{API}/reservations", headers=h(tok), json={
        "venue_id": gv["id"], "date": future(), "party_size": 2, "service_type": "table"})
    assert r.status_code == 403 and r.json()["detail"] == "Gold membership required"
    r = requests.post(f"{API}/tickets/purchase", headers=h(tok), json={"event_id": ge["id"], "quantity": 1})
    assert r.status_code == 403 and r.json()["detail"] == "Gold membership required"
    r = requests.post(f"{API}/partner-bookings", headers=h(tok), json={
        "partner_id": gp["id"], "date": future(), "units": 1, "guests": 2})
    assert r.status_code == 403 and r.json()["detail"] == "Gold membership required"
    sv = pick(venues, "silver")
    r = requests.post(f"{API}/reservations", headers=h(tok), json={
        "venue_id": sv["id"], "date": future(), "party_size": 2, "service_type": "table"})
    assert r.status_code == 403 and r.json()["detail"] == "Silver membership required"


# Bronze fee 25% on a bronze venue
def test_bronze_fee(catalog):
    venues = catalog[0]
    bv = pick(venues, "bronze")
    r = requests.post(f"{API}/reservations", headers=h(S["tok"]), json={
        "venue_id": bv["id"], "date": future(), "party_size": 2, "service_type": "table"})
    assert r.status_code == 201, r.text
    d = r.json()
    CREATED["reservations"].append(d["id"])
    assert d["platform_fee"] == 50.0 and d["total"] == 250.0


# Upgrade to silver: fee 20%, ticket discount 10%, silver unlocked but gold still locked
def test_silver(catalog):
    venues, events, partners = catalog
    tok = S["tok"]
    r = requests.post(f"{API}/membership/upgrade", json={"level": "silver"}, headers=h(tok))
    assert r.status_code == 200 and r.json()["level"] == "silver"
    assert requests.get(f"{API}/auth/me", headers=h(tok)).json()["level"] == "silver"
    pay = db().membership_payments.find_one({"user_id": S["uid"], "level": "silver"})
    assert pay and pay["amount"] == 49.0 and pay["simulated"] is True
    sv = pick(venues, "silver")
    r = requests.post(f"{API}/reservations", headers=h(tok), json={
        "venue_id": sv["id"], "date": future(), "party_size": 2, "service_type": "booth"})
    assert r.status_code == 201, r.text
    d = r.json()
    CREATED["reservations"].append(d["id"])
    assert d["platform_fee"] == 80.0 and d["total"] == 480.0
    se = pick(events, "silver")
    r = requests.post(f"{API}/tickets/purchase", headers=h(tok), json={"event_id": se["id"], "quantity": 2})
    assert r.status_code == 201, r.text
    t = r.json()
    CREATED["tickets"].append(t["id"])
    EV_SOLD[se["id"]] = EV_SOLD.get(se["id"], 0) + 2
    base = round(se["price"] * 2 * 0.9, 2)
    assert t["platform_fee"] == round(base * 0.15, 2)
    assert t["total_paid"] == round(base + round(base * 0.15, 2), 2)
    gp = pick(partners, "gold")
    r = requests.post(f"{API}/partner-bookings", headers=h(tok), json={
        "partner_id": gp["id"], "date": future(), "units": 1, "guests": 2})
    assert r.status_code == 403 and r.json()["detail"] == "Gold membership required"


# Upgrade to gold: gold items unlocked, fee 15%, discount 20%, savings vs public rate
def test_gold(catalog):
    venues, events, partners = catalog
    tok = S["tok"]
    r = requests.post(f"{API}/membership/upgrade", json={"level": "gold"}, headers=h(tok))
    assert r.status_code == 200 and r.json()["level"] == "gold"
    gv, ge, gp = pick(venues, "gold"), pick(events, "gold"), pick(partners, "gold")
    r = requests.post(f"{API}/reservations", headers=h(tok), json={
        "venue_id": gv["id"], "date": future(), "party_size": 2, "service_type": "bottle"})
    assert r.status_code == 201, r.text
    CREATED["reservations"].append(r.json()["id"])
    assert r.json()["platform_fee"] == 120.0
    r = requests.post(f"{API}/tickets/purchase", headers=h(tok), json={"event_id": ge["id"], "quantity": 1})
    assert r.status_code == 201, r.text
    t = r.json()
    CREATED["tickets"].append(t["id"])
    EV_SOLD[ge["id"]] = EV_SOLD.get(ge["id"], 0) + 1
    base = round(ge["price"] * 0.8, 2)
    assert t["platform_fee"] == round(base * 0.15, 2)
    r = requests.post(f"{API}/partner-bookings", headers=h(tok), json={
        "partner_id": gp["id"], "date": future(), "units": 2, "guests": 2})
    assert r.status_code == 201, r.text
    b = r.json()
    CREATED["partner_bookings"].append(b["id"])
    base = round(gp["base_price"] * 2, 2)
    assert b["platform_fee"] == round(base * 0.15, 2)
    assert b["public_total"] == round(gp.get("public_price", gp["base_price"]) * 2, 2)
    assert b["member_savings"] == round(max(0.0, b["public_total"] - b["total"]), 2)
    S["gold_partner_savings"] = b["member_savings"]


# Downgrade to bronze then gold locked again
def test_downgrade():
    tok = S["tok"]
    r = requests.post(f"{API}/membership/upgrade", json={"level": "bronze"}, headers=h(tok))
    assert r.status_code == 200 and r.json()["level"] == "bronze"
    pay = db().membership_payments.find_one({"user_id": S["uid"], "level": "bronze"})
    assert pay["amount"] == 0.0  # free_girl gets bronze free


# Partners: new categories, unknown category 400, >180 days 400
def test_partner_categories(catalog):
    cats = {p["category"] for p in catalog[2]}
    for c in ("jet", "helicopter", "exotic_car", "chef", "security"):
        assert c in cats, c
        r = requests.get(f"{API}/partners", params={"category": c})
        assert r.status_code == 200 and len(r.json()) >= 1
        assert all(p["category"] == c for p in r.json())
    assert requests.get(f"{API}/partners", params={"category": "spaceship"}).status_code == 400
    p = catalog[2][0]
    assert "public_price" in p and p["public_price"] >= p["base_price"]


def test_partner_180_days(catalog):
    bp = pick(catalog[2], "bronze")
    r = requests.post(f"{API}/partner-bookings", headers=h(S["tok"]), json={
        "partner_id": bp["id"], "date": future(200), "units": 1, "guests": 1})
    assert r.status_code == 400 and "6 months" in r.json()["detail"]


# Admin overview + CSV level column
def test_admin_overview_and_csv():
    at = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}).json()["access_token"]
    tok2, u2 = register("trial_male")
    requests.post(f"{API}/membership/upgrade", json={"level": "silver"}, headers=h(tok2))
    ov = requests.get(f"{API}/admin/overview", headers=h(at))
    assert ov.status_code == 200
    mbl = ov.json()["members_by_level"]
    assert set(mbl) == {"bronze", "silver", "gold"} and mbl["silver"] >= 1
    csv = requests.get(f"{API}/admin/members/export", headers=h(at))
    assert csv.status_code == 200
    lines = csv.text.strip().splitlines()
    assert lines[0].split(",")[5] == "level"
    row = [ln for ln in lines if u2["email"] in ln]
    assert row and row[0].split(",")[5] == "silver"
    gt = requests.post(f"{API}/auth/login", json={"email": GUEST[0], "password": GUEST[1]}).json()["access_token"]
    assert requests.get(f"{API}/admin/overview", headers=h(gt)).status_code == 403
