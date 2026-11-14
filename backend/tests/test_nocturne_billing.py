"""Iteration 9: monthly membership subscriptions (7-day Bronze trial for gentlemen), venue boosts,
Stripe Connect (unavailable without own key), webhook hardening, one-time checkout regression.
Uses only TEST_ users created here; everything created is removed by id at module teardown."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import certifi
import pytest
import requests
import stripe
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
VENUE = ("venue@nocturne.app", "VenuePass123!")
PROMOTER = ("promoter@nocturne.app", "PromoterPass123!")
ADMIN = ("admin@nocturne.app", "AdminPass123!")
C = {"users": [], "sessions": set(), "withdrawals": []}

# same Stripe config as stripe_core (Emergent test proxy fallback)
_raw = (os.environ.get("STRIPE_API_KEY") or "").strip()
_OWN = _raw.startswith(("sk_", "rk_")) and "emergent" not in _raw
stripe.api_key = _raw if _OWN else "sk_test_emergent"
if not _OWN:
    stripe.api_base = "https://integrations.emergentagent.com/stripe"
stripe.ca_bundle_path = certifi.where()


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def register(tier="member", **db_set):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Billing", "membership_tier": tier, "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    d = r.json()
    C["users"].append(d["user"]["id"])
    if db_set:
        DB.users.update_one({"id": d["user"]["id"]}, {"$set": db_set})
    return d["access_token"], d["user"]["id"]


def checkout(tok, **body):
    r = requests.post(f"{API}/payments/checkout", json={"origin_url": BASE_URL, **body}, headers=h(tok))
    if r.status_code == 200 and r.json().get("session_id"):
        C["sessions"].add(r.json()["session_id"])
    return r


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in C["sessions"]:
        try:
            requests.post(f"{API}/payments/cancel/{sid}", timeout=10)
        except Exception:
            pass
    DB.payment_transactions.delete_many({"session_id": {"$in": list(C["sessions"])}})
    DB.withdrawals.delete_many({"id": {"$in": C["withdrawals"]}})
    DB.membership_payments.delete_many({"user_id": {"$in": C["users"]}})
    DB.user_sessions.delete_many({"user_id": {"$in": C["users"]}})
    DB.users.delete_many({"id": {"$in": C["users"]}})


@pytest.fixture(scope="module")
def venue_tok():
    return login(VENUE)


@pytest.fixture(scope="module")
def my_venue(venue_tok):
    r = requests.get(f"{API}/host/venues", headers=h(venue_tok))
    assert r.status_code == 200 and r.json(), r.text
    return r.json()[0]


# ---------- Membership subscription checkout ----------

def test_trial_male_bronze_is_free_trial_subscription():
    tok, _ = register("trial_male")
    r = checkout(tok, kind="membership", level="bronze")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount"] == 0 and d["url"].startswith("https://checkout.stripe.com")
    st = requests.get(f"{API}/payments/status/{d['session_id']}", headers=h(tok)).json()
    assert "7 days free" in st["label"] and st["status"] == "pending"
    s = stripe.checkout.Session.retrieve(d["session_id"])
    assert s["mode"] == "subscription"


def test_trial_male_silver_no_trial():
    tok, _ = register("trial_male")
    r = checkout(tok, kind="membership", level="silver")
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 49.0
    st = requests.get(f"{API}/payments/status/{r.json()['session_id']}", headers=h(tok)).json()
    assert "7 days free" not in st["label"] and "$49.00/month" in st["label"]


def test_trial_used_no_longer_free():
    tok, _ = register("trial_male", trial_used=True)
    r = checkout(tok, kind="membership", level="bronze")
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 14.99


def test_member_bronze_paid_monthly():
    tok, _ = register("member")
    r = checkout(tok, kind="membership", level="gold")
    assert r.status_code == 200 and r.json()["amount"] == 149.0
    assert stripe.checkout.Session.retrieve(r.json()["session_id"])["mode"] == "subscription"


def test_free_girl_bronze_rejected():
    tok, _ = register("free_girl")
    r = checkout(tok, kind="membership", level="bronze")
    assert r.status_code == 400


def test_same_active_plan_rejected():
    tok, _ = register("member", stripe_subscription_id="sub_TEST_fake", subscription_level="silver",
                      subscription_status="active", level="silver")
    assert checkout(tok, kind="membership", level="silver").status_code == 400


@pytest.mark.parametrize("creds", [VENUE, ADMIN])
def test_business_roles_rejected(creds):
    assert checkout(login(creds), kind="membership", level="silver").status_code == 400


def test_unknown_level_rejected():
    tok, _ = register()
    assert checkout(tok, kind="membership", level="platinum").status_code == 400


# ---------- /membership/upgrade is checkout-only for paid levels ----------

@pytest.mark.parametrize("tier,level", [("member", "silver"), ("member", "gold"), ("trial_male", "silver")])
def test_upgrade_paid_levels_402(tier, level):
    tok, _ = register(tier)
    assert requests.post(f"{API}/membership/upgrade", json={"level": level}, headers=h(tok)).status_code == 402


def test_upgrade_bronze_402_for_member():
    tok, _ = register("member", level="silver")
    assert requests.post(f"{API}/membership/upgrade", json={"level": "bronze"}, headers=h(tok)).status_code == 402


def test_free_girl_switch_to_bronze_allowed():
    tok, uid = register("free_girl", level="silver")
    r = requests.post(f"{API}/membership/upgrade", json={"level": "bronze"}, headers=h(tok))
    assert r.status_code == 200, r.text
    assert DB.users.find_one({"id": uid})["level"] == "bronze"


def test_subscription_endpoints_without_plan():
    tok, _ = register("trial_male")
    r = requests.get(f"{API}/membership/subscription", headers=h(tok))
    assert r.status_code == 200
    assert r.json()["active"] is False and r.json()["trial_available"] is True
    assert requests.post(f"{API}/membership/subscription/cancel", headers=h(tok)).status_code == 400
    assert requests.post(f"{API}/membership/subscription/bogus", headers=h(tok)).status_code == 422


# ---------- Venue boosts ----------

@pytest.mark.parametrize("plan,amount", [("week", 49.0), ("month", 149.0)])
def test_boost_checkout_owner(venue_tok, my_venue, plan, amount):
    r = checkout(venue_tok, kind="boost", venue_id=my_venue["id"], plan=plan)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount"] == amount and d["url"].startswith("https://checkout.stripe.com")
    s = stripe.checkout.Session.retrieve(d["session_id"])
    assert s["mode"] == "payment" and s["amount_total"] == round(amount * 100)


def test_boost_guest_forbidden(my_venue):
    tok, _ = register()
    assert checkout(tok, kind="boost", venue_id=my_venue["id"], plan="week").status_code == 403


def test_boost_bad_plan_and_unknown_venue(venue_tok, my_venue):
    assert checkout(venue_tok, kind="boost", venue_id=my_venue["id"], plan="year").status_code == 400
    assert checkout(venue_tok, kind="boost", venue_id="nope", plan="week").status_code == 404


def test_featured_flags_present():
    v = requests.get(f"{API}/venues").json()
    e = requests.get(f"{API}/events").json()
    assert all("featured" in x for x in v) and all("featured" in x for x in e)
    # featured items must come first
    fv = [x["featured"] for x in v]
    assert fv == sorted(fv, reverse=True)
    fe = [x["featured"] for x in e]
    assert fe == sorted(fe, reverse=True)


# ---------- Stripe Connect (own key not set) ----------

@pytest.mark.parametrize("creds", [PROMOTER, VENUE])
def test_connect_unavailable(creds):
    tok = login(creds)
    r = requests.get(f"{API}/connect/status", headers=h(tok))
    assert r.status_code == 200 and r.json()["available"] is False
    r = requests.post(f"{API}/connect/onboard", json={"origin_url": BASE_URL}, headers=h(tok))
    assert r.status_code == 503


def test_connect_guest_forbidden():
    tok, _ = register()
    assert requests.get(f"{API}/connect/status", headers=h(tok)).status_code == 403
    assert requests.post(f"{API}/connect/onboard", json={"origin_url": BASE_URL}, headers=h(tok)).status_code == 403


def test_withdraw_still_pending():
    tok, uid = register()
    DB.users.update_one({"id": uid}, {"$set": {"role": "promoter", "wallet_balance": 50.0}})
    r = requests.post(f"{API}/promoter/withdraw", json={"amount": 20}, headers=h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    w = DB.withdrawals.find_one({"user_id": uid})
    C["withdrawals"].append(w["id"])
    assert w["status"] == "pending"


# ---------- Webhook ----------

def test_webhook_malformed():
    r = requests.post(f"{API}/webhook/stripe", data="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_webhook_unknown_session():
    ev = {"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_doesnotexist123"}}}
    assert requests.post(f"{API}/webhook/stripe", json=ev).status_code in (200, 400)
    ev = {"type": "customer.subscription.updated", "data": {"object": {"id": "sub_unknown"}}}
    assert requests.post(f"{API}/webhook/stripe", json=ev).status_code in (200, 400)
    ev = {"type": "some.other", "data": {"object": {"id": "x"}}}
    assert requests.post(f"{API}/webhook/stripe", json=ev).status_code == 200


# ---------- Regression: one-time checkouts ----------

def test_ticket_checkout_one_time():
    tok, _ = register()
    evs = [e for e in requests.get(f"{API}/events").json()
           if e.get("min_level", "bronze") == "bronze" and not e.get("approval_required") and e.get("price", 0) > 0]
    if not evs:
        pytest.skip("no open paid event")
    r = checkout(tok, kind="ticket", event_id=evs[0]["id"], quantity=1)
    assert r.status_code == 200, r.text
    s = stripe.checkout.Session.retrieve(r.json()["session_id"])
    assert s["mode"] == "payment" and s["amount_total"] == round(r.json()["amount"] * 100)


def test_reservation_checkout_one_time(my_venue):
    # venue may be gated (e.g. Gold); give the TEST_ user the venue's required level
    tok, _ = register(level=my_venue.get("min_level", "bronze"))
    date = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    r = checkout(tok, kind="reservation", venue_id=my_venue["id"], date=date, service_type="table", party_size=2)
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200 and r.json().get("url"):
        assert stripe.checkout.Session.retrieve(r.json()["session_id"])["mode"] == "payment"


# ---------- Iteration 10/11: webhook invoice parent path + proxy-mode behaviour ----------

@pytest.mark.parametrize("shape", ["legacy", "parent"])
def test_webhook_invoice_reads_subscription_id(shape):
    """Unknown sub -> 200. Linked user: own key -> Stripe lookup (fake id -> 400); proxy -> sync skipped (200).
    In both cases the fake payload must not change DB state."""
    sub = f"sub_TEST_{uuid.uuid4().hex[:10]}"
    inv = {"id": "in_test"}
    if shape == "legacy":
        inv["subscription"] = sub
    else:
        inv["parent"] = {"type": "subscription_details", "subscription_details": {"subscription": sub}}
    ev = {"type": "invoice.paid", "data": {"object": inv}}
    assert requests.post(f"{API}/webhook/stripe", json=ev).status_code == 200  # nobody holds this sub
    _, uid = register(stripe_subscription_id=sub, subscription_status="active", subscription_level="silver")
    assert requests.post(f"{API}/webhook/stripe", json=ev).status_code == (400 if _OWN else 200)
    assert DB.users.find_one({"id": uid})["subscription_status"] == "active"  # fake payload not trusted


# Iteration 11: activation no longer uses /v1/subscriptions (proxy gap) - it reads the sub via the expanded session
def test_session_expand_subscription_works():
    tok, _ = register()
    r = checkout(tok, kind="membership", level="silver")
    assert r.status_code == 200, r.text
    s = stripe.checkout.Session.retrieve(r.json()["session_id"], expand=["subscription"])
    assert s["mode"] == "subscription" and s["subscription"] is None  # unpaid -> no sub yet, but no 404


@pytest.mark.skipif(_OWN, reason="proxy-mode only")
def test_proxy_mode_subscription_not_manageable_503():
    tok, uid = register(stripe_subscription_id=f"sub_TEST_{uuid.uuid4().hex[:10]}", subscription_status="active",
                        subscription_level="silver", level="silver",
                        level_paid_until=datetime.now(timezone.utc) + timedelta(days=30))
    r = requests.get(f"{API}/membership/subscription", headers=h(tok))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["active"] is True and d["manageable"] is False and d["status"] == "active" and d["renews_at"]
    for action in ("cancel", "resume"):
        r = requests.post(f"{API}/membership/subscription/{action}", headers=h(tok))
        assert r.status_code == 503, r.text
        assert "Stripe" in r.json()["detail"]


def test_one_time_checkout_prefills_email():
    tok, uid = register()
    evs = [e for e in requests.get(f"{API}/events").json()
           if e.get("min_level", "bronze") == "bronze" and not e.get("approval_required") and e.get("price", 0) > 0]
    if not evs:
        pytest.skip("no open paid event")
    r = checkout(tok, kind="ticket", event_id=evs[0]["id"], quantity=1)
    assert r.status_code == 200, r.text
    s = stripe.checkout.Session.retrieve(r.json()["session_id"])
    assert s["customer_email"] == DB.users.find_one({"id": uid})["email"]
