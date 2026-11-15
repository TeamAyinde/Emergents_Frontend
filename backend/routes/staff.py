"""Door staff: venue owners invite people who can scan tickets and see the live door counter for their venues."""
import logging
import uuid
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from routes.features import HostDep
from routes.notify import background
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
    user_id: Optional[str] = None  # None until an invited person signs up
    name: str
    email: str
    status: str = "active"  # "active" | "invited"
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
    email = body.email.lower()
    member = await db.users.find_one({"email": email}, {"_id": 0})
    if member and member["id"] == user["id"]:
        raise HTTPException(400, "You already have full access")
    if await db.door_staff.find_one({"venue_id": body.venue_id, "email": email, "active": True}, {"_id": 1}):
        raise HTTPException(409, "Already on your door team")
    doc = {"id": str(uuid.uuid4()), "venue_id": body.venue_id, "venue_name": venues[body.venue_id],
           "user_id": member["id"] if member else None, "name": (member or {}).get("full_name") or email, "email": email,
           "status": "active" if member else "invited", "created_by": user["id"],
           "created_at": datetime.now(timezone.utc), "active": True}
    await db.door_staff.insert_one(doc)
    doc.pop("_id", None)
    if member:
        notify([member["id"]], "You're on the door 🎟️", f"{venues[body.venue_id]} added you to their door team. Tap to see tonight's events.",
               "/door", key=f"staff-{doc['id']}", kind="updates")
    else:
        background(_invite_email(email, venues[body.venue_id], user.get("full_name") or "The venue team"))
    return StaffOut(**doc)


async def _invite_email(email: str, venue_name: str, inviter: str) -> None:
    from html import escape

    from services.emailer import send_email  # noqa: E402

    origin = ((await db.settings.find_one({"_id": "public_origin"})) or {}).get("url", "")
    link = f"{origin.rstrip('/')}/sign-up?email={quote(email)}" if origin.startswith("https://") else ""
    cta = (f'<p><a href="{escape(link)}" style="display:inline-block;padding:12px 20px;background:#d4af37;color:#111;'
           f'text-decoration:none;border-radius:999px;font-weight:bold">Create your account</a></p>') if link else \
        "<p>Download the Nocturne app and create your account.</p>"
    html = ('<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
            f"<h2 style=\"margin:0 0 12px\">You're invited to the door team</h2>"
            f"<p>{escape(inviter)} added you as door staff at <strong>{escape(venue_name)}</strong>. "
            "Sign up with this email address and you'll be able to scan tickets and see the live door counter.</p>"
            f"{cta}<p style=\"font-size:12px;color:#888\">Use exactly {escape(email)} when you sign up.</p></td></tr></table>")
    try:
        await send_email(to=email, subject=f"{venue_name} invited you to their door team", html=html)
    except Exception:
        logging.getLogger("staff").exception("door staff invite email failed")


async def claim_invites(user: dict) -> None:
    """Called when an account is created: pending door-staff invites for this email become active."""
    await db.door_staff.update_many({"email": user["email"].lower(), "user_id": None, "active": True},
                                    {"$set": {"user_id": user["id"], "name": user.get("full_name") or user["email"],
                                              "status": "active", "claimed_at": datetime.now(timezone.utc)}})


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
