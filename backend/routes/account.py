"""Account self-service: download my data, delete my account (Google Play / GDPR requirements)."""
import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from server import current_user, db

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
log = logging.getLogger("account")

# collections holding a member's records, and the field that links them
OWNED = {
    "tickets": "user_id", "table_bookings": "user_id", "reservations": "user_id", "event_requests": "user_id",
    "payment_transactions": "user_id", "membership_payments": "user_id", "receipts": "user_id", "gifts": "buyer_id",
    "partner_bookings": "user_id", "feedback": "user_id", "points_ledger": "user_id", "perk_claims": "user_id",
    "withdrawals": "user_id", "support_reports": "user_id", "concierge_messages": "member_id", "concierge_threads": "member_id",
}
PRIVATE_USER_FIELDS = ("_id", "password_hash")


@router.get("/me/export")
async def export_my_data(user: UserDep):
    """Everything we hold about the signed-in member, as a JSON file."""
    me = {k: v for k, v in user.items() if k not in PRIVATE_USER_FIELDS}
    data = {"exported_at": datetime.now(timezone.utc), "account": me}
    for coll, field in OWNED.items():
        data[coll] = await db[coll].find({field: user["id"]}, {"_id": 0}).to_list(5000)
    data["door_staff"] = await db.door_staff.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    data["venue_vip_flags"] = await db.venue_vips.find({"user_id": user["id"]}, {"_id": 0, "flagged_by": 0}).to_list(100)
    body = json.dumps(data, default=str, indent=2, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="nocturne-my-data.json"'})


class DeleteIn(BaseModel):
    confirm: str  # must be "DELETE"


@router.delete("/me")
async def delete_my_account(body: DeleteIn, user: UserDep):
    """Deletes the account and personal data. Booking and payment records the venues and tax rules need are kept
    without any personal details."""
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm')
    uid = user["id"]
    if user["role"] == "venue_owner" and await db.venues.find_one({"owner_id": uid}, {"_id": 1}):
        raise HTTPException(400, "You still own venues. Contact support to transfer or close them, then delete your account.")
    if user["role"] == "admin" and await db.users.count_documents({"role": "admin"}) <= 1:
        raise HTTPException(400, "You're the only admin. Make someone else an admin first.")

    from routes.billing import cancel_subscription_now  # noqa: E402

    await cancel_subscription_now(user)  # stop future membership charges
    # personal conversations, reports and points: removed
    for coll in ("concierge_messages", "concierge_threads", "support_reports", "points_ledger", "perk_claims"):
        await db[coll].delete_many({OWNED[coll]: uid})
    await db.event_requests.update_many({"user_id": uid, "status": "pending"}, {"$set": {"status": "cancelled"}})
    await db.door_staff.update_many({"user_id": uid}, {"$set": {"active": False, "removed_at": datetime.now(timezone.utc),
                                                                "name": "Deleted member", "email": f"deleted-{uid[:8]}"}})
    await db.venue_vips.update_many({"user_id": uid}, {"$set": {"active": False, "note": None}})
    # records kept for venues / accounting: strip personal details
    scrub = {"$unset": {"email": "", "user_email": "", "phone": "", "notes": "", "comment": "", "comments": "",
                        "recipient_email": "", "message": ""},
             "$set": {"user_deleted": True, "user_name": "Deleted member"}}
    for coll in ("tickets", "table_bookings", "reservations", "event_requests", "payment_transactions", "membership_payments",
                 "receipts", "gifts", "partner_bookings", "feedback", "withdrawals"):
        await db[coll].update_many({OWNED[coll]: uid}, {**scrub, "$unset": {**scrub["$unset"], "note": ""}})
    await db.deleted_accounts.insert_one({"user_id": uid, "role": user["role"], "deleted_at": datetime.now(timezone.utc)})
    await db.users.delete_one({"id": uid})  # explicit, user-confirmed deletion
    log.info("account %s deleted by owner request", uid)
    return {"deleted": True}
