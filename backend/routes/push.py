"""Push notifications via the Emergent managed relay (guest list, tables, reservations, concierge)."""
import asyncio
import inspect
import logging
import os
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


def notify(user_ids, title: str, message: str, url: str = "", key: Optional[str] = None) -> None:
    """Fire-and-forget push; `user_ids` may be a list or an awaitable that resolves to one (looked up off the
    request path). A failed push never blocks the booking or reply that triggered it."""

    async def runner():
        try:
            resolved = await user_ids if inspect.isawaitable(user_ids) else user_ids
            ids = list(dict.fromkeys(u for u in resolved if u))
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
