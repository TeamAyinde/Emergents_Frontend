"""Iteration 15: email preferences, post-event feedback (+50 points), feedback/reminder/win-back emails honour prefs.
In-process email tests monkeypatch send_email (no real mail). Guest prefs/points are restored on teardown."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from conftest import run

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
GUEST = ("guest@nocturne.app", "GuestPass123!")
C = {"users": [], "tickets": [], "origin_set": False}
NOW = datetime.now(timezone.utc)


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(name="TEST_ Iter15 user"):
    email = f"test_{uuid.uuid4().hex[:8]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123!", "role": "guest",
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    return d["access_token"], d["user"]


def mk_ticket(uid, hours_from_now, **extra):
    tid = f"TEST_{uuid.uuid4()}"
    DB.tickets.insert_one({"id": tid, "event_id": "TEST_event", "event_title": "TEST_ Night", "venue_name": "TEST_ Venue",
                           "event_date": NOW + timedelta(hours=hours_from_now), "user_id": uid, "quantity": 1,
                           "total_paid": 0.0, "checked_in": False, "created_at": NOW, **extra})
    C["tickets"].append(tid)
    return tid


@pytest.fixture(scope="module")
def guest():
    tok = login(*GUEST)
    me = DB.users.find_one({"email": GUEST[0]}, {"_id": 0})
    return tok, me


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    base = DB.users.find_one({"email": GUEST[0]}, {"_id": 0, "id": 1, "points": 1, "email_prefs": 1,
                                                  "marketing_opt_in": 1, "marketing_opt_in_at": 1})
    had_origin = DB.settings.find_one({"_id": "public_origin"})
    yield
    DB.users.update_one({"id": base["id"]}, {"$set": {k: base.get(k) for k in
                                                     ("points", "email_prefs", "marketing_opt_in", "marketing_opt_in_at")}})
    DB.feedback.delete_many({"ticket_id": {"$in": C["tickets"]}})
    DB.points_ledger.delete_many({"user_id": base["id"], "reason": "Feedback · TEST_ Night"})
    DB.tickets.delete_many({"id": {"$in": C["tickets"]}})
    if C["origin_set"] and not had_origin:
        DB.settings.delete_one({"_id": "public_origin"})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


# ---------- Email preferences API ----------

def test_prefs_requires_auth():
    assert requests.get(f"{API}/me/email-prefs").status_code == 401


def test_prefs_get_shape(guest):
    r = requests.get(f"{API}/me/email-prefs", headers=h(guest[0]))
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"reminders", "receipts", "feedback", "offers", "newsletter"}
    assert all(isinstance(v, bool) for v in d.values())
    assert d["newsletter"] == bool(guest[1].get("marketing_opt_in"))


def test_prefs_put_persists_and_newsletter_maps(guest):
    tok = guest[0]
    body = {"reminders": False, "receipts": True, "feedback": False, "offers": True, "newsletter": False}
    r = requests.put(f"{API}/me/email-prefs", json=body, headers=h(tok))
    assert r.status_code == 200 and r.json() == body
    assert requests.get(f"{API}/me/email-prefs", headers=h(tok)).json() == body
    u = DB.users.find_one({"email": GUEST[0]})
    assert u["marketing_opt_in"] is False and u["email_prefs"]["reminders"] is False
    body2 = {**body, "newsletter": True, "reminders": True, "feedback": True}
    assert requests.put(f"{API}/me/email-prefs", json=body2, headers=h(tok)).json() == body2
    assert DB.users.find_one({"email": GUEST[0]})["marketing_opt_in"] is True


def test_prefs_partial_body_defaults(guest):
    """A partial PUT only changes the keys sent; the rest (incl. newsletter) are kept."""
    tok = guest[0]
    before = requests.get(f"{API}/me/email-prefs", headers=h(tok)).json()
    r = requests.put(f"{API}/me/email-prefs", json={"offers": False}, headers=h(tok))
    assert r.status_code == 200
    d = requests.get(f"{API}/me/email-prefs", headers=h(tok)).json()
    assert d["offers"] is False
    assert all(d[k] == before[k] for k in ("reminders", "receipts", "feedback", "newsletter"))


# ---------- Feedback API ----------

def test_feedback_rules(guest):
    tok, me = guest
    past = mk_ticket(me["id"], -12)
    future = mk_ticket(me["id"], 48)
    other_tok, other = register()
    others = mk_ticket(other["id"], -12)

    info = requests.get(f"{API}/feedback/{past}", headers=h(tok))
    assert info.status_code == 200, info.text
    i = info.json()
    assert i["event_title"] == "TEST_ Night" and i["submitted"] is False and i["points"] == 50

    for bad in (0, 6, "x"):
        assert requests.post(f"{API}/feedback/{past}", json={"rating": bad}, headers=h(tok)).status_code == 422
    assert requests.post(f"{API}/feedback/{past}", json={"rating": 5, "comment": "x" * 501}, headers=h(tok)).status_code == 422
    assert requests.post(f"{API}/feedback/{future}", json={"rating": 5}, headers=h(tok)).status_code == 400
    assert requests.post(f"{API}/feedback/{others}", json={"rating": 5}, headers=h(tok)).status_code == 404
    assert requests.get(f"{API}/feedback/{others}", headers=h(tok)).status_code == 404
    assert requests.post(f"{API}/feedback/{past}", json={"rating": 5}).status_code == 401

    p0 = DB.users.find_one({"id": me["id"]})["points"]
    r = requests.post(f"{API}/feedback/{past}", json={"rating": 4, "comment": "  TEST_ great  "}, headers=h(tok))
    assert r.status_code == 200 and r.json() == {"points": 50}
    assert DB.users.find_one({"id": me["id"]})["points"] == p0 + 50
    fb = DB.feedback.find_one({"ticket_id": past})
    assert fb["rating"] == 4 and fb["comment"] == "TEST_ great" and fb["user_id"] == me["id"]
    assert DB.points_ledger.count_documents({"user_id": me["id"], "reason": "Feedback · TEST_ Night"}) >= 1
    r2 = requests.post(f"{API}/feedback/{past}", json={"rating": 1}, headers=h(tok))
    assert r2.status_code == 409
    assert DB.users.find_one({"id": me["id"]})["points"] == p0 + 50
    i2 = requests.get(f"{API}/feedback/{past}", headers=h(tok)).json()
    assert i2["submitted"] is True and i2["rating"] == 4


def test_feedback_rewards_reflects_points(guest):
    tok, me = guest
    r = requests.get(f"{API}/auth/me", headers=h(tok))
    assert r.status_code == 200
    assert r.json().get("points") == DB.users.find_one({"id": me["id"]})["points"]


# ---------- In-process: background emails honour prefs ----------

def _capture(module):
    sent = []

    async def fake(*, to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return "fake"
    module.send_email = fake
    return sent


def test_feedback_requests_once_and_respect_pref():
    import server  # noqa: F401
    from routes import engage
    _, ua = register("TEST_ Fb On")
    _, ub = register("TEST_ Fb Off")
    DB.users.update_one({"id": ub["id"]}, {"$set": {"email_prefs": {"reminders": True, "receipts": True, "feedback": False, "offers": True}}})
    ta = mk_ticket(ua["id"], -12)
    tb = mk_ticket(ub["id"], -12)
    t_old = mk_ticket(ua["id"], -50)
    t_recent = mk_ticket(ua["id"], -2)
    orig = engage.send_email
    sent = _capture(engage)
    try:
        if not DB.settings.find_one({"_id": "public_origin"}):
            # no origin -> nothing sent, nothing claimed
            assert run(engage.send_feedback_requests()) == 0
            assert not DB.tickets.find_one({"id": ta}).get("feedback_sent")
            DB.settings.insert_one({"_id": "public_origin", "url": BASE_URL})
            C["origin_set"] = True
        origin = DB.settings.find_one({"_id": "public_origin"})["url"]
        n = run(engage.send_feedback_requests())
        mine = [s for s in sent if ta in s["html"] or tb in s["html"]]
        assert n >= 1 and len(mine) == 1, sent
        assert f"{origin}/feedback/{ta}" in mine[0]["html"] and "50 bonus" in mine[0]["html"]
        assert DB.tickets.find_one({"id": tb})["feedback_sent"] is True  # claimed but skipped
        assert not DB.tickets.find_one({"id": t_old}).get("feedback_sent")
        assert not DB.tickets.find_one({"id": t_recent}).get("feedback_sent")
        sent.clear()
        run(engage.send_feedback_requests())
        assert not [s for s in sent if ta in s["html"]]
    finally:
        engage.send_email = orig


def test_reminders_skip_pref_off():
    import server  # noqa: F401
    from routes import notify
    _, ua = register("TEST_ Rem On")
    _, ub = register("TEST_ Rem Off")
    DB.users.update_one({"id": ub["id"]}, {"$set": {"email_prefs": {"reminders": False, "receipts": True, "feedback": True, "offers": True}}})
    ta = mk_ticket(ua["id"], 24)
    tb = mk_ticket(ub["id"], 24)
    orig = notify.send_email
    sent = _capture(notify)
    try:
        run(notify.send_due_reminders())
        to = [s["to"] for s in sent]
        assert ua["email"] in to and ub["email"] not in to, to
        assert DB.tickets.find_one({"id": tb})["reminder_sent"] is True
        sent.clear()
        run(notify.send_due_reminders())
        assert ua["email"] not in [s["to"] for s in sent]
    finally:
        notify.send_email = orig


def test_receipt_skips_pref_off():
    import server  # noqa: F401
    from routes import notify
    _, ub = register("TEST_ Rcpt Off")
    sid = f"sub_TEST_{uuid.uuid4().hex[:8]}"
    DB.users.update_one({"id": ub["id"]}, {"$set": {"stripe_subscription_id": sid, "subscription_level": "silver",
                                                     "email_prefs": {"reminders": True, "receipts": False, "feedback": True, "offers": True}}})
    orig = notify.send_email
    sent = _capture(notify)
    try:
        inv = {"id": f"in_TEST_{uuid.uuid4().hex[:8]}", "billing_reason": "subscription_cycle", "amount_paid": 1000, "subscription": sid}
        run(notify.renewal_receipt(inv))
        assert not sent
        assert not DB.receipts.find_one({"_id": inv["id"]})
        DB.users.update_one({"id": ub["id"]}, {"$set": {"email_prefs.receipts": True}})
        run(notify.renewal_receipt(inv))
        assert len(sent) == 1 and sent[0]["to"] == ub["email"]
    finally:
        notify.send_email = orig
        DB.receipts.delete_one({"_id": inv["id"]})


def test_winback_once_and_respects_offers():
    import server  # noqa: F401
    from routes import engage
    _, ua = register("TEST_ Wb On")
    _, ub = register("TEST_ Wb Off")
    DB.users.update_one({"id": ub["id"]}, {"$set": {"email_prefs": {"reminders": True, "receipts": True, "feedback": True, "offers": False}}})
    DB.users.update_one({"id": ua["id"]}, {"$set": {"subscription_level": "gold"}})
    orig = engage.send_email
    sent = _capture(engage)
    try:
        a = DB.users.find_one({"id": ua["id"]}, {"_id": 0})
        run(engage.on_renewal_cancelled(a))
        assert len(sent) == 1 and sent[0]["to"] == ua["email"] and "30%" in sent[0]["subject"]
        assert DB.users.find_one({"id": ua["id"]})["winback_offered"] is True
        run(engage.on_renewal_cancelled(DB.users.find_one({"id": ua["id"]}, {"_id": 0})))
        run(engage.on_renewal_cancelled(a))  # stale doc without flag -> atomic guard
        assert len(sent) == 1
        run(engage.on_renewal_cancelled(DB.users.find_one({"id": ub["id"]}, {"_id": 0})))
        assert len(sent) == 1
        assert not DB.users.find_one({"id": ub["id"]}).get("winback_offered")
    finally:
        engage.send_email = orig


def test_apply_winback_guards():
    import server  # noqa: F401
    from routes import engage
    _, u = register("TEST_ Wb Apply")
    doc = DB.users.find_one({"id": u["id"]}, {"_id": 0})
    assert run(engage.apply_winback(doc, "sub_TEST_x")) is False  # never offered
    DB.users.update_one({"id": u["id"]}, {"$set": {"winback_offered": True, "winback_used": True}})
    assert run(engage.apply_winback(DB.users.find_one({"id": u["id"]}, {"_id": 0}), "sub_TEST_x")) is False
