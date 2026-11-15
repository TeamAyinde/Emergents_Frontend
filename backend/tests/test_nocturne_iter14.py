"""Iteration 14: gift resend/change recipient, ticket QR image, booking confirmation emails, winner email.
Only delivered@resend.dev is ever used as a real recipient (and only one TEST_ user holds it at a time)."""
import asyncio
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
sys.path.insert(0, "/app/backend")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SAFE_TO = "delivered@resend.dev"
C = {"users": [], "sessions": set(), "tickets": [], "tables": [], "res": [], "txs": [], "award": None}


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def register(name="TEST_ Iter14 guest", role="guest"):
    email = f"test_{uuid.uuid4().hex[:8]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123!", "role": role,
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


def paid_gift(tok, **kw):
    simulate_paid(checkout(tok, kind="gift", level="gold", **kw))
    return requests.get(f"{API}/gifts/mine", headers=h(tok)).json()[0]


class safe_email:
    """Temporarily gives a TEST_ user the safe address (users.email is unique)."""
    def __init__(self, uid):
        self.uid = uid

    def __enter__(self):
        self.old = DB.users.find_one({"id": self.uid})["email"]
        assert self.old.startswith("test_")
        DB.users.update_one({"id": self.uid}, {"$set": {"email": SAFE_TO}})

    def __exit__(self, *a):
        DB.users.update_one({"id": self.uid}, {"$set": {"email": self.old}})


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in C["sessions"]:
        try:
            requests.post(f"{API}/payments/cancel/{sid}", timeout=10)
        except Exception:
            pass
    DB.payment_transactions.delete_many({"session_id": {"$in": list(C["sessions"])}})
    DB.payment_transactions.delete_many({"id": {"$in": C["txs"]}})
    # issued via checkout (not inserted by the test): undo tickets_sold and the venue share
    for t in DB.tickets.find({"user_id": {"$in": C["users"]}, "id": {"$nin": list(C["tickets"])}}, {"_id": 0}):
        DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t.get("quantity", 1)}})
    DB.venue_payables.delete_many({"record_id": {"$in": [t["id"] for t in DB.tickets.find({"user_id": {"$in": C["users"]}}, {"id": 1})]}})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    DB.tickets.delete_many({"user_id": {"$in": C["users"]}})
    DB.table_bookings.delete_many({"id": {"$in": C["tables"]}})
    DB.reservations.delete_many({"id": {"$in": C["res"]}})
    DB.gifts.delete_many({"buyer_id": {"$in": C["users"]}})
    if C["award"]:
        DB.leaderboard_awards.delete_one({"_id": C["award"], "user_id": {"$in": C["users"]}})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


# ---------- Gift resend / change recipient (live server) ----------

def test_gift_resend_flow_and_limits():
    tok, _ = register()
    g = paid_gift(tok)  # no recipient yet -> email_sends 0
    assert g["recipient_email"] is None
    # invalid email -> 422
    assert requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": "nope"}, headers=h(tok)).status_code == 422
    # no email at all -> 400
    r = requests.post(f"{API}/gifts/{g['id']}/email", json={}, headers=h(tok))
    assert r.status_code == 400, r.text
    # other user -> 404
    otok, _ = register()
    assert requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": SAFE_TO}, headers=h(otok)).status_code == 404
    # unauthenticated -> 401/403
    assert requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": SAFE_TO}).status_code in (401, 403)
    # real send #1 (uppercase -> stored lowercase)
    r = requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": "Delivered@Resend.dev"}, headers=h(tok), timeout=60)
    assert r.status_code == 200, r.text
    assert r.json() == {"email_status": "sent", "recipient_email": SAFE_TO}
    mine = requests.get(f"{API}/gifts/mine", headers=h(tok)).json()[0]
    assert mine["recipient_email"] == SAFE_TO and mine["email_status"] == "sent"
    assert DB.gifts.find_one({"id": g["id"]})["email_sends"] == 1
    # jump to 2 sends, real resend #3 with empty body re-uses stored recipient
    DB.gifts.update_one({"id": g["id"]}, {"$set": {"email_sends": 2}})
    r = requests.post(f"{API}/gifts/{g['id']}/email", json={}, headers=h(tok), timeout=60)
    assert r.status_code == 200, r.text
    assert DB.gifts.find_one({"id": g["id"]})["email_sends"] == 3
    # 4th -> 429, counter unchanged
    r = requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": SAFE_TO}, headers=h(tok))
    assert r.status_code == 429, r.text
    assert DB.gifts.find_one({"id": g["id"]})["email_sends"] == 3


def test_gift_bought_with_email_counts_first_send():
    tok, _ = register()
    sid = checkout(tok, kind="gift", level="silver", recipient_email=SAFE_TO)
    import server  # noqa: F401
    from services import emailer
    orig = emailer.send_email

    async def fake(**_):
        return "x"
    emailer.send_email = fake  # the in-process background send must not hit the proxy
    try:
        simulate_paid(sid)
        run(asyncio.sleep(0.2))
    finally:
        emailer.send_email = orig
    g = DB.gifts.find_one({"buyer_id": DB.payment_transactions.find_one({"session_id": sid})["user_id"]})
    assert g["email_sends"] == 1
    DB.gifts.update_one({"id": g["id"]}, {"$set": {"email_sends": 3}})
    assert requests.post(f"{API}/gifts/{g['id']}/email", json={}, headers=h(tok)).status_code == 429


def test_gift_resend_redeemed_400():
    btok, _ = register()
    g = paid_gift(btok)
    rtok, _ = register()
    assert requests.post(f"{API}/gifts/redeem", json={"code": g["code"]}, headers=h(rtok)).status_code == 200
    r = requests.post(f"{API}/gifts/{g['id']}/email", json={"recipient_email": SAFE_TO}, headers=h(btok))
    assert r.status_code == 400 and "redeemed" in r.json()["detail"]


def test_gift_resend_send_failure_503(monkeypatch):
    import server  # noqa: F401
    from services import emailer
    from routes import notify
    from fastapi import HTTPException
    tok, u = register()
    g = paid_gift(tok)

    async def boom(**_):
        raise RuntimeError("Failed to send email")
    monkeypatch.setattr(emailer, "send_email", boom)
    with pytest.raises(HTTPException) as e:
        run(notify.resend_gift(g["id"], notify.GiftEmailIn(recipient_email=SAFE_TO), DB.users.find_one({"id": u["id"]})))
    assert e.value.status_code == 503
    doc = DB.gifts.find_one({"id": g["id"]})
    assert doc["email_status"].startswith("failed:") and doc["email_sends"] == 0  # failed sends do not count toward the limit


# ---------- Ticket QR + booking confirmation emails ----------

def _open_paid_event():
    evs = [e for e in requests.get(f"{API}/events").json()
           if e.get("min_level", "bronze") == "bronze" and not e.get("approval_required") and e.get("price", 0) > 0]
    if not evs:
        pytest.skip("no open paid event")
    return evs[0]


def test_ticket_qr_png_and_booking_email_real_send(monkeypatch):
    import server  # noqa: F401
    from routes import notify
    tok, u = register(name="TEST_ Iter14 Ticket")
    ev = _open_paid_event()
    sid = checkout(tok, kind="ticket", event_id=ev["id"], quantity=2)
    real = notify.send_email
    captured = []

    async def skip(**kw):  # swallow the in-process background send from _complete
        return "x"
    monkeypatch.setattr(notify, "send_email", skip)
    tx = simulate_paid(sid)
    run(asyncio.sleep(0.2))
    assert tx["status"] == "paid" and tx["result_id"]
    tid = tx["result_id"]
    # public QR image
    r = requests.get(f"{API}/tickets/{tid}/qr.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert requests.get(f"{API}/tickets/TEST_{uuid.uuid4()}/qr.png").status_code == 404
    # booking email -> real send to the safe address
    DB.payment_transactions.update_one({"session_id": sid}, {"$unset": {"email_sent": ""}})

    async def cap(**kw):
        captured.append(kw)
        return await real(**kw)
    monkeypatch.setattr(notify, "send_email", cap)
    with safe_email(u["id"]):
        run(notify.booking_email(tx, tid))
    m = captured[-1]
    assert m["to"] == SAFE_TO and ev["title"] in m["subject"]
    assert f'src="{BASE_URL}/api/tickets/{tid}/qr.png"' in m["html"]
    assert tid[:8].upper() in m["html"] and "2 × ticket" in m["html"]
    assert DB.payment_transactions.find_one({"session_id": sid})["email_sent"] is True


def _seed_tx(uid, kind, origin, amount=50.0):
    txid = f"TEST_{uuid.uuid4()}"
    tx = {"id": txid, "user_id": uid, "kind": kind, "amount": amount, "origin": origin}
    DB.payment_transactions.insert_one({**tx, "session_id": f"TEST_{txid}", "fulfilled": True})
    C["txs"].append(txid)
    return tx


@pytest.fixture
def fake_send(monkeypatch):
    import server  # noqa: F401
    from services import emailer
    from routes import notify
    sent = []

    async def fake(*, to, subject, html):
        emailer._assert_safe_email(subject, html)
        sent.append({"to": to, "subject": subject, "html": html})
        return "x"
    monkeypatch.setattr(notify, "send_email", fake)
    return sent


def test_booking_email_ticket_escapes_and_http_origin_no_qr(fake_send):
    from routes import notify
    _, u = register(name="TEST_<i>Eve</i> X")
    tid = f"TEST_{uuid.uuid4()}"
    DB.tickets.insert_one({"id": tid, "event_title": 'TEST_ <script>alert(1)</script> & "Night"', "venue_name": "TEST_ <b>V</b>",
                           "event_date": datetime.now(timezone.utc), "quantity": 1, "user_id": u["id"]})
    C["tickets"].append(tid)
    tx = _seed_tx(u["id"], "ticket", "http://localhost:3000")
    run(notify.booking_email(tx, tid))
    html = fake_send[-1]["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html
    assert "&lt;i&gt;Eve&lt;/i&gt;" in html and "<b>V</b>" not in html
    assert "<img" not in html  # non-https origin -> no QR image (would fail G3)
    assert DB.payment_transactions.find_one({"id": tx["id"]})["email_sent"] is True


def test_booking_email_table_and_reservation(fake_send):
    from routes import notify
    _, u = register(name="TEST_ Tab Res")
    bid, rid = f"TEST_{uuid.uuid4()}", f"TEST_{uuid.uuid4()}"
    DB.table_bookings.insert_one({"id": bid, "table_id": "T7", "section": "VIP", "event_title": "TEST_ Ev", "venue_name": "TEST_ Club",
                                  "event_date": datetime.now(timezone.utc), "party_size": 4, "min_spend": 500, "user_id": u["id"]})
    DB.reservations.insert_one({"id": rid, "service_type": "dinner", "venue_name": "TEST_ Bistro",
                                "date": datetime.now(timezone.utc), "party_size": 2, "user_id": u["id"]})
    C["tables"].append(bid)
    C["res"].append(rid)
    t1 = _seed_tx(u["id"], "table", BASE_URL)
    run(notify.booking_email(t1, bid))
    m = fake_send[-1]
    assert m["subject"] == "Your table at TEST_ Club is confirmed"
    assert "Table T7 · VIP" in m["html"] and "Party of 4" in m["html"] and "$500" in m["html"] and bid[:8].upper() in m["html"]
    t2 = _seed_tx(u["id"], "reservation", BASE_URL, amount=0)
    run(notify.booking_email(t2, rid))
    m = fake_send[-1]
    assert m["subject"] == "Your reservation at TEST_ Bistro is confirmed"
    assert "Dinner · TEST_ Bistro" in m["html"] and "Paid:" not in m["html"]
    for t in (t1, t2):
        assert DB.payment_transactions.find_one({"id": t["id"]})["email_sent"] is True


# ---------- Winner announcement ----------

def test_winner_email_on_award(fake_send):
    from routes import growth
    from routes import notify
    last = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=1))
    month = last.strftime("%Y-%m")
    if DB.leaderboard_awards.find_one({"_id": month}):
        pytest.skip("last month already awarded (real data) — not touching it")
    _, p = register(name="TEST_ Winner Promo", role="promoter")
    tid = f"TEST_{uuid.uuid4()}"
    DB.tickets.insert_one({"id": tid, "event_id": "TEST_", "event_title": "TEST_", "event_date": last, "venue_name": "TEST_",
                           "user_id": f"TEST_{uuid.uuid4()}", "promoter_id": p["id"], "quantity": 500, "promoter_earning": 0.0,
                           "created_at": last.replace(hour=12)})
    C["tickets"].append(tid)
    with safe_email(p["id"]):
        award = run(growth._award_last_month())
        C["award"] = month
        run(asyncio.sleep(0.2))  # lets the background winner_email run (captured by fake_send)
        assert award["user_id"] == p["id"] and award["guests"] == 500 and award["bonus"] == 100.0
        run(notify.winner_email(award))
    m = fake_send[-1]
    assert m["to"] == SAFE_TO and "promoter bonus" in m["subject"]
    assert "500 guests" in m["html"] and "$100 bonus" in m["html"] and month in m["html"]
    assert len(fake_send) == 2  # background + direct
    assert DB.users.find_one({"id": p["id"]}).get("wallet_balance", 0) >= 100.0
    # idempotent: second call doesn't re-award or re-email
    again = run(growth._award_last_month())
    assert again["user_id"] == p["id"] and len(fake_send) == 2
