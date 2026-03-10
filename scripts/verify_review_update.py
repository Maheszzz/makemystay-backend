import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.configs.db_config import get_mysql_db
from app.repo import realty as realty_repo
from app.schemas.realty import ReviewResponse

def verify_api_logic():
    db = next(get_mysql_db())
    try:
        # Test retrieval
        reviews = realty_repo.get_reviews_by_property_id(db, 1)
        if not reviews:
            print("No reviews found for property 1")
            return

        review = reviews[0]
        print(f"Database object property_name: {review.property_name}")
        
        # Test schema conversion
        response = ReviewResponse.model_validate(review)
        print(f"Schema response property_name: {response.property_name}")
        
        if response.property_name == "Kings & Queens Coliving":
            print("Verification successful!")
        else:
            print(f"Verification failed: expected 'Kings & Queens Coliving', got '{response.property_name}'")

    finally:
        db.close()

if __name__ == "__main__":
    verify_api_logic()
