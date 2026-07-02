from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.utils.seo import canonical_property_url, public_url, safe_slug, truncate_text


@dataclass(frozen=True)
class LocationSeed:
    name: str
    kind: str
    city: str
    aliases: tuple[str, ...]
    nearby_areas: tuple[str, ...]
    tech_parks: tuple[str, ...]
    metro: tuple[str, ...]
    bus_stops: tuple[str, ...]
    schools: tuple[str, ...]
    hospitals: tuple[str, ...]
    restaurants: tuple[str, ...]
    shopping: tuple[str, ...]
    gyms: tuple[str, ...]
    parks: tuple[str, ...]
    safety: str
    nightlife: str
    cost_of_living: str
    rental_trends: str
    popular_property_types: tuple[str, ...]
    map_query: str


LOCATION_SEEDS: tuple[LocationSeed, ...] = (
    LocationSeed(
        name="Bellandur",
        kind="locality",
        city="Bangalore",
        aliases=("bellandur",),
        nearby_areas=("Kadubeesanahalli", "Marathahalli", "HSR Layout", "Sarjapur Road"),
        tech_parks=("RMZ Ecospace", "Embassy Tech Village", "Cessna Business Park"),
        metro=("Bellandur Road railway station", "Kadubeesanahalli upcoming metro corridor"),
        bus_stops=("Bellandur Gate", "Eco Space Bus Stop", "Devarabisanahalli"),
        schools=("New Horizon Gurukul", "Gear Innovative International School"),
        hospitals=("Sakra World Hospital", "Manipal Hospital Sarjapur Road"),
        restaurants=("Big Pitcher", "Asha Tiffins", "The Fisherman's Wharf"),
        shopping=("Central Mall Bellandur", "Soul Space Spirit Central"),
        gyms=("Cult Bellandur", "Gold's Gym Bellandur"),
        parks=("Bellandur Lake trail", "Kaikondrahalli Lake"),
        safety="Busy ORR stretches are active late, while inner residential streets are best checked during site visits.",
        nightlife="Bellandur has pubs and casual dining around ORR, Sarjapur Road, and nearby Marathahalli.",
        cost_of_living="Mid to premium for PGs and managed rentals because of ORR tech-park demand.",
        rental_trends="Demand is strongest for furnished PG rooms, coliving beds, and compact 1 BHK homes near ORR offices.",
        popular_property_types=("PG", "Coliving", "1 BHK", "2 BHK"),
        map_query="Bellandur Bangalore",
    ),
    LocationSeed(
        name="Marathahalli",
        kind="locality",
        city="Bangalore",
        aliases=("marathahalli",),
        nearby_areas=("Kundalahalli", "Brookefield", "Bellandur", "Whitefield"),
        tech_parks=("Cessna Business Park", "Embassy Tech Village", "ITPL"),
        metro=("Kundalahalli Metro Station", "Kadubeesanahalli metro corridor"),
        bus_stops=("Marathahalli Bridge", "Kalamandir", "Multiplex Marathahalli"),
        schools=("Vagdevi Vilas School", "Ryan International School Kundalahalli"),
        hospitals=("Sankara Eye Hospital", "Yashomati Hospital"),
        restaurants=("Absolute Barbecues", "Nandhana Palace", "A2B Marathahalli"),
        shopping=("Brookefield Mall", "Brand Factory Marathahalli"),
        gyms=("Cult Marathahalli", "Snap Fitness"),
        parks=("Chinnappanahalli Lake Park", "AECS Layout parks"),
        safety="Main roads remain active through the evening; compare lane lighting and access control for each property.",
        nightlife="Casual restaurants, lounges, and late food options cluster near Marathahalli Bridge and Brookefield.",
        cost_of_living="Balanced pricing with many PG and shared options for ORR and Whitefield commuters.",
        rental_trends="PG and coliving inventory moves quickly when pricing includes food, Wi-Fi, and housekeeping.",
        popular_property_types=("PG", "Coliving", "1 BHK", "Rental Homes"),
        map_query="Marathahalli Bangalore",
    ),
    LocationSeed(
        name="Whitefield",
        kind="locality",
        city="Bangalore",
        aliases=("whitefield",),
        nearby_areas=("ITPL", "Brookefield", "Kadugodi", "Varthur"),
        tech_parks=("ITPL", "Brigade Tech Park", "GR Tech Park"),
        metro=("Whitefield Kadugodi Metro Station", "Hopefarm Channasandra Metro Station"),
        bus_stops=("ITPL Bus Stop", "Hope Farm", "Whitefield TTMC"),
        schools=("Vydehi School of Excellence", "The Deens Academy"),
        hospitals=("Vydehi Hospital", "Manipal Hospital Whitefield"),
        restaurants=("Windmills Craftworks", "Cafe Noir", "MTR Whitefield"),
        shopping=("Phoenix Marketcity", "Forum Shantiniketan", "Park Square Mall"),
        gyms=("Cult Whitefield", "Gold's Gym Whitefield"),
        parks=("Inner Circle Municipal Park", "Sheelavanthakere Lake"),
        safety="Gated communities and managed stays are common; verify commute after dark for interior lanes.",
        nightlife="Whitefield offers breweries, mall dining, and hotel lounges around ITPL and EPIP Zone.",
        cost_of_living="Wide range, from affordable PG beds to premium apartments near metro and tech parks.",
        rental_trends="Metro access has increased demand for managed PGs, 1 BHK flats, and family rentals.",
        popular_property_types=("PG", "Coliving", "1 BHK", "2 BHK"),
        map_query="Whitefield Bangalore",
    ),
    LocationSeed(
        name="Kadubeesanahalli",
        kind="locality",
        city="Bangalore",
        aliases=("kadubeesanahalli",),
        nearby_areas=("Bellandur", "Panathur", "Marathahalli", "Devarabisanahalli"),
        tech_parks=("Embassy Tech Village", "RMZ Ecospace", "Cessna Business Park"),
        metro=("Kadubeesanahalli metro corridor", "Bellandur Road railway station"),
        bus_stops=("Kadubeesanahalli", "New Horizon College", "Devarabisanahalli"),
        schools=("New Horizon Gurukul", "Orchids The International School Panathur"),
        hospitals=("Sakra World Hospital", "Cloudnine Bellandur"),
        restaurants=("Asha Tiffins", "Rameshwaram Cafe Brookefield", "Truffles Bellandur"),
        shopping=("Soul Space Spirit Central", "Brookefield Mall"),
        gyms=("Cult Kadubeesanahalli", "Anytime Fitness Bellandur"),
        parks=("Panathur Lake", "Bellandur Lake trail"),
        safety="Strong office traffic improves activity on main roads; internal access roads vary by building.",
        nightlife="Dining and pub options are close in Bellandur, Marathahalli, and Brookefield.",
        cost_of_living="Premium for walkable ORR access; shared PG rooms help manage monthly costs.",
        rental_trends="Most searches focus on PGs and coliving within short commute distance of ETV and Ecospace.",
        popular_property_types=("PG", "Coliving", "1 BHK"),
        map_query="Kadubeesanahalli Bangalore",
    ),
    LocationSeed(
        name="HSR Layout",
        kind="locality",
        city="Bangalore",
        aliases=("hsr-layout", "hsr"),
        nearby_areas=("Koramangala", "Bellandur", "BTM Layout", "Sarjapur Road"),
        tech_parks=("RMZ Ecospace", "Embassy Tech Village", "Global Technology Park"),
        metro=("Silk Board metro interchange", "HSR metro corridor"),
        bus_stops=("HSR BDA Complex", "Agara", "Silk Board"),
        schools=("National Public School HSR", "JSS Public School"),
        hospitals=("Narayana Multispeciality Hospital HSR", "Greenview Medical Center"),
        restaurants=("Broadway", "Here & Now", "Asha Tiffins HSR"),
        shopping=("HSR BDA Complex", "Market Square HSR"),
        gyms=("Cult HSR", "Multifit HSR"),
        parks=("Agara Lake", "HSR Sector parks"),
        safety="Residential sectors are generally active; verify building security and parking before finalizing.",
        nightlife="HSR has cafes, pubs, and late dining with easy access to Koramangala.",
        cost_of_living="Mid to premium because of strong residential demand and ORR connectivity.",
        rental_trends="1 BHK, 2 BHK, PG, and coliving demand stays high among tech and startup workers.",
        popular_property_types=("PG", "Coliving", "1 BHK", "Rental Homes"),
        map_query="HSR Layout Bangalore",
    ),
    LocationSeed(
        name="Koramangala",
        kind="locality",
        city="Bangalore",
        aliases=("koramangala",),
        nearby_areas=("HSR Layout", "BTM Layout", "Indiranagar", "Ejipura"),
        tech_parks=("Global Technology Park", "Embassy GolfLinks", "RMZ Ecospace"),
        metro=("Silk Board metro interchange", "Mahatma Gandhi Road metro via commute"),
        bus_stops=("Sony World Signal", "Koramangala BDA Complex", "Forum Mall"),
        schools=("Bethany High", "St. Francis High School"),
        hospitals=("St. John's Medical College Hospital", "Apollo Spectra Koramangala"),
        restaurants=("Truffles", "Meghana Foods", "A Hole Lotta Love Cafe"),
        shopping=("Nexus Koramangala", "Raheja Arcade"),
        gyms=("Cult Koramangala", "Gold's Gym Koramangala"),
        parks=("BBMP Park 5th Block", "Lakshmi Devi Park"),
        safety="High footfall areas are active late; quieter blocks should be inspected by commute time.",
        nightlife="One of Bangalore's strongest nightlife clusters with pubs, cafes, and live events.",
        cost_of_living="Premium for central blocks; shared PGs and coliving reduce upfront deposits.",
        rental_trends="Demand stays broad across PG, coliving, 1 BHK, and premium rental homes.",
        popular_property_types=("PG", "Coliving", "1 BHK", "Rental Homes"),
        map_query="Koramangala Bangalore",
    ),
    LocationSeed(
        name="Electronic City",
        kind="locality",
        city="Bangalore",
        aliases=("electronic-city",),
        nearby_areas=("Hosa Road", "Bommasandra", "Begur", "Singasandra"),
        tech_parks=("Electronic City Phase 1", "Electronic City Phase 2", "Infosys Campus"),
        metro=("Electronic City metro corridor", "Bommasandra metro corridor"),
        bus_stops=("Electronic City Wipro Gate", "Infosys Gate", "Konappana Agrahara"),
        schools=("Treamis World School", "Ebenezer International School"),
        hospitals=("Narayana Institute of Cardiac Sciences", "Springleaf Hospital"),
        restaurants=("46 Ounces", "Barbeque Nation Electronic City", "Sreeraj Lassi Bar"),
        shopping=("M5 Ecity Mall", "Village Hypermarket"),
        gyms=("Cult Electronic City", "Gold's Gym Electronic City"),
        parks=("Neeladri Nagar parks", "Celebrity Park"),
        safety="Township and campus-adjacent areas are active; confirm last-mile commute for late shifts.",
        nightlife="Nightlife is practical and local, with breweries and restaurants around Neeladri Road.",
        cost_of_living="Usually more affordable than central ORR while offering strong tech-campus access.",
        rental_trends="PGs, coliving, and 1 BHK homes perform well for campus-based employees.",
        popular_property_types=("PG", "Coliving", "1 BHK", "2 BHK"),
        map_query="Electronic City Bangalore",
    ),
    LocationSeed(
        name="Ecospace",
        kind="tech_park",
        city="Bangalore",
        aliases=("ecospace", "rmz-ecospace"),
        nearby_areas=("Bellandur", "Kadubeesanahalli", "Marathahalli", "Panathur"),
        tech_parks=("RMZ Ecospace", "Embassy Tech Village", "Cessna Business Park"),
        metro=("Kadubeesanahalli metro corridor", "Bellandur Road railway station"),
        bus_stops=("Eco Space Bus Stop", "Bellandur Gate", "Devarabisanahalli"),
        schools=("New Horizon Gurukul", "Gear Innovative International School"),
        hospitals=("Sakra World Hospital", "Cloudnine Bellandur"),
        restaurants=("Big Pitcher", "Asha Tiffins", "The Fisherman's Wharf"),
        shopping=("Central Mall Bellandur", "Soul Space Spirit Central"),
        gyms=("Cult Bellandur", "Gold's Gym Bellandur"),
        parks=("Bellandur Lake trail", "Kaikondrahalli Lake"),
        safety="Office corridors are active late; verify walking routes from each stay to the tech park.",
        nightlife="Bellandur and Marathahalli provide nearby after-work dining and pub options.",
        cost_of_living="Premium for walk-to-work inventory; better value appears slightly inside Bellandur and Panathur.",
        rental_trends="PG near Ecospace and coliving near Ecospace are high-intent searches with strong weekday demand.",
        popular_property_types=("PG", "Coliving", "1 BHK"),
        map_query="RMZ Ecospace Bangalore",
    ),
    LocationSeed(
        name="Embassy Tech Village",
        kind="tech_park",
        city="Bangalore",
        aliases=("embassy-tech-village", "etv"),
        nearby_areas=("Bellandur", "Kadubeesanahalli", "Devarabisanahalli", "Marathahalli"),
        tech_parks=("Embassy Tech Village", "RMZ Ecospace", "Cessna Business Park"),
        metro=("Kadubeesanahalli metro corridor", "Bellandur Road railway station"),
        bus_stops=("Embassy Tech Village", "New Horizon College", "Kadubeesanahalli"),
        schools=("New Horizon Gurukul", "Orchids The International School Panathur"),
        hospitals=("Sakra World Hospital", "Manipal Hospital Sarjapur Road"),
        restaurants=("Asha Tiffins", "Truffles Bellandur", "Big Pitcher"),
        shopping=("Soul Space Spirit Central", "Brookefield Mall"),
        gyms=("Cult Kadubeesanahalli", "Anytime Fitness Bellandur"),
        parks=("Panathur Lake", "Bellandur Lake trail"),
        safety="Choose properties with clear access, visitor controls, and well-lit routes for late office exits.",
        nightlife="Nearby Bellandur and Marathahalli cover most after-work dining and social options.",
        cost_of_living="High for the closest ORR inventory; shared accommodation is common for budget control.",
        rental_trends="Search demand clusters around PG near Embassy Tech Village and coliving near ETV.",
        popular_property_types=("PG", "Coliving", "1 BHK"),
        map_query="Embassy Tech Village Bangalore",
    ),
    LocationSeed(
        name="RMZ Ecosystem",
        kind="tech_park",
        city="Bangalore",
        aliases=("rmz-ecosystem",),
        nearby_areas=("Thanisandra", "Nagavara", "Manyata Tech Park", "Hebbal"),
        tech_parks=("RMZ Ecosystem", "Manyata Tech Park", "Kirloskar Business Park"),
        metro=("Nagavara metro corridor", "Hebbal railway station"),
        bus_stops=("Nagavara Junction", "Thanisandra Main Road", "Manyata Tech Park Gate"),
        schools=("Vidyashilp Academy", "Rashtrotthana Vidya Kendra"),
        hospitals=("Aster CMI Hospital", "Regal Hospital"),
        restaurants=("Elements Mall dining", "Byg Brewski Hennur", "Nandhana Palace"),
        shopping=("Elements Mall", "Esteem Mall"),
        gyms=("Cult Thanisandra", "Gold's Gym Hennur"),
        parks=("Nagavara Lake", "Hebbal Lake"),
        safety="Main corridors are active; check last-mile access around Thanisandra and Nagavara.",
        nightlife="North Bangalore has growing dining, brewery, and mall-led nightlife options.",
        cost_of_living="Mid to premium depending on proximity to business parks and gated communities.",
        rental_trends="PG and rental-home demand is rising with North Bangalore office growth.",
        popular_property_types=("PG", "Coliving", "1 BHK", "Rental Homes"),
        map_query="RMZ Ecosystem Bangalore",
    ),
    LocationSeed(
        name="Bagmane Tech Park",
        kind="tech_park",
        city="Bangalore",
        aliases=("bagmane-tech-park",),
        nearby_areas=("CV Raman Nagar", "Indiranagar", "Baiyappanahalli", "Kaggadasapura"),
        tech_parks=("Bagmane Tech Park", "Bagmane Constellation Business Park", "Embassy GolfLinks"),
        metro=("Baiyappanahalli Metro Station", "Indiranagar Metro Station"),
        bus_stops=("Bagmane Tech Park", "LRDE", "CV Raman Nagar"),
        schools=("National Centre for Excellence", "Kendriya Vidyalaya DRDO"),
        hospitals=("Manipal Hospital Old Airport Road", "Chinmaya Mission Hospital"),
        restaurants=("Indiranagar 100 Feet Road", "Toit", "CTR Indiranagar"),
        shopping=("Gopalan Signature Mall", "Indiranagar stores"),
        gyms=("Cult Indiranagar", "Snap Fitness CV Raman Nagar"),
        parks=("Bagmane Lake", "DRDO Township parks"),
        safety="Office and defense-area roads are structured; confirm visitor access and evening connectivity.",
        nightlife="Indiranagar is close for Bangalore's strongest pub, cafe, and restaurant options.",
        cost_of_living="Premium near Indiranagar, more balanced around CV Raman Nagar and Kaggadasapura.",
        rental_trends="Strong demand for PGs and 1 BHK homes among East Bangalore office workers.",
        popular_property_types=("PG", "Coliving", "1 BHK", "2 BHK"),
        map_query="Bagmane Tech Park Bangalore",
    ),
    LocationSeed(
        name="Manyata Tech Park",
        kind="tech_park",
        city="Bangalore",
        aliases=("manyata-tech-park",),
        nearby_areas=("Nagavara", "Hebbal", "Thanisandra", "Hennur"),
        tech_parks=("Manyata Tech Park", "RMZ Ecosystem", "Kirloskar Business Park"),
        metro=("Nagavara metro corridor", "Hebbal railway station"),
        bus_stops=("Manyata Tech Park Gate", "Nagavara Junction", "Hebbal Kempapura"),
        schools=("Vidyashilp Academy", "Sindhi High School Hebbal"),
        hospitals=("Aster CMI Hospital", "Bangalore Baptist Hospital"),
        restaurants=("Elements Mall dining", "Byg Brewski Hennur", "Nagarjuna Hebbal"),
        shopping=("Elements Mall", "Esteem Mall", "Orion East via commute"),
        gyms=("Cult Manyata", "Gold's Gym Hennur"),
        parks=("Nagavara Lake", "Hebbal Lake"),
        safety="Managed stays near the park should be checked for access control, transport, and late-shift entry.",
        nightlife="North Bangalore offers mall dining, breweries, and airport-road hotel lounges.",
        cost_of_living="Mid to premium, with lower-cost options further inside Thanisandra and Hennur.",
        rental_trends="PG near Manyata Tech Park is a durable search cluster for freshers and office relocations.",
        popular_property_types=("PG", "Coliving", "1 BHK", "Rental Homes"),
        map_query="Manyata Tech Park Bangalore",
    ),
)


SEARCH_INTENTS: dict[str, dict[str, str]] = {
    "pg": {"label": "PG", "plural": "PGs", "property_type": "PG"},
    "coliving": {"label": "Coliving", "plural": "Coliving spaces", "property_type": "PG"},
    "1-bhk": {"label": "1 BHK", "plural": "1 BHK homes", "property_type": "1BHK"},
    "rental-homes": {"label": "Rental Homes", "plural": "Rental homes", "property_type": "rent"},
}


POPULAR_BANGALORE_PATHS: tuple[tuple[str, str], ...] = (
    ("pg", "bellandur"),
    ("pg", "marathahalli"),
    ("pg", "whitefield"),
    ("pg", "kadubeesanahalli"),
    ("pg", "ecospace"),
    ("pg", "embassy-tech-village"),
    ("pg", "rmz-ecosystem"),
    ("pg", "bagmane-tech-park"),
    ("pg", "manyata-tech-park"),
    ("pg", "hsr-layout"),
    ("pg", "koramangala"),
    ("pg", "electronic-city"),
    ("coliving", "bangalore"),
    ("1-bhk", "bellandur"),
    ("rental-homes", "bangalore"),
)


def _clean(value: Optional[Any]) -> str:
    return " ".join(str(value or "").split()).strip()


def location_path(intent: str, slug: str) -> str:
    return f"/locations/{safe_slug(intent)}/{safe_slug(slug)}"


def _bangalore_seed() -> LocationSeed:
    return LocationSeed(
        name="Bangalore",
        kind="city",
        city="Bangalore",
        aliases=("bangalore", "bengaluru"),
        nearby_areas=("Bellandur", "Whitefield", "HSR Layout", "Koramangala", "Electronic City", "Manyata Tech Park"),
        tech_parks=("RMZ Ecospace", "Embassy Tech Village", "Manyata Tech Park", "Bagmane Tech Park", "ITPL"),
        metro=("Purple Line", "Green Line", "Yellow Line corridor", "Blue Line airport corridor"),
        bus_stops=("Majestic", "Silk Board", "Marathahalli Bridge", "Hebbal", "KR Puram"),
        schools=("National Public School", "Delhi Public School", "The Deens Academy"),
        hospitals=("Manipal Hospital", "Aster CMI Hospital", "Sakra World Hospital", "Narayana Health"),
        restaurants=("Indiranagar restaurants", "Koramangala cafes", "Whitefield breweries"),
        shopping=("Phoenix Marketcity", "Nexus Koramangala", "Orion Mall", "Forum Shantiniketan"),
        gyms=("Cult.fit centers", "Gold's Gym", "Anytime Fitness"),
        parks=("Cubbon Park", "Lalbagh", "Agara Lake", "Hebbal Lake"),
        safety="Safety varies by micro-market, so shortlist properties with lighting, access control, and reliable transport.",
        nightlife="Bangalore has strong nightlife clusters in Indiranagar, Koramangala, HSR, Whitefield, and North Bangalore.",
        cost_of_living="Budgets vary widely by commute, furnishing, deposit, and whether food and utilities are included.",
        rental_trends="Demand is strongest around tech corridors, metro access, and managed accommodation clusters.",
        popular_property_types=("PG", "Coliving", "1 BHK", "2 BHK", "Rental Homes"),
        map_query="Bangalore Karnataka",
    )


def get_location_seed(slug: str) -> Optional[LocationSeed]:
    slug = safe_slug(slug)
    if slug in ("bangalore", "bengaluru"):
        return _bangalore_seed()
    for seed in LOCATION_SEEDS:
        if slug == safe_slug(seed.name) or slug in {safe_slug(alias) for alias in seed.aliases}:
            return seed
    return None


def iter_location_pages() -> Iterable[dict[str, str]]:
    for intent, slug in POPULAR_BANGALORE_PATHS:
        seed = get_location_seed(slug)
        if seed and intent in SEARCH_INTENTS:
            yield {"intent": intent, "slug": safe_slug(slug), "path": location_path(intent, slug), "name": seed.name}


def find_location_page(path: str) -> Optional[dict[str, str]]:
    parts = [part for part in path.split("/") if part]
    if len(parts) != 3 or parts[0] != "locations":
        return None
    intent, slug = safe_slug(parts[1]), safe_slug(parts[2])
    if intent not in SEARCH_INTENTS or not get_location_seed(slug):
        return None
    return {"intent": intent, "slug": slug, "path": location_path(intent, slug)}


def build_location_title(intent: str, seed: LocationSeed) -> str:
    label = SEARCH_INTENTS[intent]["label"]
    preposition = "near" if seed.kind == "tech_park" else "in"
    return truncate_text(f"{label} {preposition} {seed.name} | Verified Stays on MakeMyStay", 70)


def build_location_description(intent: str, seed: LocationSeed) -> str:
    plural = SEARCH_INTENTS[intent]["plural"]
    preposition = "near" if seed.kind == "tech_park" else "in"
    return truncate_text(
        f"Find verified {plural} {preposition} {seed.name}, {seed.city} with rents, commute details, nearby tech parks, metro, safety, amenities, maps, FAQs, and local property options.",
        160,
    )


def _section(title: str, items: Iterable[str], summary: str = "") -> dict[str, Any]:
    return {"title": title, "summary": summary, "items": [{"name": item} for item in items if item]}


def _related_locality_links(site_url: str, seed: LocationSeed, intent: str) -> list[dict[str, str]]:
    links = []
    for area in seed.nearby_areas:
        area_seed = get_location_seed(area)
        slug = safe_slug(area)
        if area_seed:
            links.append({"label": f"{SEARCH_INTENTS[intent]['label']} in {area_seed.name}", "url": public_url(site_url, location_path(intent, slug)), "reason": "nearby_area"})
        else:
            links.append({"label": f"Properties in {area}", "url": public_url(site_url, f"/properties?search={area.replace(' ', '+')}"), "reason": "nearby_area"})
    return links[:8]


def _popular_search_links(site_url: str, seed: LocationSeed) -> list[dict[str, str]]:
    links = []
    for intent, meta in SEARCH_INTENTS.items():
        links.append(
            {
                "label": f"{meta['label']} {'near' if seed.kind == 'tech_park' else 'in'} {seed.name}",
                "url": public_url(site_url, location_path(intent, safe_slug(seed.name))),
                "reason": "popular_search",
            }
        )
    return links


def build_location_page(
    site_url: str,
    intent: str,
    slug: str,
    *,
    featured_properties: Optional[list[Any]] = None,
    blog_links: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    seed = get_location_seed(slug)
    if not seed or intent not in SEARCH_INTENTS:
        raise ValueError("Unknown location page")
    meta = SEARCH_INTENTS[intent]
    preposition = "near" if seed.kind == "tech_park" else "in"
    path = location_path(intent, slug)
    properties = featured_properties or []
    property_links = [
        {
            "label": _clean(getattr(prop, "property_name", None)),
            "url": canonical_property_url(site_url, prop),
            "reason": "featured_property",
        }
        for prop in properties[:8]
        if _clean(getattr(prop, "property_name", None))
    ]
    fallback_blogs = [
        {"label": f"How to choose a PG {preposition} {seed.name}", "url": public_url(site_url, f"/blog/pg-in-{safe_slug(seed.name)}-guide"), "reason": "blog"},
        {"label": f"Rental checklist for {seed.name}", "url": public_url(site_url, f"/blog/{safe_slug(seed.name)}-rental-checklist"), "reason": "blog"},
    ]
    internal_links = (
        property_links
        + _related_locality_links(site_url, seed, intent)
        + [{"label": f"Properties {preposition} {seed.name}", "url": public_url(site_url, f"/properties?search={seed.name.replace(' ', '+')}"), "reason": "property_search"}]
        + [{"label": f"Tech parks near {seed.name}", "url": public_url(site_url, f"/properties?search={'+'.join(seed.tech_parks[:1]).replace(' ', '+')}"), "reason": "nearby_tech_park"}]
        + (blog_links or fallback_blogs)
        + _popular_search_links(site_url, seed)
        + [{"label": f"Rental homes in {seed.city}", "url": public_url(site_url, location_path("rental-homes", safe_slug(seed.city))), "reason": "related_city"}]
    )
    faqs = [
        {"question": f"How do I find {meta['label']} {preposition} {seed.name}?", "answer": f"Use MakeMyStay to compare verified {meta['plural'].lower()} {preposition} {seed.name}, shortlist by budget and commute, and confirm availability before visiting."},
        {"question": f"What is the cost of living {preposition} {seed.name}?", "answer": seed.cost_of_living},
        {"question": f"Which tech parks are close to {seed.name}?", "answer": "Nearby tech parks include " + ", ".join(seed.tech_parks[:4]) + "."},
        {"question": f"What property types are popular {preposition} {seed.name}?", "answer": "Popular options include " + ", ".join(seed.popular_property_types) + "."},
        {"question": f"Is {seed.name} good for working professionals?", "answer": f"{seed.name} works well for many professionals because of access to {', '.join(seed.tech_parks[:2])}, bus connectivity, food options, and managed stays."},
    ]
    return {
        "path": path,
        "canonical_path": path,
        "title": build_location_title(intent, seed),
        "description": build_location_description(intent, seed),
        "hero": {
            "h1": f"{meta['label']} {preposition} {seed.name}",
            "summary": f"Compare verified {meta['plural'].lower()} {preposition} {seed.name}, {seed.city} with commute, lifestyle, pricing, maps, and local decision signals in one place.",
            "primary_search": f"{meta['label']} {preposition} {seed.name}",
        },
        "area_overview": f"{seed.name} is a {seed.kind.replace('_', ' ')} market in {seed.city} with strong demand for {', '.join(seed.popular_property_types[:3])}.",
        "why_live_here": [
            f"Shortlist stays around {', '.join(seed.tech_parks[:2])}.",
            f"Daily needs are supported by nearby restaurants, shopping, gyms, hospitals, and bus routes.",
            "Verified MakeMyStay listings help compare price, amenities, photos, reviews, and availability.",
        ],
        "sections": {
            "nearby_tech_parks": _section("Nearby tech parks", seed.tech_parks),
            "nearby_metro": _section("Nearby metro", seed.metro),
            "nearby_bus_stops": _section("Nearby bus stops", seed.bus_stops),
            "schools": _section("Schools", seed.schools),
            "hospitals": _section("Hospitals", seed.hospitals),
            "restaurants": _section("Restaurants", seed.restaurants),
            "shopping": _section("Shopping", seed.shopping),
            "gyms": _section("Gyms", seed.gyms),
            "parks": _section("Parks", seed.parks),
            "safety": {"title": "Safety", "summary": seed.safety},
            "nightlife": {"title": "Nightlife", "summary": seed.nightlife},
            "cost_of_living": {"title": "Cost of living", "summary": seed.cost_of_living},
            "rental_trends": {"title": "Rental trends", "summary": seed.rental_trends},
            "popular_property_types": _section("Popular property types", seed.popular_property_types),
        },
        "featured_properties": [
            {
                "id": getattr(prop, "id", None),
                "name": _clean(getattr(prop, "property_name", None)),
                "location": _clean(getattr(prop, "location", None)),
                "property_type": _clean(getattr(prop, "property_type", None)),
                "starting_price": getattr(prop, "starting_price", None),
            }
            for prop in properties[:8]
        ],
        "related_localities": _related_locality_links(site_url, seed, intent),
        "internal_links": internal_links,
        "map": {
            "query": seed.map_query,
            "embed_query": seed.map_query.replace(" ", "+"),
            "label": f"Map of {seed.name}, {seed.city}",
        },
        "faqs": faqs,
        "updated_at": datetime.now(timezone.utc).date().isoformat(),
    }
