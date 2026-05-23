import asyncio
import uuid
from sqlalchemy import text
from app.db.session import SessionLocal
from app.db.models import User, Zone, Role
from app.core.security import hash_pw


# Chinnaswamy stadium approximate zones (lat, lng polygons)
# Each polygon is a small square around the named gate
def _square(lat: float, lng: float, half: float = 0.0003) -> str:
    """Return a WKT POLYGON around (lat, lng) with ~30m half-side."""
    return (
        f"POLYGON(("
        f"{lng - half} {lat - half}, "
        f"{lng + half} {lat - half}, "
        f"{lng + half} {lat + half}, "
        f"{lng - half} {lat + half}, "
        f"{lng - half} {lat - half}"
        f"))"
    )


ZONES = [
    # name, kind, capacity, lat, lng
    ("Gate 1",    "gate",      5000, 12.9795, 77.5990),
    ("Gate 3",    "gate",      5000, 12.9798, 77.5995),
    ("Gate 7",    "gate",      4000, 12.9785, 77.6002),   # the bottleneck
    ("Gate 9",    "gate",      6000, 12.9782, 77.5998),
    ("Gate 11",   "gate",      6000, 12.9780, 77.5992),
    ("Concourse North", "concourse", 12000, 12.9792, 77.5996),
    ("Concourse South", "concourse", 12000, 12.9784, 77.5996),
    ("Exit Ramp East",  "exit",      8000, 12.9789, 77.6005),
    ("Exit Ramp West",  "exit",      8000, 12.9789, 77.5987),
]

USERS = [
    ("commander@sentinel.local", "commander123", Role.admin,     "Ops Commander"),
    ("volunteer1@sentinel.local","volunteer123", Role.volunteer, "Volunteer Alpha"),
    ("volunteer2@sentinel.local","volunteer123", Role.volunteer, "Volunteer Bravo"),
    ("medic1@sentinel.local",    "medic123",     Role.medical,   "Medic Charlie"),
    ("fan@sentinel.local",       "fan123",       Role.fan,       "Test Fan"),
]


async def main() -> None:
    async with SessionLocal() as s:
        # Insert zones — use raw SQL for the geometry constructor
        for name, kind, capacity, lat, lng in ZONES:
            wkt = _square(lat, lng)
            await s.execute(text("""
                INSERT INTO zones (id, name, kind, capacity, geom)
                VALUES (:id, :name, :kind, :capacity, ST_GeomFromText(:wkt, 4326))
                ON CONFLICT (name) DO NOTHING
            """), {
                "id": str(uuid.uuid4()),
                "name": name, "kind": kind, "capacity": capacity, "wkt": wkt,
            })

        # Insert users
        for email, pw, role, name in USERS:
            existing = await s.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": email}
            )
            if existing.first():
                continue
            u = User(
                email=email,
                password_hash=hash_pw(pw),
                role=role,
                full_name=name,
            )
            s.add(u)

        await s.commit()
        print(f"Seeded {len(ZONES)} zones and {len(USERS)} users.")


if __name__ == "__main__":
    asyncio.run(main())
