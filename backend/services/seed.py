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


async def _seed_core(db):
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
            "marketing_opt_in": True,
            "marketing_opt_in_at": datetime.now(timezone.utc),
            "city": "Los Angeles",
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
    # only the curated venues — never venues created by tests or owners
    venues_in_db = await db.venues.find({"id": {"$not": {"$regex": "^TEST_"}}, "name": {"$not": {"$regex": "^TEST_"}}}, {"_id": 0}).to_list(None)
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


U = "https://images.unsplash.com/"
PARTNERS = [
    # (name, category, city, member rate, public rate, unit, rating, min level, image, description)
    ("The Sunset Grand", "hotel", "West Hollywood", 650, 820, "night", 4.8, "bronze", U+"photo-1582719508461-905c673771fd?w=1200&q=80",
     "Five-star suites above the Strip with rooftop pool access and late checkout for members."),
    ("Pacific Coast Suites", "hotel", "Santa Monica", 480, 590, "night", 4.6, "bronze", U+"photo-1542314831-068cd1dbfeeb?w=1200&q=80",
     "Oceanfront rooms steps from the pier. Members get a welcome bottle on arrival."),
    ("The Beverly Penthouse Collection", "hotel", "Beverly Hills", 2400, 3200, "night", 4.9, "gold", U+"photo-1631049307264-da0ec9d70304?w=1200&q=80",
     "Private-floor penthouses with butler service, in-suite spa and a dedicated driver."),
    ("Onyx Black Car", "black_car", "Los Angeles", 120, 155, "hour", 4.9, "bronze", U+"photo-1563720223185-11003d516935?w=1200&q=80",
     "Licensed chauffeurs in late-model Escalades and S-Class. Airport and club runs."),
    ("Royal Stretch Limousines", "limo", "Los Angeles", 220, 290, "hour", 4.7, "silver", U+"photo-1647621185394-1d5d2c5c1b06?w=1200&q=80",
     "Stretch limos and party buses for up to 20 guests. Champagne service available."),
    ("Apex Exotic Rentals", "exotic_car", "Beverly Hills", 1800, 2300, "day", 4.8, "silver", U+"photo-1544636331-e26879cd4d9b?w=1200&q=80",
     "Lamborghini, Ferrari and Rolls-Royce rentals delivered to your door, insurance included."),
    ("Hillside Glass Estate", "mansion", "Hollywood Hills", 4500, 6000, "day", 4.8, "silver", U+"photo-1613490493576-7fde63acd811?w=1200&q=80",
     "Infinity pool, city views and a 150-guest permit for private and corporate events."),
    ("Malibu Modern Villa", "mansion", "Malibu", 6800, 9000, "day", 4.9, "gold", U+"photo-1600596542815-ffad4c1539a9?w=1200&q=80",
     "Beachfront villa for launches, birthdays and brand shoots. Security and staff on request."),
    ("Marina del Rey Yacht Charters", "yacht", "Marina del Rey", 900, 1200, "hour", 4.8, "silver", U+"photo-1567899378494-47b22a2ae96a?w=1200&q=80",
     "70 ft motor yacht with captain, crew and DJ booth. Sunset cruises up to 40 guests."),
    ("Newport Superyacht Club", "yacht", "Newport Beach", 2500, 3400, "hour", 4.9, "gold", U+"photo-1605281317010-fe5ffe798166?w=1200&q=80",
     "120 ft superyacht with chef, jacuzzi deck and overnight charters to Catalina."),
    ("SkyLux Private Jets", "jet", "Van Nuys", 6500, 8200, "hour", 4.9, "gold", U+"photo-1540962351504-03099e0a754b?w=1200&q=80",
     "Light to heavy jets from Van Nuys to Vegas, Cabo, Miami and beyond. Catering on board."),
    ("Pacific Heli Tours", "helicopter", "Santa Monica", 1400, 1800, "hour", 4.7, "silver", U+"photo-1608236415053-3691791bbffe?w=1200&q=80",
     "Doors-off city tours, rooftop transfers and sunset flights over Malibu."),
    ("Chef Table at Home", "chef", "Los Angeles", 350, 450, "hour", 4.8, "bronze", U+"photo-1556910103-1c02745aae4d?w=1200&q=80",
     "Private chefs for dinner parties and after-parties. Tasting menus for 2 to 60 guests."),
    ("Sentinel Executive Protection", "security", "Los Angeles", 150, 200, "hour", 4.8, "silver", U+"photo-1541872703-74c5e44368f9?w=1200&q=80",
     "Licensed, discreet security for VIPs, events and nights out. Armed and unarmed teams."),
]

VENUE_LEVELS = {"Club Noire": "gold", "The Golden Hour": "gold", "Velvet Sky Rooftop": "silver", "Riviera Supperclub": "silver"}

EXTRA_VENUES = [
    {"name": "The Vault Members Club", "city": "Beverly Hills", "state": "CA", "category": "Private Members Club",
     "image_url": U+"photo-1470337458703-46ad1756a187?w=1200&q=80", "rating": 4.9, "price_range": "$$$$$",
     "description": "Invitation-only club below Rodeo Drive. Gold members only, no phones on the floor.", "min_level": "gold"},
    {"name": "Obsidian Supper Club", "city": "San Francisco", "state": "CA", "category": "Supperclub",
     "image_url": U+"photo-1414235077428-338989a2e8c0?w=1200&q=80", "rating": 4.8, "price_range": "$$$$",
     "description": "Eight-course chef's counter followed by a jazz and house lounge.", "min_level": "silver"},
]


ARTICLES = [
    {"title": "After Midnight: LA's Five Most Exclusive Rooms", "category": "nightlife",
     "cover_image": "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80",
     "summary": "Where the industry goes when the velvet rope closes.",
     "body": "Los Angeles never really sleeps; it just moves behind unmarked doors.\n\nFrom rooftop lounges in West Hollywood to supper clubs in Santa Monica, the city's best nights now happen in smaller, members-first rooms where the guest list matters more than the line outside.\n\nOur picks this month lean intimate: candle-lit booths, resident DJs and bartenders who remember your order. Book a table early, dress the part, and let your promoter handle the door."},
    {"title": "The Weekend Escape: Palm Springs in 48 Hours", "category": "travel",
     "cover_image": "https://images.unsplash.com/photo-1540541338287-41700207dee6?w=1400&q=80",
     "summary": "Desert sunsets, poolside bottle service and mid-century glamour.",
     "body": "Two hours from LA, Palm Springs trades neon for starlight.\n\nCheck in Friday afternoon, claim a cabana by three, and catch golden hour from the hills. Saturday belongs to brunch, vintage shopping and a long poolside session. Close the weekend with a private dinner under the palms.\n\nMembers can book black car transfers and villa stays directly in the app."},
    {"title": "Living Large: Yacht Season Starts Now", "category": "luxury",
     "cover_image": "https://images.unsplash.com/photo-1567899378494-47b22a2ae96a?w=1400&q=80",
     "summary": "How to plan the perfect private charter on the California coast.",
     "body": "Nothing says celebration like leaving the dock at sunset.\n\nThe best charters start with the right size boat: 40 guests is the sweet spot for birthdays and brand events. Add a DJ, a raw bar and a chauffeur to meet you at the marina.\n\nRequest a charter in Nocturne Luxe and our team handles the rest."},
]


async def _seed_partners_and_articles(db):
    now = datetime.now(timezone.utc)
    for (name, cat, city, rate, public, unit, rating, lvl, img, desc) in PARTNERS:
        await db.partners.update_one(
            {"name": name},
            {"$set": {"category": cat, "city": city, "base_price": rate, "public_price": public, "price_unit": unit,
                      "rating": rating, "min_level": lvl, "image_url": img, "description": desc},
             "$setOnInsert": {"id": str(uuid.uuid4()), "name": name, "created_at": now}},
            upsert=True,
        )
    await db.partners.delete_many({"name": {"$in": ["Newport Luxe Yachts", "Marina del Rey Yacht Club Charters"]}})
    for i, a in enumerate(ARTICLES):
        if not await db.articles.find_one({"title": a["title"]}):
            await db.articles.insert_one({
                "id": str(uuid.uuid4()), **a, "published": True,
                "created_at": now - timedelta(days=i),
            })


async def _apply_levels(db):
    for v in EXTRA_VENUES:
        if not await db.venues.find_one({"name": v["name"]}):
            await db.venues.insert_one({"id": str(uuid.uuid4()), **v, "created_at": datetime.now(timezone.utc)})
    for name, lvl in VENUE_LEVELS.items():
        await db.venues.update_one({"name": name}, {"$set": {"min_level": lvl}})
    await db.venues.update_many({"min_level": {"$exists": False}}, {"$set": {"min_level": "bronze"}})
    async for v in db.venues.find({}, {"_id": 0, "id": 1, "min_level": 1}):
        await db.events.update_many({"venue_id": v["id"], "min_level": {"$exists": False}}, {"$set": {"min_level": v["min_level"]}})
    await db.users.update_many({"level": {"$exists": False}}, {"$set": {"level": "bronze"}})


async def _apply_host_features(db):
    from server import make_tables
    owner = await db.users.find_one({"email": "venue@nocturne.app"}, {"_id": 0, "id": 1})
    if owner:
        await db.venues.update_many({"name": {"$in": ["Mirage Lounge", "Club Noire", "Harbor House", "The Ember Room"]}},
                                    {"$set": {"owner_id": owner["id"]}})
    async for e in db.events.find({"tables": {"$exists": False}}, {"_id": 0}):
        await db.events.update_one({"id": e["id"]}, {"$set": {
            "tables": make_tables(max(300.0, e["price"] * 10), e.get("min_level", "bronze")), "has_tables": True,
            "capacity": 150, "approval_required": False, "plus_one_limit": 3, "guest_list_visible": True,
        }})
    # Demo: one approval-only event (Industry Fridays) and one near sold out event (Rooftop Reverie)
    await db.events.update_many({"title": "Industry Fridays"}, {"$set": {"approval_required": True}})
    await db.events.update_many({"title": "Rooftop Reverie", "capacity": 150}, {"$set": {"capacity": 2}})


PERKS = [
    ("Velvet Sky Rooftop", "Complimentary welcome cocktail", "One signature cocktail on arrival, any night.", "drinks", "bronze", "NOCWELCOME", "photo-1514933651103-005eec06c04b"),
    ("Onyx Black Car", "15% off airport transfers", "LAX, BUR and SNA runs in an Escalade or S-Class.", "transport", "bronze", "ONYX15", "photo-1563720223185-11003d516935"),
    ("Harbor House", "Chef's tasting for 2 at 25% off", "Seven-course coastal tasting menu, Sunday to Thursday.", "dining", "bronze", "HARBOR25", "photo-1414235077428-338989a2e8c0"),
    ("Mirage Lounge", "Skip the line + free entry before 11pm", "Show your code at the door.", "nightlife", "silver", "MIRAGEVIP", "photo-1630395822970-acd6a691d97e"),
    ("The Sunset Grand", "Suite upgrade + late checkout", "Subject to availability, any weekend stay.", "hotels", "silver", "SUNSETUP", "photo-1582719508461-905c673771fd"),
    ("Apex Exotic Rentals", "$300 off your first exotic rental", "Lamborghini, Ferrari or Rolls-Royce, 24h minimum.", "cars", "silver", "APEX300", "photo-1544636331-e26879cd4d9b"),
    ("Club Noire", "Complimentary bottle with any VIP table", "One premium bottle on the house.", "nightlife", "gold", "NOIREGOLD", "photo-1545128485-c400e7702796"),
    ("SkyLux Private Jets", "Free empty-leg upgrade", "First access to empty legs at 50% off.", "travel", "gold", "SKYLUXGOLD", "photo-1540962351504-03099e0a754b"),
    ("Newport Superyacht Club", "Free extra hour on any charter", "Plus champagne service for your group.", "yachts", "gold", "YACHTHOUR", "photo-1605281317010-fe5ffe798166"),
]


async def _seed_perks(db):
    for (partner, title, desc, cat, lvl, code, img) in PERKS:
        await db.perks.update_one({"code": code}, {"$set": {
            "partner_name": partner, "title": title, "description": desc, "category": cat, "min_level": lvl,
            "image_url": U + img + "?w=900&q=80"}, "$setOnInsert": {"id": str(uuid.uuid4()), "code": code}}, upsert=True)


async def seed_all(db):
    await _seed_perks(db)
    await _seed_partners_and_articles(db)
    await _seed_core(db)
    await _apply_levels(db)
    await _apply_host_features(db)
