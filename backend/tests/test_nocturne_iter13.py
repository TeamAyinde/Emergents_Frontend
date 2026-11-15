"""Iteration 13: gift email delivery, gift status on /auth/me, promoter monthly rank.
Only delivered@resend.dev is ever used as a real recipient."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import run, simulate_paid

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
SAFE_TO = "delivered@resend.dev"
C = {"users": [], "sessions": set()}


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(name="TEST_ Iter13 guest"):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    assert r.status_code == 200, r.text
    C["sessions"].add(r.json()["session_id"])
    return r.json()["session_id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in C["sessions"]:
        try:
            requests.post(f"{API}/payments/cancel/{sid}", timeout=10)
        except Exception:
            pass
    DB.payment_transactions.delete_many({"session_id": {"$in": list(C["sessions"])}})
    DB.gifts.delete_many({"buyer_id": {"$in": C["users"]}})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


# ---------- Gift email delivery (real send, safe address only) ----------

def test_gift_with_email_is_sent():
    tok, _ = register()
    sid = checkout(tok, kind="gift", level="gold", recipient_email=SAFE_TO, note="TEST_ <b>enjoy</b> & have fun")
    tx = simulate_paid(sid)
    assert tx["status"] == "paid", tx
    import time
    sys.path.insert(0, "/app/backend")
    from routes import growth
    # in-process simulation ends its event loop before the background send runs; send it here like the server does
    first = requests.get(f"{API}/gifts/mine", headers=h(tok)).json()[0]
    if not first.get("email_status"):
        run(growth.email_gift(first["id"]))
    for _ in range(30):
        mine = requests.get(f"{API}/gifts/mine", headers=h(tok)).json()
        if mine and mine[0].get("email_status"):
            break
        time.sleep(1)
    assert len(mine) == 1
    assert mine[0]["recipient_email"] == SAFE_TO
    assert mine[0]["email_status"] == "sent", mine[0]


def test_gift_without_email_has_no_status():
    tok, _ = register()
    simulate_paid(checkout(tok, kind="gift", level="silver"))
    mine = requests.get(f"{API}/gifts/mine", headers=h(tok)).json()
    assert len(mine) == 1 and mine[0]["recipient_email"] is None and mine[0]["email_status"] is None


# ---------- Email template / failure path (in-process, send_email patched; no real email) ----------

def _seed_gift(buyer_id, note):
    gid = f"TEST_{uuid.uuid4()}"
    DB.gifts.insert_one({"id": gid, "code": "GIFT-T" + uuid.uuid4().hex[:5].upper(), "level": "gold", "days": 30,
                         "buyer_id": buyer_id, "recipient_email": SAFE_TO, "note": note, "redeemed": False,
                         "amount": 0, "created_at": datetime.now(timezone.utc)})
    return gid


def test_email_template_escapes_note_and_name(monkeypatch):
    import sys
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from services import emailer
    from routes import growth
    _, u = register(name='TEST_ <script>x</script> Bob')
    gid = _seed_gift(u["id"], '<a href="http://evil.example">click</a> "hi"')
    sent = {}

    async def fake_send(*, to, subject, html):
        emailer._assert_safe_email(subject, html)  # real G2/G3 checks still apply
        sent.update(to=to, subject=subject, html=html)
        return "x"

    monkeypatch.setattr(emailer, "send_email", fake_send)
    run(growth.email_gift(gid))
    assert sent["to"] == SAFE_TO
    assert "<script>" not in sent["html"] and "&lt;script&gt;" in sent["html"]
    assert '<a href="http://evil' not in sent["html"] and "&lt;a href=" in sent["html"]
    code = DB.gifts.find_one({"id": gid})["code"]
    assert code in sent["html"]
    assert DB.gifts.find_one({"id": gid})["email_status"] == "sent"


def test_email_failure_sets_failed_status(monkeypatch):
    import sys
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401
    from services import emailer
    from routes import growth
    _, u = register()
    gid = _seed_gift(u["id"], None)

    async def boom(**_):
        raise RuntimeError("Failed to send email")

    monkeypatch.setattr(emailer, "send_email", boom)
    run(growth.email_gift(gid))
    st = DB.gifts.find_one({"id": gid})["email_status"]
    assert st.startswith("failed:") and "Failed to send email" in st and len(st) <= 120


# ---------- Gift status on /auth/me ----------

def test_redeem_sets_gift_fields_on_me_and_expired_hidden():
    btok, _ = register()
    simulate_paid(checkout(btok, kind="gift", level="gold"))
    code = requests.get(f"{API}/gifts/mine", headers=h(btok)).json()[0]["code"]
    rtok, ru = register()
    before = requests.get(f"{API}/auth/me", headers=h(rtok)).json()
    assert before.get("gift_level") is None and before.get("gift_until") is None
    r = requests.post(f"{API}/gifts/redeem", json={"code": code}, headers=h(rtok))
    assert r.status_code == 200, r.text
    me = requests.get(f"{API}/auth/me", headers=h(rtok)).json()
    assert me["gift_level"] == "gold" and me["level"] == "gold"
    until = datetime.fromisoformat(me["gift_until"].replace("Z", "+00:00"))
    until = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
    assert timedelta(days=29) < until - datetime.now(timezone.utc) <= timedelta(days=30)
    # expire it -> not returned, level falls back
    DB.users.update_one({"id": ru["id"]}, {"$set": {"gift_until": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    me = requests.get(f"{API}/auth/me", headers=h(rtok)).json()
    assert me.get("gift_level") is None and me.get("gift_until") is None and me["level"] == "bronze"


# ---------- Promoter rank = monthly leaderboard position ----------

def test_promoter_rank_matches_monthly_board():
    tok = login(PROMOTER)
    me = requests.get(f"{API}/auth/me", headers=h(tok)).json()
    stats = requests.get(f"{API}/promoter/stats", headers=h(tok)).json()
    board = requests.get(f"{API}/promoter/leaderboard/monthly").json()["entries"]
    ids = [e["user_id"] for e in board]
    expected = ids.index(me["id"]) + 1 if me["id"] in ids else 0  # 0 = not ranked this month
    assert stats["rank"] == expected, (stats, ids)


def test_promoter_rank_with_seeded_board():
    """A TEST_ promoter with more guests this month ranks #1, promoter@ #2 in both stats and board."""
    tok = login(PROMOTER)
    me = requests.get(f"{API}/auth/me", headers=h(tok)).json()
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "promoter",
        "full_name": "TEST_ Iter13 promoter", "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    other = r.json()["user"]
    C["users"].append(other["id"])
    ev = requests.get(f"{API}/events").json()[-1]["id"]
    tids = []
    for pid, qty in ((me["id"], 1), (other["id"], 50)):
        tid = f"TEST_{uuid.uuid4()}"
        DB.tickets.insert_one({"id": tid, "event_id": ev, "event_title": "TEST_", "event_date": datetime.now(timezone.utc),
                               "venue_name": "TEST_", "user_id": f"TEST_{uuid.uuid4()}", "promoter_id": pid, "quantity": qty,
                               "total_paid": 0, "credit_used": 0, "platform_fee": 0, "promoter_earning": 0.0,
                               "venue_share": 0, "payment_session": None, "checked_in": False,
                               "created_at": datetime.now(timezone.utc)})
        tids.append(tid)
    try:
        ids = [e["user_id"] for e in requests.get(f"{API}/promoter/leaderboard/monthly").json()["entries"]]
        stats = requests.get(f"{API}/promoter/stats", headers=h(tok)).json()
        assert other["id"] in ids and me["id"] in ids
        assert stats["rank"] == ids.index(me["id"]) + 1
        assert ids.index(other["id"]) < ids.index(me["id"])
        ostats = requests.get(f"{API}/promoter/stats", headers=h(r.json()["access_token"])).json()
        assert ostats["rank"] == ids.index(other["id"]) + 1
    finally:
        DB.tickets.delete_many({"id": {"$in": tids}})
