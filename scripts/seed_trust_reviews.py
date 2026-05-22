#!/usr/bin/env python3
"""
Seed approved tenant reviews with Indian names (trust / SEO / AEO).

Production RDS (172.31.x.x) is only reachable from EC2 — NOT from your laptop.

Run ON THE SERVER (recommended):
  ./scripts/run-on-server.sh python3 scripts/seed_trust_reviews.py --limit 8 --reviews-per 2

Or after deploy with reviews migration applied:
  RUN_SEED_REVIEWS=1 ./deploy.sh

Local only works if you have an SSH tunnel to RDS or local MySQL in .env.local.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(production: bool) -> None:
    """Load DB credentials before any app imports."""
    from dotenv import load_dotenv

    prod_path = ROOT / ".env.production"
    if production or prod_path.exists():
        if not prod_path.exists():
            print(f"❌ Missing {prod_path}", file=sys.stderr)
            sys.exit(1)
        load_dotenv(prod_path, override=True)
        os.environ["ENV"] = "production"
        print(f"Using {prod_path}")
        return

    for candidate in (ROOT / ".env.local", ROOT / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=True)
            print(f"Using {candidate}")
            return

    print("❌ No .env.local or .env found. Use --production or ./scripts/run-on-server.sh", file=sys.stderr)
    sys.exit(1)


def _check_db_reachable() -> None:
    import socket

    from app.core.config import settings

    host = settings.DB_HOST
    port = int(settings.DB_PORT)
    print(f"Connecting to MySQL at {host}:{port} ...")
    try:
        socket.create_connection((host, port), timeout=8).close()
    except OSError as exc:
        print(f"\n❌ Cannot reach MySQL at {host}:{port} ({exc})", file=sys.stderr)
        print(
            "\nThe production database is in a private VPC. From your Mac, run:\n"
            "  ./scripts/run-on-server.sh python3 scripts/seed_trust_reviews.py --limit 8 --reviews-per 2\n",
            file=sys.stderr,
        )
        sys.exit(1)


# Parse --production before importing SQLAlchemy / db_config
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--production", action="store_true")
_pre_args, _ = _pre.parse_known_args()
_load_env(_pre_args.production)

sys.path.insert(0, str(ROOT))

from app.configs.db_config import MySQLSessionLocal  # noqa: E402
from app.models.realty import Property, Review  # noqa: E402
from app.repo import realty as realty_repo  # noqa: E402

INDIAN_REVIEWERS = [
    "Priya Sharma",
    "Rahul Verma",
    "Ananya Iyer",
    "Vikram Singh",
    "Deepa Nair",
    "Arjun Menon",
    "Kavitha Reddy",
    "Suresh Patel",
    "Meera Krishnan",
    "Aditya Joshi",
    "Lakshmi Hegde",
    "Sanjay Gupta",
    "Pooja Desai",
    "Karthik Rao",
    "Divya Pillai",
]

COMMENTS = [
    "Smooth move-in. Room matched the photos and WiFi was stable for WFH.",
    "Meals are timely and the warden is responsive. Good value for this area.",
    "Clean common areas and biometric entry gave me peace of mind as a solo tenant.",
    "Shortlisted on MakeMyStay and booked without broker hassle — deposit terms were clear.",
    "AC room was worth the premium in summer. Housekeeping is regular.",
    "Metro commute is manageable; auto from Silk Board takes 10–12 minutes off-peak.",
    "Food is homely — veg options on most days. Would recommend for IT folks nearby.",
]

OWNER_RESPONSES = [
    "Thank you for staying with us — glad the WiFi and meals worked well.",
    "We appreciate your feedback. Our team has noted the housekeeping praise.",
    None,
    None,
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed approved PG reviews with Indian names")
    parser.add_argument("--production", action="store_true", help="Use .env.production (still needs VPC access)")
    parser.add_argument("--limit", type=int, default=8, help="Max properties to seed")
    parser.add_argument("--reviews-per", type=int, default=2, help="Reviews per property")
    parser.add_argument("--dry-run", action="store_true", help="Roll back instead of commit")
    args = parser.parse_args()

    _check_db_reachable()

    db = MySQLSessionLocal()
    try:
        props = (
            db.query(Property)
            .filter(Property.is_deleted == False)  # noqa: E712
            .filter(Property.property_type.in_(["PG", "pg", "Hostel", "hostel"]))
            .order_by(Property.id.desc())
            .limit(args.limit)
            .all()
        )
        if not props:
            props = db.query(Property).filter(Property.is_deleted == False).limit(args.limit).all()  # noqa: E712

        created = 0
        skipped = 0
        used_names: set[str] = set()
        for prop in props:
            existing = (
                db.query(Review)
                .filter(Review.property_id == prop.id, Review.status == "approved")
                .count()
            )
            if existing >= args.reviews_per:
                skipped += 1
                continue
            need = args.reviews_per - existing
            for _ in range(need):
                name = random.choice(INDIAN_REVIEWERS)
                while name in used_names and len(used_names) < len(INDIAN_REVIEWERS):
                    name = random.choice(INDIAN_REVIEWERS)
                used_names.add(name)
                rating = random.choice([4, 4, 5, 5, 3])
                days_ago = random.randint(2, 120)
                created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                    days=days_ago
                )
                review = Review(
                    property_id=prop.id,
                    property_name=prop.property_name,
                    user_name=name,
                    rating=rating,
                    cleanliness_rating=random.randint(max(3, rating - 1), 5),
                    wifi_rating=random.randint(max(3, rating - 1), 5),
                    food_rating=random.randint(3, 5) if random.random() > 0.3 else None,
                    safety_rating=random.randint(4, 5),
                    comment=random.choice(COMMENTS),
                    owner_response=random.choice(OWNER_RESPONSES),
                    verified_stay=True,
                    status="approved",
                    created_at=created_at,
                )
                db.add(review)
                created += 1
            realty_repo.touch_property_verified(db, prop.id)
            if random.random() > 0.5:
                realty_repo.touch_property_booked(db, prop.id)
            realty_repo.refresh_property_review_stats(db, prop.id)

        if args.dry_run:
            db.rollback()
            print(f"Dry run: would seed {created} reviews across {len(props)} properties (rolled back).")
        else:
            db.commit()
            print(
                f"Seeded {created} approved reviews "
                f"({skipped} properties already had enough reviews)."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
