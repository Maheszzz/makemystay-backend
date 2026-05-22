#!/usr/bin/env python3
"""
Seed approved tenant reviews with Indian names for trust / SEO / AEO demos.
Run from repo root: python scripts/seed_trust_reviews.py [--limit 8]
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.configs.db_config import MySQLSessionLocal
from app.models.realty import Property, Review
from app.repo import realty as realty_repo

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8, help="Max properties to seed")
    parser.add_argument("--reviews-per", type=int, default=2, help="Reviews per property")
    args = parser.parse_args()

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
        used_names = set()
        for prop in props:
            for i in range(args.reviews_per):
                name = random.choice(INDIAN_REVIEWERS)
                while name in used_names and len(used_names) < len(INDIAN_REVIEWERS):
                    name = random.choice(INDIAN_REVIEWERS)
                used_names.add(name)
                rating = random.choice([4, 4, 5, 5, 3])
                days_ago = random.randint(2, 120)
                created_at = datetime.utcnow() - timedelta(days=days_ago)
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

        db.commit()
        print(f"Seeded {created} approved reviews across {len(props)} properties.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
