"""Push notifications via the Emergent managed relay (guest list, tables, reservations, concierge)."""
import asyncio
import inspect
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server import current_user, db

router = APIRouter(prefix="/api")
logger = logging.getLogger("push")
UserDep = Annotated[dict, Depends(current_user)]

PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")

_client = httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": PUSH_KEY}, timeout=10.0)
_tasks: set = set()


class RegisterPushBody(BaseModel):
    user_id: str
    platform: str  # "android" | "ios"
    device_token: str


@router.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody, user: UserDep):
    if body.user_id != user["id"]:
        raise HTTPException(403, "You can only register your own device")
    if body.platform not in {"android", "ios"}:
        raise HTTPException(400, "Platform must be android or ios")
    resp = await _client.post("/api/v1/push/users/register", json=body.model_dump())
    if resp.status_code == 401:
        raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
    if resp.status_code >= 500:
        raise HTTPException(502, "Push provider unavailable")
    resp.raise_for_status()
    return {"status": "registered"}


async def send_push(recipients: list[str], data: dict, idempotency_key: Optional[str] = None, _attempt: int = 0) -> None:
    if not recipients:
        return
    if len(recipients) > 100:
        raise ValueError("max 100 recipients per /trigger call; chunk before sending")
    if "title" not in data or "message" not in data:
        raise ValueError("data must include title and message")
    payload: dict = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    resp = await _client.post("/api/v1/push/trigger", json=payload)
    if resp.status_code == 401:
        raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
    code = resp.json().get("code", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
    if code == "idempotency_key_in_progress" and idempotency_key and _attempt < 3:
        await asyncio.sleep(3)
        return await send_push(recipients, data, idempotency_key=idempotency_key, _attempt=_attempt + 1)
    if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
        logger.warning(f"Push paused: {code} ({resp.status_code}): {resp.json().get('message', '')}")
        return
    if resp.status_code >= 500:
        raise HTTPException(502, "Push provider unavailable")
    resp.raise_for_status()


def notify(user_ids, title: str, message: str, url: str = "", key: Optional[str] = None, kind: str = "updates") -> None:
    """Fire-and-forget push; `user_ids` may be a list or an awaitable that resolves to one (looked up off the
    request path). Members who switched `kind` off are skipped. A failed push never blocks the action."""

    async def runner():
        try:
            resolved = await user_ids if inspect.isawaitable(user_ids) else user_ids
            ids = list(dict.fromkeys(u for u in resolved if u))
            muted = {u["id"] async for u in db.users.find({"id": {"$in": ids}, f"push_prefs.{kind}": False}, {"id": 1})}
            ids = [u for u in ids if u not in muted]
            if not ids:
                return
            data = {"title": title, "message": message}
            if url:
                data["action_url"] = url
            await send_push(ids[:100], data, idempotency_key=key)
        except Exception as e:
            logger.warning(f"Push failed (non-blocking): {e}")

    task = asyncio.create_task(runner())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def venue_owner(venue_id: Optional[str]) -> Optional[str]:
    v = await db.venues.find_one({"id": venue_id}, {"_id": 0, "owner_id": 1}) if venue_id else None
    return (v or {}).get("owner_id")


# ---------- Push preferences ----------

PUSH_KEYS = ("event_night", "updates", "concierge", "sales", "door_rush", "table_offers")


class PushPrefs(BaseModel):
    event_night: bool = True  # 2 hours before doors open
    updates: bool = True  # guest list decisions, waitlist spots, new requests, bookings, reservations
    concierge: bool = True  # concierge replies
    sales: bool = True  # promoters: someone bought through your link + weekly recap
    door_rush: bool = True  # hosts: live check-in milestones
    table_offers: bool = True  # event-day VIP table offers


class PushPrefsIn(BaseModel):
    event_night: Optional[bool] = None
    updates: Optional[bool] = None
    concierge: Optional[bool] = None
    sales: Optional[bool] = None
    door_rush: Optional[bool] = None
    table_offers: Optional[bool] = None


@router.get("/me/push-prefs", response_model=PushPrefs)
async def get_push_prefs(user: UserDep):
    p = user.get("push_prefs") or {}
    return PushPrefs(**{k: p.get(k, True) for k in PUSH_KEYS})


@router.put("/me/push-prefs", response_model=PushPrefs)
async def put_push_prefs(body: PushPrefsIn, user: UserDep):
    """Partial update: only the keys sent are changed."""
    new = (await get_push_prefs(user)).model_copy(update=body.model_dump(exclude_none=True))
    await db.users.update_one({"id": user["id"]}, {"$set": {"push_prefs": new.model_dump()}})
    return new


# ---------- Event night alerts (2 hours before doors) ----------

NIGHT_EVERY_S = 300
NIGHT_LEAD = timedelta(hours=2)


async def send_night_alerts() -> int:
    """Pushes every ticket holder whose event starts within the next 2 hours, once per ticket."""
    now = datetime.now(timezone.utc)
    sent = 0
    async for t in db.tickets.find({"event_date": {"$gt": now, "$lte": now + NIGHT_LEAD},
                                    "night_alert_sent": {"$ne": True}}, {"_id": 0}):
        claimed = await db.tickets.update_one({"id": t["id"], "night_alert_sent": {"$ne": True}},
                                              {"$set": {"night_alert_sent": True}})
        if not claimed.modified_count:
            continue
        d = t["event_date"] if t["event_date"].tzinfo else t["event_date"].replace(tzinfo=timezone.utc)
        mins = max(1, int((d - now).total_seconds() // 60))
        when = f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins} min"
        notify([t["user_id"]], f"Tonight: {t['event_title']}",
               f"Doors open in {when} at {t.get('venue_name', 'the venue')}. Tap to have your ticket ready to scan.",
               f"/ticket/{t['id']}", key=f"night-{t['id']}", kind="event_night")
        sent += 1
    return sent


async def night_alert_loop() -> None:
    while True:
        try:
            await send_night_alerts()
        except Exception:
            logger.exception("night alert round failed")
        await asyncio.sleep(NIGHT_EVERY_S)
