"""Door staff: venue owners invite people who can scan tickets and see the live door counter for their venues."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from routes.features import HostDep
from routes.push import notify
from server import current_user, db

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]


class StaffIn(BaseModel):
    venue_id: str
    email: EmailStr


class StaffOut(BaseModel):
    id: str
    venue_id: str
    venue_name: str
    user_id: str
    name: str
    email: str
    created_at: datetime


class DutyEvent(BaseModel):
    id: str
    title: str
    date: datetime
    venue_name: str
    tickets_sold: int
    capacity: int


class DutyOut(BaseModel):
    venues: List[str]
    events: List[DutyEvent]


async def is_door_staff(venue_id, user_id: str) -> bool:
    return bool(venue_id) and bool(await db.door_staff.find_one({"venue_id": venue_id, "user_id": user_id, "active": True}, {"_id": 1}))


async def _my_venues(user: dict) -> dict:
    filt = {} if user["role"] == "admin" else {"owner_id": user["id"]}
    return {v["id"]: v["name"] async for v in db.venues.find(filt, {"_id": 0, "id": 1, "name": 1})}


@router.get("/host/staff", response_model=List[StaffOut])
async def list_staff(user: HostDep):
    venues = await _my_venues(user)
    return [StaffOut(**s) async for s in db.door_staff.find({"venue_id": {"$in": list(venues)}, "active": True}, {"_id": 0}).sort("created_at", -1)]


@router.post("/host/staff", response_model=StaffOut, status_code=201)
async def add_staff(body: StaffIn, user: HostDep):
    venues = await _my_venues(user)
    if body.venue_id not in venues:
        raise HTTPException(403, "Not your venue")
    member = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not member:
        raise HTTPException(404, "No Nocturne account with that email — ask them to sign up first")
    if member["id"] == user["id"]:
        raise HTTPException(400, "You already have full access")
    if await is_door_staff(body.venue_id, member["id"]):
        raise HTTPException(409, "Already on your door team")
    doc = {"id": str(uuid.uuid4()), "venue_id": body.venue_id, "venue_name": venues[body.venue_id], "user_id": member["id"],
           "name": member.get("full_name") or member["email"], "email": member["email"], "created_by": user["id"],
           "created_at": datetime.now(timezone.utc), "active": True}
    await db.door_staff.insert_one(doc)
    doc.pop("_id", None)
    notify([member["id"]], "You're on the door 🎟️", f"{venues[body.venue_id]} added you to their door team. Tap to see tonight's events.",
           "/door", key=f"staff-{doc['id']}", kind="updates")
    return StaffOut(**doc)


@router.delete("/host/staff/{sid}")
async def remove_staff(sid: str, user: HostDep):
    venues = await _my_venues(user)
    res = await db.door_staff.update_one({"id": sid, "venue_id": {"$in": list(venues)}, "active": True},
                                         {"$set": {"active": False, "removed_at": datetime.now(timezone.utc), "removed_by": user["id"]}})
    if not res.modified_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/staff/duty", response_model=DutyOut)
async def my_duty(user: UserDep):
    """Venues I'm door staff for, plus their events from 12 hours ago onwards."""
    rows = await db.door_staff.find({"user_id": user["id"], "active": True}, {"_id": 0, "venue_id": 1, "venue_name": 1}).to_list(50)
    ids = [r["venue_id"] for r in rows]
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    events = [DutyEvent(id=e["id"], title=e["title"], date=e["date"], venue_name=e.get("venue_name", ""),
                        tickets_sold=e.get("tickets_sold", 0), capacity=e.get("capacity") or 200)
              async for e in db.events.find({"venue_id": {"$in": ids}, "date": {"$gte": since}}, {"_id": 0}).sort("date", 1).limit(20)]
    return DutyOut(venues=[r["venue_name"] for r in rows], events=events)
