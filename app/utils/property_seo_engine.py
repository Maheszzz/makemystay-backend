from __future__ import annotations

from typing import Any, Optional

from app.utils.blog_content_engine import blog_links_for_context
from app.utils.property_seo_narrative import build_property_seo_about
from app.utils.seo import canonical_property_path, canonical_property_type, canonical_property_url, money_value


NEARBY_PLACE_HINTS = {
    "koramangala": ["Forum Mall", "Sony World Signal", "St. John's Medical College", "Ejipura"],
    "indiranagar": ["100 Feet Road", "CMH Road", "Indiranagar Metro Station", "Domlur"],
    "whitefield": ["ITPL", "Phoenix Marketcity", "Hope Farm", "Kadugodi Metro Station"],
    "hsr": ["HSR BDA Complex", "Agara Lake", "Outer Ring Road", "Silk Board"],
    "bellandur": ["Outer Ring Road", "Eco Space", "Bellandur Lake", "Sarjapur Road"],
    "btm": ["BTM Layout", "Silk Board", "Bannerghatta Road", "Madiwala"],
    "marathahalli": ["Marathahalli Bridge", "Kundalahalli Gate", "Outer Ring Road", "HAL"],
}


def _clean(value: Optional[Any]) -> str:
    return " ".join(str(value or "").split()).strip()


def _amenities(prop: Any) -> list[dict[str, str]]:
    raw = getattr(prop, "features", None) or []
    if not isinstance(raw, list):
        raw = []
    out: list[dict[str, str]] = []
    for item in raw:
        name = _clean(item)
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": f"{name} is listed as an amenity for {_clean(getattr(prop, 'property_name', None))}.",
            }
        )
    if out:
        return out
    defaults = ["Power backup", "Security", "Water supply"]
    return [
        {
            "name": name,
            "description": f"Confirm {name.lower()} details during the site visit.",
        }
        for name in defaults
    ]


def _nearby_places(prop: Any) -> list[dict[str, str]]:
    location = _clean(getattr(prop, "location", None))
    key = location.lower()
    places: list[str] = []
    for token, hints in NEARBY_PLACE_HINTS.items():
        if token in key:
            places = hints
            break
    if not places:
        city = _clean(getattr(prop, "city", None)) or "Bangalore"
        places = [location or city, f"{city} commute routes", f"{city} schools and clinics"]
    return [{"name": place, "type": "local_landmark"} for place in places[:6]]


def _faq(prop: Any) -> list[dict[str, str]]:
    name = _clean(getattr(prop, "property_name", None)) or "this property"
    location = _clean(getattr(prop, "location", None)) or _clean(getattr(prop, "city", None)) or "Bangalore"
    price = money_value(getattr(prop, "starting_price", None))
    price_answer = (
        f"{name} starts at Rs. {price:,.0f}. Confirm final rent, deposit, and inclusions before booking."
        if price is not None
        else f"Contact MakeMyStay for the latest price and deposit details for {name}."
    )
    return [
        {"question": f"What is the price of {name}?", "answer": price_answer},
        {"question": f"Where is {name} located?", "answer": f"{name} is located in {location}."},
        {
            "question": f"What amenities are available at {name}?",
            "answer": "Key amenities include " + ", ".join(item["name"] for item in _amenities(prop)[:6]) + ".",
        },
        {
            "question": f"How can I visit {name}?",
            "answer": "Use the enquiry or call flow on MakeMyStay and verify availability before visiting.",
        },
    ]


def _review_highlights(prop: Any) -> dict[str, Any]:
    reviews = list(getattr(prop, "reviews", None) or [])
    snippets = []
    for review in reviews[:5]:
        comment = _clean(getattr(review, "comment", None))
        if not comment:
            continue
        snippets.append(
            {
                "rating": getattr(review, "rating", None),
                "user_name": _clean(getattr(review, "user_name", None)),
                "snippet": comment[:220],
                "verified_stay": bool(getattr(review, "verified_stay", False)),
            }
        )
    return {
        "average_rating": float(getattr(prop, "average_rating", 0) or 0),
        "review_count": int(getattr(prop, "review_count", 0) or 0),
        "snippets": snippets,
    }


def _google_maps(prop: Any) -> dict[str, Any]:
    lat = getattr(prop, "latitude", None)
    lng = getattr(prop, "longitude", None)
    map_link = _clean(getattr(prop, "map_link", None))
    query = _clean(getattr(prop, "location", None)) or _clean(getattr(prop, "city", None)) or "Bangalore"
    embed_query = query.replace(" ", "+")
    out = {
        "map_link": map_link or None,
        "search_query": query,
        "embed_query": embed_query,
    }
    if lat is not None and lng is not None:
        out["latitude"] = float(lat)
        out["longitude"] = float(lng)
    return out


def _image_seo(prop: Any) -> list[dict[str, Any]]:
    images = list(getattr(prop, "images", None) or [])
    name = _clean(getattr(prop, "property_name", None)) or "Property"
    location = _clean(getattr(prop, "location", None)) or "Bangalore"
    out = []
    for index, image in enumerate(images, start=1):
        room_hint = "primary view" if bool(getattr(image, "is_primary", False)) else f"gallery image {index}"
        alt = f"{name} {room_hint} in {location}"
        out.append(
            {
                "id": getattr(image, "id", None),
                "url": getattr(image, "image_url", None),
                "alt": alt,
                "title": f"{name} - {location}",
                "caption": f"{name} property photo from MakeMyStay, {location}.",
                "is_primary": bool(getattr(image, "is_primary", False)),
                "sort_order": getattr(image, "sort_order", 0) or 0,
            }
        )
    return out


def _internal_links(site_url: str, prop: Any, related_properties: Optional[list[Any]] = None) -> list[dict[str, str]]:
    category = canonical_property_type(prop)
    location = _clean(getattr(prop, "location", None))
    links = [
        {"label": "All properties", "url": f"{site_url}/properties", "reason": "listing_index"},
        {"label": f"{category.upper()} properties", "url": f"{site_url}/{category if category != 'plot' else 'plots'}", "reason": "category_hub"},
    ]
    if location:
        links.append(
            {
                "label": f"Properties in {location}",
                "url": f"{site_url}/properties?search={location.replace(' ', '+')}",
                "reason": "locality_cluster",
            }
        )
    links.extend(blog_links_for_context(site_url, locality=location, category=category, limit=4))
    for related in (related_properties or [])[:6]:
        links.append(
            {
                "label": _clean(getattr(related, "property_name", None)),
                "url": canonical_property_url(site_url, related),
                "reason": "related_property",
            }
        )
    return [link for link in links if link.get("label")]


def build_property_seo_engine(
    site_url: str,
    prop: Any,
    *,
    related_properties: Optional[list[Any]] = None,
) -> dict[str, Any]:
    name = _clean(getattr(prop, "property_name", None)) or "Property"
    location = _clean(getattr(prop, "location", None)) or _clean(getattr(prop, "city", None)) or "Bangalore"
    category = canonical_property_type(prop)
    ai_description = build_property_seo_about(prop)
    short_description = (
        f"{name} is a verified {category} listing in {location} with structured pricing, amenities, reviews, maps, and related properties on MakeMyStay."
    )
    return {
        "canonical_path": canonical_property_path(prop),
        "canonical_url": canonical_property_url(site_url, prop),
        "ai_description": ai_description,
        "summary": short_description,
        "amenities": _amenities(prop),
        "nearby_places": _nearby_places(prop),
        "faqs": _faq(prop),
        "reviews": _review_highlights(prop),
        "internal_links": _internal_links(site_url, prop, related_properties),
        "google_maps": _google_maps(prop),
        "related_properties": [
            {
                "id": getattr(item, "id", None),
                "name": _clean(getattr(item, "property_name", None)),
                "url": canonical_property_url(site_url, item),
                "location": _clean(getattr(item, "location", None)),
                "starting_price": money_value(getattr(item, "starting_price", None)),
            }
            for item in (related_properties or [])[:6]
        ],
        "image_seo": _image_seo(prop),
    }
