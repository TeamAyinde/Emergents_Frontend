"""Iteration 17: lists TEST_ users created during T1's interrupted run window (read-only)."""
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
for u in DB.users.find({"email": {"$regex": "^test_", "$options": "i"}}, {"_id": 0, "id": 1, "email": 1, "created_at": 1}).sort("created_at", 1):
    print(u.get("created_at"), u["email"], u["id"])
