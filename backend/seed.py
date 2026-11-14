"""Idempotent seed: test users, California venues, upcoming events."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


TEST_USERS = [
    {
        "email": "guest@nocturne.app",
        "password": "GuestPass123!",
        "full_name": "Ava Guest",
        "role": "guest",
        "membership_tier": "member",
        "referral_code": "AVA1GUEST",
    },
    {
        "email": "promoter@nocturne.app",
        "password": "PromoterPass123!",
        "full_name": "Marco Promo",
        "role": "promoter",
        "membership_tier": "member",
        "referral_code": "MARCO1",
    },
    {
        "email": "venue@nocturne.app",
        "password": "VenuePass123!",
        "full_name": "Luxe Lounge Owner",
        "role": "venue_owner",
        "membership_tier": "venue",
        "referral_code": "LUXE1",
    },
    {
        "email": "admin@nocturne.app",
        "password": "AdminPass123!",
        "full_name": "Night Admin",
        "role": "admin",
        "membership_tier": "corporate",
        "referral_code": "ADMIN1",
    },
]


VENUES = [
    {
        "name": "Velvet Sky Rooftop",
        "city": "Los Angeles", "state": "CA", "category": "Rooftop Lounge",
        "image_url": "https://images.unsplash.com/photo-1756981168649-0e3c3c8a32f3?crop=entropy&cs=srgb&fm=jpg&w=1200&q=80",
        "rating": 4.8, "price_range": "$$$",
        "description": "Panoramic downtown views with hand-crafted cocktails and a sultry rooftop vibe.",
    },
    {
        "name": "Club Noire",
        "city": "Los Angeles", "state": "CA", "category": "Nightclub",
        "image_url": "https://images.unsplash.com/photo-1545128485-c400e7702796?crop=entropy&cs=srgb&fm=jpg&w=1200&q=80",
        "rating": 4.7, "price_range": "$$$$",
        "description": "LA's most exclusive underground nightclub. Bottle service only.",
    },
    {
        "name": "Mirage Lounge",
        "city": "West Hollywood", "state": "CA", "category": "Lounge",
        "image_url": "https://images.unsplash.com/photo-1630395822970-acd6a691d97e?crop=entropy&cs=srgb&fm=jpg&w=1200&q=80",
        "rating": 4.6, "price_range": "$$$",
        "description": "Neon-drenched hideaway for the industry crowd.",
    },
    {
        "name": "Harbor House",
        "city": "San Diego", "state": "CA", "category": "Restaurant & Bar",
        "image_url": "https://images.unsplash.com/photo-1600891964599-f61ba0e24092?w=1200&q=80",
        "rating": 4.5, "price_range": "$$$",
        "description": "Chef-driven coastal menu with a waterfront patio.",
    },
    {
        "name": "The Golden Hour",
        "city": "Beverly Hills", "state": "CA", "category": "Cocktail Bar",
        "image_url": "https://images.unsplash.com/photo-1572116469696-31de0f17cc34?w=1200&q=80",
        "rating": 4.9, "price_range": "$$$$",
        "description": "Gold-leafed interiors and bespoke cocktails. Members and reservations only.",
    },
    {
        "name": "The Ember Room",
        "city": "San Francisco", "state": "CA", "category": "Speakeasy",
        "image_url": "https://images.unsplash.com/photo-1514933651103-005eec06c04b?w=1200&q=80",
        "rating": 4.7, "price_range": "$$$",
        "description": "Hidden speakeasy behind a bookstore. Reservations required.",
    },
    {
        "name": "Palm Pavilion",
        "city": "Palm Springs", "state": "CA", "category": "Resort Lounge",
        "image_url": "https://images.unsplash.com/photo-1540541338287-41700207dee6?w=1200&q=80",
        "rating": 4.5, "price_range": "$$$",
        "description": "Poolside bottle service and desert sunsets.",
    },
    {
        "name": "Riviera Supperclub",
        "city": "Santa Monica", "state": "CA", "category": "Supperclub",
        "image_url": "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=1200&q=80",
        "rating": 4.6, "price_range": "$$$$",
        "description": "Michelin-leaning dinner then live DJ sets till 2am.",
    },
]


def _event_image(i: int) -> str:
    imgs = [
        "https://images.unsplash.com/photo-1545128485-c400e7702796?crop=entropy&cs=srgb&fm=jpg&w=1400&q=80",
        "https://images.unsplash.com/photo-1618409698966-6caa2b95733a?crop=entropy&cs=srgb&fm=jpg&w=1400&q=80",
        "https://images.unsplash.com/photo-1630395822970-acd6a691d97e?crop=entropy&cs=srgb&fm=jpg&w=1400&q=80",
        "https://images.unsplash.com/photo-1571266028243-d220c9c3b31f?w=1400&q=80",
        "https://images.unsplash.com/photo-1574391884720-bbc3740c59d1?w=1400&q=80",
    ]
    return imgs[i % len(imgs)]


async def seed_all(db):
    # Users
    for u in TEST_USERS:
        existing = await db.users.find_one({"email": u["email"]})
        if existing:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "email": u["email"],
            "password_hash": _hash(u["password"]),
            "full_name": u["full_name"],
            "role": u["role"],
            "membership_tier": u["membership_tier"],
            "referral_code": u["referral_code"],
            "wallet_balance": 0.0,
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(doc)

    # Venues
    for v in VENUES:
        existing = await db.venues.find_one({"name": v["name"], "city": v["city"]})
        if existing:
            continue
        doc = {"id": str(uuid.uuid4()), **v, "created_at": datetime.now(timezone.utc)}
        await db.venues.insert_one(doc)

    # Events (seed only once per venue)
    venues_in_db = await db.venues.find({}, {"_id": 0}).to_list(None)
    titles = [
        "Midnight Gold — Grand Opening",
        "Crimson Hour: Open Decks",
        "Velvet Sessions w/ DJ Nyx",
        "Rooftop Reverie",
        "Noche de Luna — Latin Night",
        "Industry Fridays",
        "Private Members Social",
        "Cinematic Supper Series",
    ]
    for i, venue in enumerate(venues_in_db):
        existing = await db.events.find_one({"venue_id": venue["id"]})
        if existing:
            continue
        date = datetime.now(timezone.utc) + timedelta(days=(i + 2), hours=21 - i)
        doc = {
            "id": str(uuid.uuid4()),
            "title": titles[i % len(titles)],
            "venue_id": venue["id"],
            "venue_name": venue["name"],
            "city": venue["city"],
            "date": date,
            "price": [40, 60, 80, 120, 150][i % 5],
            "image_url": _event_image(i),
            "description": f"An exclusive evening at {venue['name']}. Table service available. Dress code enforced.",
            "tags": ["Open Bar", "DJ", "VIP"][: (i % 3) + 1],
            "tickets_sold": 0,
            "created_at": datetime.now(timezone.utc),
        }
        await db.events.insert_one(doc)
