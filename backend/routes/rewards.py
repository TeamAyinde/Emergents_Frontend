"""Reward points (redeem for credit) and tier-gated members perks wallet."""
import uuid
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import DESCENDING

from server import LEVEL_RANK, POINTS_MULTIPLIER, current_user, db, user_level

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
POINTS_PER_DOLLAR_CREDIT = 20  # 100 points = $5 credit


class LedgerRow(BaseModel):
    id: str
    points: int
    reason: str
    created_at: datetime


class RewardsOut(BaseModel):
    points: int
    credit_balance: float
    multiplier: float
    points_per_dollar_credit: int
    history: List[LedgerRow]


class RedeemIn(BaseModel):
    points: int = Field(ge=100, le=1_000_000)


@router.get("/rewards", response_model=RewardsOut)
async def rewards(user: UserDep):
    hist = [LedgerRow(**r) async for r in db.points_ledger.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING).limit(50)]
    return RewardsOut(points=int(user.get("points", 0)), credit_balance=round(user.get("credit_balance", 0.0), 2),
                      multiplier=POINTS_MULTIPLIER[user_level(user)], points_per_dollar_credit=POINTS_PER_DOLLAR_CREDIT,
                      history=hist)


@router.post("/rewards/redeem", response_model=RewardsOut)
async def redeem(body: RedeemIn, user: UserDep):
    if body.points % 100:
        raise HTTPException(400, "Redeem in blocks of 100 points")
    credit = round(body.points / POINTS_PER_DOLLAR_CREDIT, 2)
    res = await db.users.update_one({"id": user["id"], "points": {"$gte": body.points}},
                                    {"$inc": {"points": -body.points, "credit_balance": credit}})
    if res.modified_count == 0:
        raise HTTPException(400, "Not enough points")
    await db.points_ledger.insert_one({"id": str(uuid.uuid4()), "user_id": user["id"], "points": -body.points,
                                       "reason": f"Redeemed for ${credit:.2f} credit", "created_at": datetime.now(timezone.utc)})
    return await rewards(await db.users.find_one({"id": user["id"]}, {"_id": 0}))


class PerkOut(BaseModel):
    id: str
    partner_name: str
    title: str
    description: str
    category: str
    image_url: str
    min_level: str
    locked: bool
    claimed: bool
    code: str  # empty until claimed


@router.get("/perks", response_model=List[PerkOut])
async def perks(user: UserDep):
    claimed = {c["perk_id"] async for c in db.perk_claims.find({"user_id": user["id"]}, {"perk_id": 1})}
    lvl = LEVEL_RANK[user_level(user)]
    out = []
    async for p in db.perks.find({}, {"_id": 0}).sort("min_level", 1):
        is_claimed = p["id"] in claimed
        out.append(PerkOut(**{k: p[k] for k in ("id", "partner_name", "title", "description", "category", "image_url", "min_level")},
                           locked=LEVEL_RANK[p["min_level"]] > lvl, claimed=is_claimed, code=p["code"] if is_claimed else ""))
    out.sort(key=lambda x: (x.locked, LEVEL_RANK[x.min_level]))
    return out


@router.post("/perks/{pid}/claim", response_model=PerkOut)
async def claim(pid: str, user: UserDep):
    p = await db.perks.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Perk not found")
    if LEVEL_RANK[p["min_level"]] > LEVEL_RANK[user_level(user)]:
        raise HTTPException(403, f"{p['min_level'].capitalize()} membership required")
    await db.perk_claims.update_one({"user_id": user["id"], "perk_id": pid},
                                    {"$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}}, upsert=True)
    return PerkOut(**{k: p[k] for k in ("id", "partner_name", "title", "description", "category", "image_url", "min_level")},
                   locked=False, claimed=True, code=p["code"])
