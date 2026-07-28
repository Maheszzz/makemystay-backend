#!/usr/bin/env python3
"""
Script to update avg_rating and review_count in the MySQL database for
the handwritten Top PG and Rental properties.
"""
import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.configs.db_config import get_db

TOP_PROPERTY_UPDATES = [
    # PG Properties
    ("Signature", 4.9, 1250),
    ("Cozy Colive", 4.9, 1180),
    ("Cozy", 4.9, 1180),
    ("Hive Colive", 4.8, 1120),
    ("Hive", 4.8, 1120),
    ("Orchid House", 4.8, 1050),
    ("Orchid", 4.8, 1050),
    ("Cherry Blossom", 4.8, 980),
    ("Nesto HSR", 4.7, 920),
    ("Nesto", 4.7, 920),
    ("Your Shell", 4.8, 880),
    ("Daisy Crest", 4.7, 830),
    ("SC Ladies", 4.8, 790),
    ("Halo Colive", 4.7, 740),
    ("Halo", 4.7, 740),
    ("SLV Cozy", 4.8, 700),
    # Rental Properties
    ("Infinity", 4.9, 1350),
    ("Urban Nivas", 4.9, 1280),
    ("Aster Residency", 4.8, 1220),
    ("Lakshmi Glory", 4.8, 1150),
    ("Lakshmi", 4.8, 1150),
    ("People Tree", 4.8, 1100),
    ("Peepal Tree", 4.8, 1100),
    ("Marshall Elite", 4.9, 1050),
    ("Aster ATS", 4.8, 1000),
    ("Aster", 4.8, 1000),
    ("Green Homes", 4.8, 950),
    ("Tech Homes", 4.7, 900),
    ("Tec Homes", 4.7, 900),
    ("Sky Homes", 4.7, 860),
    ("Marshall Manor", 4.8, 820),
    ("Skyra", 4.7, 780),
    ("Sanchi", 4.7, 740),
    ("Saanchi", 4.7, 740),
    ("Urban Stay", 4.7, 700),
    ("VSS Home", 4.6, 660),
    ("Clomo Colive", 4.6, 620),
    ("Clomo", 4.6, 620),
]

def main():
    db = next(get_db())
    updated_count = 0
    for keyword, rating, rev_count in TOP_PROPERTY_UPDATES:
        sql = text(
            "UPDATE properties SET avg_rating = :rating, review_count = :rev_count "
            "WHERE property_name LIKE :kw AND (review_count < :rev_count OR review_count IS NULL)"
        )
        res = db.execute(sql, {"rating": rating, "rev_count": rev_count, "kw": f"%{keyword}%"})
        if res.rowcount > 0:
            updated_count += res.rowcount
            print(f"Updated {res.rowcount} row(s) matching keyword '{keyword}' -> rating={rating}, reviews={rev_count}")
    db.commit()
    print(f"Done! Total properties updated in database: {updated_count}")

if __name__ == "__main__":
    main()
