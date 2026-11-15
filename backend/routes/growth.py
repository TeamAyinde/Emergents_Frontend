"""Monthly promoter leaderboard (with winner bonus), gift memberships, spotlight rules."""
import secrets
from html import escape
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from server import LEVEL_PRICE, LEVEL_RANK, current_user, db, user_level

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
WINNER_BONUS = 100.0
SPOTLIGHT_DAILY_CAP = 2
GIFT_LEVELS = ("silver", "gold")
GIFT_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


# ---------- Monthly leaderboard ----------

class MonthlyEntry(BaseModel):
    user_id: str
    full_name: str
    guests: int
    earnings: float


class MonthlyBoard(BaseModel):
    month: str
    bonus: float
    entries: List[MonthlyEntry]
    last_winner: Optional[dict] = None


async def _rank(month: str, limit: int = 20) -> List[MonthlyEntry]:
    start, end = _month_bounds(month)
    rows = await db.tickets.aggregate([
        {"$match": {"promoter_id": {"$ne": None}, "created_at": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$promoter_id", "guests": {"$sum": "$quantity"}, "earnings": {"$sum": "$promoter_earning"}}},
        {"$lookup": {"from": "users", "localField": "_id", "foreignField": "id", "as": "u"}},
        {"$match": {"u.role": "promoter"}},
        {"$sort": {"guests": -1, "earnings": -1}},
        {"$limit": limit},
    ]).to_list(limit)
    names = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": [r["_id"] for r in rows]}, "role": "promoter"}, {"_id": 0, "id": 1, "full_name": 1}).to_list(limit)}
    return [MonthlyEntry(user_id=r["_id"], full_name=names[r["_id"]]["full_name"], guests=r["guests"],
                         earnings=round(r["earnings"], 2)) for r in rows if r["_id"] in names]


async def _award_last_month() -> Optional[dict]:
    """Pays last month's winner once (idempotent via the month as _id)."""
    last = (_now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    done = await db.leaderboard_awards.find_one({"_id": last})
    if done:
        return done
    top = await _rank(last, 1)
    if not top:
        return None
    award = {"_id": last, "user_id": top[0].user_id, "full_name": top[0].full_name, "guests": top[0].guests,
             "bonus": WINNER_BONUS, "created_at": _now()}
    try:
        await db.leaderboard_awards.insert_one(award)
    except DuplicateKeyError:
        return await db.leaderboard_awards.find_one({"_id": last})
    await db.users.update_one({"id": top[0].user_id}, {"$inc": {"wallet_balance": WINNER_BONUS}})
    from routes.notify import background, winner_email  # noqa: E402

    background(winner_email(award))
    return award


@router.get("/promoter/leaderboard/monthly", response_model=MonthlyBoard)
async def monthly_leaderboard():
    winner = await _award_last_month()
    month = _now().strftime("%Y-%m")
    last = {"month": winner["_id"], "full_name": winner["full_name"], "guests": winner["guests"],
            "bonus": winner["bonus"]} if winner else None
    return MonthlyBoard(month=month, bonus=WINNER_BONUS, entries=await _rank(month), last_winner=last)


# ---------- Spotlight rules ----------

async def spotlight_check(event_id: str, user: dict) -> tuple[bool, str, int]:
    """(allowed, reason, remaining today). Promoters may only spotlight events they've brought guests to."""
    day = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = await db.spotlights.count_documents({"user_id": user["id"], "created_at": {"$gte": day}})
    remaining = max(0, SPOTLIGHT_DAILY_CAP - used)
    if user["role"] == "admin":
        return True, "", remaining
    if not await db.tickets.find_one({"event_id": event_id, "promoter_id": user["id"]}, {"_id": 1}):
        return False, "Bring at least one guest with your code to spotlight this event", remaining
    if remaining == 0:
        return False, f"Daily limit reached — {SPOTLIGHT_DAILY_CAP} spotlights per day", 0
    return True, "", remaining


@router.get("/spotlight/eligibility/{event_id}")
async def spotlight_eligibility(event_id: str, user: UserDep):
    if user["role"] not in ("promoter", "admin"):
        return {"eligible": False, "reason": "Only promoters can spotlight events", "remaining_today": 0}
    ok, reason, remaining = await spotlight_check(event_id, user)
    return {"eligible": ok, "reason": reason, "remaining_today": remaining}


# ---------- Gift memberships ----------

class GiftOut(BaseModel):
    id: str
    code: str
    level: str
    days: int
    recipient_email: Optional[str] = None
    note: Optional[str] = None
    redeemed: bool = False
    redeemed_by_name: Optional[str] = None
    email_status: Optional[str] = None
    created_at: datetime


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


def quote_gift(level: Optional[str], email: Optional[str], note: Optional[str]) -> dict:
    if level not in GIFT_LEVELS:
        raise HTTPException(400, "Gift Silver or Gold")
    return {"total": LEVEL_PRICE[level], "label": f"Gift · Nocturne {level.capitalize()} · 1 month", "venue_id": None,
            "payload": {"gift_level": level, "recipient_email": (email or "").strip().lower() or None,
                        "note": (note or "").strip()[:200] or None},
            "no_credit": True}


async def create_gift(tx: dict) -> str:
    p = tx["payload"]
    gid = str(uuid.uuid4())
    await db.gifts.insert_one({
        "id": gid, "code": "GIFT-" + secrets.token_hex(3).upper(), "level": p["gift_level"], "days": GIFT_DAYS,
        "buyer_id": tx["user_id"], "recipient_email": p.get("recipient_email"), "note": p.get("note"),
        "redeemed": False, "amount": tx["amount"], "created_at": _now(),
    })
    if p.get("recipient_email"):
        from routes.notify import background  # noqa: E402 — never slow the payment confirmation

        await db.gifts.update_one({"id": gid}, {"$set": {"email_sends": 1}})
        background(email_gift(gid))
    return gid


async def email_gift(gid: str) -> None:
    """Emails the code to the friend (fixed template; buyer's note is escaped)."""
    from services.emailer import EMAIL_FROM_NAME, send_email  # noqa: E402

    gift = await db.gifts.find_one({"id": gid}, {"_id": 0})
    buyer = await db.users.find_one({"id": gift["buyer_id"]}, {"_id": 0, "full_name": 1})
    name = escape((buyer or {}).get("full_name", "A friend"))
    level = gift["level"].capitalize()
    note = f'<p style="font-style:italic;color:#555">&ldquo;{escape(gift["note"])}&rdquo;</p>' if gift.get("note") else ""
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
        f'<h2 style="margin:0 0 12px">{name} gifted you a month of {escape(EMAIL_FROM_NAME)} {level}</h2>'
        f"{note}"
        '<p>Your gift code:</p>'
        f'<p style="font-size:24px;font-weight:bold;letter-spacing:2px;color:#b8860b">{escape(gift["code"])}</p>'
        f'<p>Open the {escape(EMAIL_FROM_NAME)} app, go to Profile &rarr; Gifts and enter the code to unlock '
        f'{gift["days"]} days of {level} perks.</p>'
        f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. We never ask for your password or card details by email.</p>'
        "</td></tr></table>"
    )
    try:
        await send_email(to=gift["recipient_email"], subject=f"{(buyer or {}).get('full_name', 'A friend')} sent you a {EMAIL_FROM_NAME} gift", html=html)
        status = "sent"
    except Exception as exc:
        status = f"failed: {exc}"[:120]
    await db.gifts.update_one({"id": gid}, {"$set": {"email_status": status}})


@router.get("/gifts/mine", response_model=List[GiftOut])
async def my_gifts(user: UserDep):
    return [GiftOut(**g) async for g in db.gifts.find({"buyer_id": user["id"]}, {"_id": 0}).sort("created_at", -1)]


@router.post("/gifts/redeem")
async def redeem_gift(body: RedeemIn, user: UserDep):
    code = body.code.strip().upper()
    gift = await db.gifts.find_one({"code": code}, {"_id": 0})
    if not gift:
        raise HTTPException(404, "Gift code not found")
    if gift["buyer_id"] == user["id"]:
        raise HTTPException(400, "Share this gift with a friend — you can't redeem your own")
    if LEVEL_RANK[user_level(user)] > LEVEL_RANK[gift["level"]] or user["role"] in ("admin", "venue_owner"):
        raise HTTPException(400, "Your current level already includes everything in this gift — pass it to a friend")
    res = await db.gifts.update_one({"code": code, "redeemed": False}, {"$set": {
        "redeemed": True, "redeemed_by": user["id"], "redeemed_by_name": user["full_name"], "redeemed_at": _now()}})
    if res.modified_count == 0:
        raise HTTPException(409, "This gift has already been redeemed")
    cur_until = user.get("gift_until")
    cur_until = cur_until.replace(tzinfo=timezone.utc) if cur_until and not cur_until.tzinfo else cur_until
    active = bool(cur_until and cur_until > _now())
    cur_level = user.get("gift_level") if active else None
    if cur_level == gift["level"]:
        level, until = cur_level, cur_until + timedelta(days=gift["days"])  # same level: stack the time
    elif cur_level and LEVEL_RANK[cur_level] > LEVEL_RANK[gift["level"]]:
        level, until = cur_level, max(cur_until, _now() + timedelta(days=gift["days"]))
    else:
        level, until = gift["level"], _now() + timedelta(days=gift["days"])
    await db.users.update_one({"id": user["id"]}, {"$set": {"gift_level": level, "gift_until": until}})
    return {"level": level, "until": until}
