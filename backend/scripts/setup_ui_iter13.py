"""Creates 2 TEST_ users for the iteration-13 UI run (buyer + redeemer); writes /tmp/ui13.json. Cleanup: --cleanup."""
import json
import os
import sys
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
F = "/tmp/ui13.json"

if "--cleanup" in sys.argv:
    d = json.load(open(F))
    ids = [d["buyer"]["id"], d["redeemer"]["id"]]
    print("gifts", DB.gifts.delete_many({"buyer_id": {"$in": ids}}).deleted_count)
    print("tx", DB.payment_transactions.delete_many({"user_id": {"$in": ids}}).deleted_count)
    print("sessions", DB.user_sessions.delete_many({"user_id": {"$in": ids}}).deleted_count)
    print("users", DB.users.delete_many({"id": {"$in": ids}, "email": {"$regex": "^test_"}}).deleted_count)
    sys.exit(0)

out = {}
for k in ("buyer", "redeemer"):
    email = f"test_ui13_{k}_{uuid.uuid4().hex[:6]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "role": "guest",
                                                    "full_name": f"TEST_ UI13 {k}", "membership_tier": "member",
                                                    "marketing_opt_in": False})
    assert r.status_code == 201, r.text
    out[k] = {"id": r.json()["user"]["id"], "email": email, "password": "TestPass123!"}
json.dump(out, open(F, "w"))
print(json.dumps(out))
