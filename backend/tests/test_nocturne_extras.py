"""Nocturne iteration 3: registration consent fields, preferences, luxe partners & bookings, journal,
admin dashboard (overview/members/CSV export/journal CRUD/AI draft/booking status), withdrawal fees.
All created data tracked by id and removed at module teardown."""
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

GUEST = ("guest@nocturne.app", "GuestPass123!")
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")

CREATED = {"users": [], "partner_bookings": [], "articles": [], "withdrawals": []}
WALLET = {"promoter_id": None, "delta": 0.0}
STATE = {}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {creds[0]}: {r.status_code}")
    return r.json()


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    yield
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # partner-booking confirmation awards points to the seeded guest: undo exactly what this run added
    g = db.users.find_one({"email": GUEST[0]}, {"id": 1})
    rows = list(db.points_ledger.find({"user_id": g["id"], "reason": {"$regex": "^Luxe"}, "created_at": {"$gte": start}}))
    if rows:
        db.points_ledger.delete_many({"id": {"$in": [r["id"] for r in rows]}})
        db.users.update_one({"id": g["id"]}, {"$inc": {"points": -sum(r["points"] for r in rows)}})
    for uid in CREATED["users"]:
        db.users.delete_one({"id": uid})
    for bid in CREATED["partner_bookings"]:
        db.partner_bookings.delete_one({"id": bid})
    for aid in CREATED["articles"]:
        db.articles.delete_one({"id": aid})
    for wid in CREATED["withdrawals"]:
        db.withdrawals.delete_one({"id": wid})
    if WALLET["promoter_id"] and WALLET["delta"]:
        db.users.update_one({"id": WALLET["promoter_id"]}, {"$inc": {"wallet_balance": WALLET["delta"]}})


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN)["access_token"]


@pytest.fixture(scope="module")
def guest():
    return login(GUEST)["access_token"]


# --- Registration consent fields
class TestRegister:
    def test_register_default_optin_with_phone_city(self):
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "TestPass123!", "full_name": "TEST_Lux User",
            "phone": "+1 555 0100", "city": "Los Angeles"})
        assert r.status_code == 201, r.text
        u = r.json()["user"]
        CREATED["users"].append(u["id"])
        assert u["marketing_opt_in"] is True
        assert u["phone"] == "+1 555 0100" and u["city"] == "Los Angeles"
        STATE["new_user"] = (email, r.json()["access_token"])

    def test_register_optout(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!",
            "full_name": "TEST_Optout", "marketing_opt_in": False})
        assert r.status_code == 201
        CREATED["users"].append(r.json()["user"]["id"])
        assert r.json()["user"]["marketing_opt_in"] is False
        STATE["optout_email"] = r.json()["user"]["email"]

    def test_prefs_toggle(self):
        email, tok = STATE["new_user"]
        r = requests.patch(f"{API}/me/preferences", json={"marketing_opt_in": False}, headers=h(tok))
        assert r.status_code == 200 and r.json()["marketing_opt_in"] is False
        me = requests.get(f"{API}/auth/me", headers=h(tok))
        if me.status_code == 200:
            assert me.json()["marketing_opt_in"] is False
        r = requests.patch(f"{API}/me/preferences", json={"marketing_opt_in": True}, headers=h(tok))
        assert r.json()["marketing_opt_in"] is True

    def test_prefs_unauth(self):
        assert requests.patch(f"{API}/me/preferences", json={"marketing_opt_in": True}).status_code in (401, 403)


# --- Partners & luxe bookings
class TestPartners:
    def test_list_and_filter(self):
        r = requests.get(f"{API}/partners")
        assert r.status_code == 200 and len(r.json()) > 0
        cats = {p["category"] for p in r.json()}
        for c in ["hotel", "black_car", "limo", "mansion", "yacht"]:
            assert c in cats, f"missing category {c}"
            rc = requests.get(f"{API}/partners", params={"category": c})
            assert rc.status_code == 200 and all(p["category"] == c for p in rc.json()) and rc.json()
        STATE["partner"] = next(p for p in r.json() if p.get("min_level", "bronze") == "bronze")  # bronze guest

    def test_get_partner_and_404(self):
        p = STATE["partner"]
        r = requests.get(f"{API}/partners/{p['id']}")
        assert r.status_code == 200 and r.json()["name"] == p["name"]
        assert requests.get(f"{API}/partners/nope-xyz").status_code == 404

    def test_booking_fee_and_mine(self, guest):
        p = STATE["partner"]
        r = requests.post(f"{API}/partner-bookings", headers=h(guest), json={
            "partner_id": p["id"], "date": future(5), "units": 3, "guests": 4, "notes": "TEST_ booking"})
        assert r.status_code == 201, r.text
        b = r.json()
        CREATED["partner_bookings"].append(b["id"])
        assert b["status"] == "requested"
        assert b["base_price"] == round(p["base_price"] * 3, 2)
        assert b["platform_fee"] == round(b["base_price"] * 0.25, 2)  # bronze tier fee
        assert b["total"] == round(b["base_price"] + b["platform_fee"], 2)
        mine = requests.get(f"{API}/partner-bookings/mine", headers=h(guest)).json()
        assert any(x["id"] == b["id"] for x in mine)
        STATE["booking"] = b["id"]

    @pytest.mark.parametrize("payload,code", [
        ({"units": 0, "guests": 2, "days": 3}, 422), ({"units": 15, "guests": 2, "days": 3}, 422),
        ({"units": 1, "guests": 0, "days": 3}, 422), ({"units": 1, "guests": 101, "days": 3}, 422),
        ({"units": 1, "guests": 2, "days": -2}, 400)])
    def test_booking_validation(self, guest, payload, code):
        r = requests.post(f"{API}/partner-bookings", headers=h(guest), json={
            "partner_id": STATE["partner"]["id"], "date": future(payload["days"]),
            "units": payload["units"], "guests": payload["guests"]})
        if r.status_code == 201:
            CREATED["partner_bookings"].append(r.json()["id"])
        assert r.status_code == code

    def test_booking_unauth(self):
        r = requests.post(f"{API}/partner-bookings", json={"partner_id": "x", "date": future(), "units": 1, "guests": 1})
        assert r.status_code in (401, 403)


# --- Journal + admin journal + AI draft
class TestJournal:
    def test_public_list_published_only(self):
        r = requests.get(f"{API}/journal")
        assert r.status_code == 200 and all(a["published"] for a in r.json())

    def test_admin_create_draft_and_publish(self, admin, guest):
        base = {"title": "TEST_ Article", "category": "luxury", "cover_image": "https://images.unsplash.com/photo-1",
                "summary": "s", "body": "Body text", "published": False}
        r = requests.post(f"{API}/admin/journal", json=base, headers=h(admin))
        assert r.status_code == 201, r.text
        aid = r.json()["id"]
        CREATED["articles"].append(aid)
        assert all(a["id"] != aid for a in requests.get(f"{API}/journal").json())
        assert requests.get(f"{API}/journal/{aid}", headers=h(guest)).status_code == 404
        assert requests.get(f"{API}/journal/{aid}", headers=h(admin)).status_code == 200
        assert any(a["id"] == aid for a in requests.get(f"{API}/admin/journal", headers=h(admin)).json())
        r = requests.put(f"{API}/admin/journal/{aid}", json={**base, "published": True, "title": "TEST_ Pub"}, headers=h(admin))
        assert r.status_code == 200 and r.json()["published"] and r.json()["title"] == "TEST_ Pub"
        assert any(a["id"] == aid for a in requests.get(f"{API}/journal").json())
        g = requests.get(f"{API}/journal/{aid}", headers=h(guest))
        assert g.status_code == 200 and g.json()["title"] == "TEST_ Pub"
        assert requests.get(f"{API}/journal/{aid}").status_code in (401, 403)

    def test_admin_article_validation(self, admin):
        base = {"title": "TEST_ x", "category": "food", "cover_image": "https://x", "body": "b"}
        assert requests.post(f"{API}/admin/journal", json=base, headers=h(admin)).status_code == 400
        assert requests.post(f"{API}/admin/journal", json={**base, "category": "travel", "cover_image": "http://x"},
                             headers=h(admin)).status_code == 400
        assert requests.put(f"{API}/admin/journal/nope", json={**base, "category": "travel"},
                            headers=h(admin)).status_code == 404

    def test_ai_draft_stream(self, admin):
        r = requests.post(f"{API}/admin/journal/draft", headers=h(admin), timeout=120,
                          json={"topic": "Sunset yacht parties in Malibu", "category": "luxury"})
        assert r.status_code == 200, r.text
        text = r.text.strip()
        print("DRAFT HEAD:", text[:300])
        lines = [l for l in text.splitlines() if l.strip()]
        assert len(lines) >= 3 and len(text) > 500, f"draft too short: {text[:300]}"
        assert not lines[0].startswith("#")

    def test_ai_draft_bad_category(self, admin):
        r = requests.post(f"{API}/admin/journal/draft", headers=h(admin), json={"topic": "abcd", "category": "food"})
        assert r.status_code == 400


# --- Admin RBAC, overview, members, export, booking status
class TestAdmin:
    @pytest.mark.parametrize("method,path", [
        ("get", "/admin/overview"), ("get", "/admin/members"), ("get", "/admin/members/export"),
        ("get", "/admin/journal"), ("get", "/admin/partner-bookings"), ("post", "/admin/journal/draft"),
        ("post", "/admin/journal"), ("patch", "/admin/partner-bookings/x")])
    def test_non_admin_403(self, guest, method, path):
        body = {"topic": "abcd", "category": "luxury"} if "draft" in path else (
            {"status": "confirmed"} if "partner" in path else {"title": "t", "category": "luxury", "cover_image": "https://x", "body": "b"})
        r = getattr(requests, method)(f"{API}{path}", headers=h(guest), json=body if method != "get" else None)
        assert r.status_code == 403

    def test_overview_shape(self, admin):
        r = requests.get(f"{API}/admin/overview", headers=h(admin))
        assert r.status_code == 200
        d = r.json()
        for k in ["ticket_fees", "reservation_fees", "partner_fees", "withdrawal_fees", "membership_mrr_estimate"]:
            assert isinstance(d["revenue"][k], (int, float))
        rv = d["revenue"]
        assert d["revenue_total"] == round(rv["ticket_fees"] + rv["reservation_fees"] + rv["partner_fees"] + rv["withdrawal_fees"], 2)
        STATE["overview"] = d

    def test_members_and_export(self, admin):
        r = requests.get(f"{API}/admin/members", headers=h(admin))
        assert r.status_code == 200 and "password_hash" not in r.json()[0]
        opt = requests.get(f"{API}/admin/members", params={"opted_in": "true"}, headers=h(admin)).json()
        assert all(m["marketing_opt_in"] for m in opt)
        e = requests.get(f"{API}/admin/members/export", headers=h(admin))
        assert e.status_code == 200 and "text/csv" in e.headers["content-type"]
        assert e.text.splitlines()[0].startswith("full_name,email,phone,city")
        assert STATE["new_user"][0] in e.text
        assert STATE["optout_email"] not in e.text
        assert len(e.text.strip().splitlines()) - 1 == len(opt)

    def test_booking_confirm_then_400_and_partner_fees(self, admin):
        bid = STATE["booking"]
        before = requests.get(f"{API}/admin/overview", headers=h(admin)).json()
        assert any(b["id"] == bid for b in requests.get(f"{API}/admin/partner-bookings", headers=h(admin)).json())
        assert requests.patch(f"{API}/admin/partner-bookings/{bid}", json={"status": "bogus"}, headers=h(admin)).status_code == 400
        r = requests.patch(f"{API}/admin/partner-bookings/{bid}", json={"status": "confirmed"}, headers=h(admin))
        assert r.status_code == 200 and r.json()["status"] == "confirmed"
        assert requests.patch(f"{API}/admin/partner-bookings/{bid}", json={"status": "declined"}, headers=h(admin)).status_code == 400
        after = requests.get(f"{API}/admin/overview", headers=h(admin)).json()
        assert round(after["revenue"]["partner_fees"] - before["revenue"]["partner_fees"], 2) == r.json()["platform_fee"]
        assert after["pending_partner_requests"] == before["pending_partner_requests"] - 1

    def test_withdrawal_recorded_in_overview(self, admin):
        # use a TEST_ promoter with a test-funded wallet so seeded promoter is untouched
        rr = requests.post(f"{API}/auth/register", json={
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!",
            "full_name": "TEST_Promo", "role": "promoter"})
        if rr.status_code != 201:
            pytest.skip(f"promoter register failed {rr.status_code}")
        tok, user = rr.json()["access_token"], rr.json()["user"]
        CREATED["users"].append(user["id"])
        MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].users.update_one(
            {"id": user["id"]}, {"$set": {"wallet_balance": 50.0}})
        before = requests.get(f"{API}/admin/overview", headers=h(admin)).json()["revenue"]["withdrawal_fees"]
        r = requests.post(f"{API}/promoter/withdraw", json={"amount": 10}, headers=h(tok))
        assert r.status_code == 200, r.text
        WALLET["promoter_id"], WALLET["delta"] = user["id"], 10.0
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        w = db.withdrawals.find_one({"user_id": user["id"]}, sort=[("created_at", -1)])
        CREATED["withdrawals"].append(w["id"])
        after = requests.get(f"{API}/admin/overview", headers=h(admin)).json()["revenue"]["withdrawal_fees"]
        assert round(after - before, 2) == r.json()["fee"]
