import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv("/app/backend/.env")
_DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def grant_credit(uid: str, amount: float) -> None:
    """Gives a TEST_ user reward credit so paid items go through the credit path (no card). TEST_ users only."""
    _DB.users.update_one({"id": uid, "email": {"$regex": "^test_", "$options": "i"}}, {"$set": {"credit_balance": float(amount)}})


_LOOP = None


def run(coro):
    """Runs a coroutine on one shared loop (motor binds to the first loop it is used on)."""
    global _LOOP
    import asyncio
    _LOOP = _LOOP or asyncio.new_event_loop()
    return _LOOP.run_until_complete(coro)


def simulate_paid(session_id: str) -> dict:
    """Simulates Stripe reporting a card checkout as paid: runs the same fulfilment as the webhook/status poll
    (payments._complete) in-process against the same DB. Returns the payment transaction."""
    sys.path.insert(0, "/app/backend")
    import server  # noqa: F401  (import order mirrors uvicorn)
    from routes import payments
    run(payments._complete(session_id))
    return _DB.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})


def set_level(uid: str, level: str) -> None:
    """Simulates a paid Stripe membership upgrade for a TEST_ user (memberships cannot use credit)."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    _DB.users.update_one({"id": uid, "email": {"$regex": "^test_", "$options": "i"}},
                         {"$set": {"level": level, "level_since": now, "level_paid_until": now + timedelta(days=30)}})


# Iteration 8: the iteration-7 LEGACY_402 skip list was removed. Legacy tests now set up paid items via the credit
# path of POST /api/payments/checkout (grant_credit), credit-covered direct purchase, a simulated card payment
# (simulate_paid) or a simulated paid upgrade (set_level), and assert 402 on the direct paid endpoints.

