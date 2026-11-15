"""Iteration-14 UI setup: TEST_ buyer with 3 seeded gifts (fresh / maxed-out sends / redeemed); writes /tmp/ui14.json.
Optional --ticket-user also creates a TEST_ user whose email is delivered@resend.dev (for the 4242 booking-email run).
Cleanup: --cleanup (deletes only the ids written to /tmp/ui14.json)."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
F = "/tmp/ui14.json"


def reg(email, name):
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "role": "guest",
                                                    "full_name": name, "membership_tier": "member", "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    return {"id": r.json()["user"]["id"], "email": email, "password": "TestPass123!"}


if "--cleanup" in sys.argv:
    d = json.load(open(F))
    ids = [u["id"] for u in d["users"]]
    print("gifts", DB.gifts.delete_many({"id": {"$in": d["gifts"]}}).deleted_count)
    print("tickets", DB.tickets.delete_many({"user_id": {"$in": ids}}).deleted_count)
    print("tx", DB.payment_transactions.delete_many({"user_id": {"$in": ids}}).deleted_count)
    print("sessions", DB.user_sessions.delete_many({"user_id": {"$in": ids}}).deleted_count)
    print("users", DB.users.delete_many({"id": {"$in": ids}}).deleted_count)
    sys.exit(0)

if "--ticket-user" in sys.argv:
    d = json.load(open(F))
    u = reg("delivered@resend.dev", "TEST_ UI14 Ticket")
    d["users"].append(u)
    d["ticket_user"] = u
    json.dump(d, open(F, "w"))
    print(json.dumps(u))
    sys.exit(0)

buyer = reg(f"test_ui14_{uuid.uuid4().hex[:6]}@nocturne.app", "TEST_ UI14 buyer")
gifts, codes = [], {}
for k, extra in (("fresh", {}), ("maxed", {"recipient_email": "delivered@resend.dev", "email_status": "sent", "email_sends": 3}),
                 ("redeemed", {"redeemed": True, "redeemed_by_name": "TEST_ Friend"})):
    gid, code = f"TEST_{uuid.uuid4()}", "GIFT-T" + uuid.uuid4().hex[:5].upper()
    DB.gifts.insert_one({"id": gid, "code": code, "level": "gold", "days": 30, "buyer_id": buyer["id"], "recipient_email": None,
                         "note": None, "redeemed": False, "amount": 0, "created_at": datetime.now(timezone.utc), **extra})
    gifts.append(gid)
    codes[k] = code
out = {"users": [buyer], "buyer": buyer, "gifts": gifts, "codes": codes}
json.dump(out, open(F, "w"))
print(json.dumps(out))
