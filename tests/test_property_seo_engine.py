from decimal import Decimal
from types import SimpleNamespace

from app.utils.property_seo_engine import build_property_seo_engine


def _property(**overrides):
    base = dict(
        id=1,
        property_name="Sunrise PG",
        location="Koramangala",
        city="bangalore",
        locality="Koramangala",
        property_type="PG",
        listing_type="rent",
        starting_price=Decimal("12000"),
        private_price=None,
        slug="sunrise-pg-koramangala",
        is_available=True,
        features=["WiFi", "Food", "Housekeeping"],
        map_link="https://maps.google.com/?q=Sunrise+PG",
        latitude=Decimal("12.93520000"),
        longitude=Decimal("77.62450000"),
        average_rating=Decimal("4.50"),
        review_count=2,
        description="A managed PG close to commute routes with practical amenities.",
        images=[
            SimpleNamespace(id=1, image_url="https://cdn.example.com/primary.jpg", is_primary=True, sort_order=0),
            SimpleNamespace(id=2, image_url="https://cdn.example.com/room.jpg", is_primary=False, sort_order=1),
        ],
        reviews=[
            SimpleNamespace(rating=5, user_name="Asha", comment="Clean rooms and responsive staff.", verified_stay=True),
            SimpleNamespace(rating=4, user_name="Dev", comment="Good food and easy commute.", verified_stay=False),
        ],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_property_seo_engine_builds_full_property_page_payload():
    prop = _property()
    related = [
        _property(
            id=2,
            property_name="Green Nest PG",
            slug="green-nest-pg-koramangala",
            starting_price=Decimal("13000"),
            images=[],
            reviews=[],
        )
    ]

    payload = build_property_seo_engine("https://example.com", prop, related_properties=related)

    assert payload["canonical_url"] == "https://example.com/properties/pg/sunrise-pg-koramangala"
    assert "Sunrise PG" in payload["ai_description"]
    assert [item["name"] for item in payload["amenities"][:3]] == ["WiFi", "Food", "Housekeeping"]
    assert "Forum Mall" in [place["name"] for place in payload["nearby_places"]]
    assert payload["faqs"][0]["question"] == "What is the price of Sunrise PG?"
    assert payload["reviews"]["snippets"][0]["snippet"] == "Clean rooms and responsive staff."
    assert payload["google_maps"]["latitude"] == 12.9352
    assert payload["image_seo"][0]["alt"] == "Sunrise PG primary view in Koramangala"
    assert payload["related_properties"][0]["url"] == "https://example.com/properties/pg/green-nest-pg-koramangala"
    assert any(link["reason"] == "related_property" for link in payload["internal_links"])


def test_property_seo_engine_uses_defaults_when_amenities_images_and_map_are_sparse():
    prop = _property(features=[], images=[], reviews=[], map_link="", latitude=None, longitude=None)

    payload = build_property_seo_engine("https://example.com", prop)

    assert [item["name"] for item in payload["amenities"]] == ["Power backup", "Security", "Water supply"]
    assert payload["image_seo"] == []
    assert payload["google_maps"]["map_link"] is None
    assert payload["reviews"]["snippets"] == []
    assert any(link["reason"] == "locality_cluster" for link in payload["internal_links"])
