from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Any, Iterable, Optional

from app.utils.location_seo_engine import get_location_seed, location_path
from app.utils.seo import canonical_property_url, public_url, safe_slug, truncate_text


@dataclass(frozen=True)
class BlogAuthor:
    name: str
    slug: str
    title: str
    bio: str


@dataclass(frozen=True)
class BlogSeed:
    title: str
    slug: str
    category: str
    tags: tuple[str, ...]
    author: str
    intent: str
    topic: str
    locality: str
    summary: str
    sections: tuple[str, ...]
    faqs: tuple[tuple[str, str], ...]
    featured_image: str
    published: date
    updated: date


AUTHORS: dict[str, BlogAuthor] = {
    "makemystay-editorial": BlogAuthor(
        name="MakeMyStay Editorial",
        slug="makemystay-editorial",
        title="Housing research team",
        bio="Local housing researchers covering PGs, coliving, rentals, commute, and neighborhood decisions.",
    ),
    "rental-advisory": BlogAuthor(
        name="MakeMyStay Rental Advisory",
        slug="rental-advisory",
        title="Rental strategy desk",
        bio="Rental specialists helping tenants compare pricing, deposits, amenities, and move-in readiness.",
    ),
}


BLOG_SEEDS: tuple[BlogSeed, ...] = (
    BlogSeed(
        title="Moving to Bangalore: Complete Rental and PG Guide",
        slug="moving-to-bangalore-rental-pg-guide",
        category="Moving to Bangalore",
        tags=("moving", "bangalore", "rental tips", "pg"),
        author="makemystay-editorial",
        intent="informational",
        topic="moving_to_bangalore",
        locality="Bangalore",
        summary="A practical guide to choosing areas, PGs, coliving spaces, rentals, commute routes, deposits, and move-in checks when relocating to Bangalore.",
        sections=("Choose the right commute corridor", "Compare PG, coliving, and flats", "Budget for rent and deposits", "Verify safety and amenities", "Plan the first week"),
        faqs=(
            ("Which area is best when moving to Bangalore?", "Choose the area based on office location, metro or bus access, budget, and late-evening commute safety."),
            ("Is PG or flat better for a new Bangalore resident?", "PGs and coliving work better for fast move-ins, while flats suit longer stays and families."),
        ),
        featured_image="/og/blog-moving-bangalore.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Best PGs in Bangalore for Working Professionals",
        slug="best-pgs-in-bangalore-working-professionals",
        category="Best PGs",
        tags=("pg", "working professionals", "bangalore", "verified stays"),
        author="makemystay-editorial",
        intent="commercial",
        topic="best_pgs",
        locality="Bangalore",
        summary="How to shortlist professional-friendly PGs in Bangalore by commute, food, Wi-Fi, security, housekeeping, and rent transparency.",
        sections=("What makes a PG professional-friendly", "Best corridors to compare", "Amenities to verify", "Pricing and deposit checks", "How MakeMyStay helps"),
        faqs=(
            ("What should working professionals check in a PG?", "Prioritize commute, Wi-Fi, power backup, meals, housekeeping, entry rules, and visitor policy."),
            ("Which Bangalore areas have strong PG demand?", "Bellandur, Marathahalli, Whitefield, HSR Layout, Koramangala, Electronic City, and Manyata are major PG clusters."),
        ),
        featured_image="/og/blog-best-pgs.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Best Coliving Spaces in Bangalore: What to Compare",
        slug="best-coliving-spaces-bangalore",
        category="Best Coliving",
        tags=("coliving", "bangalore", "managed stays"),
        author="makemystay-editorial",
        intent="commercial",
        topic="best_coliving",
        locality="Bangalore",
        summary="A comparison framework for Bangalore coliving spaces across privacy, community, food, housekeeping, security, and commute access.",
        sections=("Coliving versus PG", "Room sharing choices", "Community and house rules", "Cost inclusions", "Best-fit localities"),
        faqs=(
            ("Is coliving more expensive than PG?", "Coliving can cost more when it includes better common spaces, events, premium furnishing, and managed services."),
            ("Who should choose coliving?", "Coliving suits students, freshers, and professionals who want managed services and a lighter setup burden."),
        ),
        featured_image="/og/blog-coliving.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Rental Tips for Bangalore: Deposits, Agreements, and Move-In Checks",
        slug="bangalore-rental-tips-deposit-agreement",
        category="Rental Tips",
        tags=("rental tips", "deposit", "agreement", "bangalore"),
        author="rental-advisory",
        intent="informational",
        topic="rental_tips",
        locality="Bangalore",
        summary="Tenant-focused rental tips for Bangalore covering deposits, rental agreements, maintenance, brokerage, inventory checks, and exit clauses.",
        sections=("Deposit norms", "Agreement clauses", "Inventory checks", "Maintenance and utilities", "Exit planning"),
        faqs=(
            ("How much deposit is common in Bangalore rentals?", "Deposits vary by area and owner, so compare total upfront cost rather than rent alone."),
            ("What should be in a rental agreement?", "Include rent, deposit, notice period, lock-in, maintenance, utility rules, and handover condition."),
        ),
        featured_image="/og/blog-rental-tips.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Bellandur Area Guide for PGs, Coliving, and 1 BHK Rentals",
        slug="bellandur-area-guide-pg-coliving-1-bhk",
        category="Area Guides",
        tags=("bellandur", "area guide", "pg", "1 bhk"),
        author="makemystay-editorial",
        intent="local",
        topic="area_guides",
        locality="Bellandur",
        summary="A local guide to Bellandur covering ORR commute, nearby tech parks, PG demand, 1 BHK rentals, food, safety, and lifestyle.",
        sections=("Bellandur overview", "Tech park commute", "PG and 1 BHK demand", "Food and lifestyle", "Who should live here"),
        faqs=(
            ("Is Bellandur good for PG accommodation?", "Bellandur is strong for PGs because of ORR offices, Embassy Tech Village, RMZ Ecospace, and Sarjapur Road access."),
            ("What property types are popular in Bellandur?", "PGs, coliving rooms, 1 BHK homes, and 2 BHK flats are common Bellandur searches."),
        ),
        featured_image="/og/blog-bellandur-guide.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Cost of Living in Bangalore for Students and Working Professionals",
        slug="cost-of-living-in-bangalore-students-professionals",
        category="Cost of Living",
        tags=("cost of living", "students", "working professionals", "bangalore"),
        author="rental-advisory",
        intent="informational",
        topic="cost_of_living",
        locality="Bangalore",
        summary="Estimate monthly Bangalore living costs across rent, food, commute, utilities, deposits, furnishings, and lifestyle choices.",
        sections=("Monthly rent ranges", "Food and utilities", "Commute costs", "Setup and deposits", "Ways to control spend"),
        faqs=(
            ("What is the biggest monthly cost in Bangalore?", "Rent is usually the largest cost, followed by food, commute, utilities, and lifestyle spend."),
            ("How can students reduce living costs?", "Students can reduce costs through shared PG rooms, inclusive meals, and locations close to college or metro routes."),
        ),
        featured_image="/og/blog-cost-bangalore.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="PG Near Embassy Tech Village: Commute and Locality Guide",
        slug="pg-near-embassy-tech-village-guide",
        category="Tech Park Guides",
        tags=("embassy tech village", "pg", "tech park", "bellandur"),
        author="makemystay-editorial",
        intent="local",
        topic="tech_park_guides",
        locality="Embassy Tech Village",
        summary="Compare PGs near Embassy Tech Village across Bellandur, Kadubeesanahalli, Devarabisanahalli, and Marathahalli commute routes.",
        sections=("Best nearby localities", "Walk and bus commute", "What PG amenities matter", "Budget signals", "Shortlist checklist"),
        faqs=(
            ("Which areas are close to Embassy Tech Village?", "Bellandur, Kadubeesanahalli, Devarabisanahalli, Panathur, and Marathahalli are common options."),
            ("Is PG near Embassy Tech Village expensive?", "Closest ORR inventory is usually premium, while nearby inner areas may offer better value."),
        ),
        featured_image="/og/blog-etv-guide.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Student Housing in Bangalore: PG, Coliving, or Apartment?",
        slug="student-housing-bangalore-pg-coliving-apartment",
        category="Student Housing",
        tags=("student housing", "pg", "coliving", "apartment"),
        author="makemystay-editorial",
        intent="informational",
        topic="student_housing",
        locality="Bangalore",
        summary="A student housing guide comparing PGs, coliving spaces, and apartments by budget, rules, meals, safety, and college commute.",
        sections=("Student priorities", "PG pros and cons", "Coliving pros and cons", "Apartment setup costs", "Parent checklist"),
        faqs=(
            ("Is PG safe for students in Bangalore?", "Choose verified PGs with access control, clear rules, lighting, and reachable management."),
            ("Should students rent apartments?", "Apartments work when students can manage deposits, furniture, utilities, cooking, and longer commitments."),
        ),
        featured_image="/og/blog-student-housing.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="1 BHK in Bellandur: Rent, Commute, and Shortlist Guide",
        slug="1-bhk-in-bellandur-rent-commute-guide",
        category="1 BHK Guides",
        tags=("1 bhk", "bellandur", "rent", "commute"),
        author="rental-advisory",
        intent="local",
        topic="1_bhk_guides",
        locality="Bellandur",
        summary="A guide to finding 1 BHK rentals in Bellandur, including ORR commute, rent drivers, furnishing, deposits, and building checks.",
        sections=("Who should choose Bellandur", "Rent drivers", "Furnished versus unfurnished", "Commute to tech parks", "Visit checklist"),
        faqs=(
            ("Is Bellandur good for 1 BHK rentals?", "Bellandur works well for people needing ORR, Sarjapur Road, and nearby tech park access."),
            ("What should I check before renting a 1 BHK?", "Check ventilation, water, power backup, parking, deposit terms, maintenance, and commute at office timings."),
        ),
        featured_image="/og/blog-1bhk-bellandur.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Apartment Guide in Bangalore: How to Compare Flats Before Renting",
        slug="apartment-guide-bangalore-compare-flats",
        category="Apartment Guides",
        tags=("apartment", "flat", "rental tips", "bangalore"),
        author="rental-advisory",
        intent="commercial",
        topic="apartment_guides",
        locality="Bangalore",
        summary="A practical apartment comparison guide for Bangalore renters evaluating flats, societies, maintenance, commute, and total monthly cost.",
        sections=("Shortlist by lifestyle", "Society checks", "Maintenance costs", "Commute and parking", "Final negotiation"),
        faqs=(
            ("How do I compare apartments in Bangalore?", "Compare total monthly cost, commute, society condition, maintenance, water, parking, and agreement terms."),
            ("Are furnished apartments worth it?", "Furnished apartments can reduce setup work but should be compared on rent premium and item condition."),
        ),
        featured_image="/og/blog-apartment-guide.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
    BlogSeed(
        title="Real Estate Investment Guide for Bangalore Rental Demand",
        slug="bangalore-real-estate-investment-rental-demand-guide",
        category="Investment Guides",
        tags=("investment", "rental demand", "bangalore", "property"),
        author="rental-advisory",
        intent="commercial",
        topic="investment_guides",
        locality="Bangalore",
        summary="A rental-demand lens for Bangalore property investors comparing tenant profiles, tech corridors, furnishing, liquidity, and operating risk.",
        sections=("Demand corridors", "Tenant profiles", "Furnishing strategy", "Yield and vacancy", "Risk controls"),
        faqs=(
            ("Which Bangalore areas have rental demand?", "Tech corridors around ORR, Whitefield, Electronic City, North Bangalore, and central startup hubs see durable rental demand."),
            ("What should investors verify?", "Verify legal title, demand depth, vacancy risk, maintenance, furnishing costs, and exit liquidity."),
        ),
        featured_image="/og/blog-investment-guide.jpg",
        published=date(2026, 7, 2),
        updated=date(2026, 7, 2),
    ),
)


def _clean(value: Optional[Any]) -> str:
    return " ".join(str(value or "").split()).strip()


def blog_path(slug: str) -> str:
    return f"/blog/{safe_slug(slug)}"


def get_blog(slug: str) -> Optional[BlogSeed]:
    slug = safe_slug(slug)
    return next((post for post in BLOG_SEEDS if safe_slug(post.slug) == slug), None)


def iter_blog_posts() -> Iterable[BlogSeed]:
    return sorted(BLOG_SEEDS, key=lambda post: (post.updated, post.title), reverse=True)


def _reading_time(seed: BlogSeed) -> int:
    words = len((seed.summary + " " + " ".join(seed.sections) + " " + " ".join(a for _, a in seed.faqs)).split())
    return max(4, ceil((words + 900) / 220))


def _toc(seed: BlogSeed) -> list[dict[str, str]]:
    return [{"id": safe_slug(section), "label": section} for section in seed.sections]


def _body_sections(seed: BlogSeed) -> list[dict[str, Any]]:
    sections = []
    for title in seed.sections:
        sections.append(
            {
                "id": safe_slug(title),
                "heading": title,
                "body": _generated_section(seed, title),
            }
        )
    return sections


def _generated_section(seed: BlogSeed, heading: str) -> str:
    locality = seed.locality
    if "commute" in heading.lower():
        return f"Treat commute as a daily cost, not a one-time filter. For {locality}, compare office-timing travel, late-evening return options, bus or metro access, and the last-mile route from each shortlisted property."
    if "budget" in heading.lower() or "cost" in heading.lower() or "deposit" in heading.lower():
        return f"Build the budget from rent, deposit, food, utilities, maintenance, commute, and setup costs. In {locality}, inclusive PG or coliving pricing can be easier to compare than bare rent alone."
    if "safety" in heading.lower() or "verify" in heading.lower() or "check" in heading.lower():
        return "During the visit, verify access control, lighting, water supply, power backup, house rules, maintenance owner, and exact inclusions before paying a token amount."
    return f"{heading} matters because housing quality changes by lane, building, operator, and commute pattern. Use verified listings, compare photos and amenities, and shortlist options that match your daily routine in {locality}."


def search_blogs(query: str = "", category: str = "", tag: str = "", page: int = 1, page_size: int = 10) -> dict[str, Any]:
    query_norm = query.strip().lower()
    category_norm = category.strip().lower()
    tag_norm = tag.strip().lower()
    posts = list(iter_blog_posts())
    if query_norm:
        posts = [
            post for post in posts
            if query_norm in " ".join([post.title, post.summary, post.category, " ".join(post.tags), post.locality]).lower()
        ]
    if category_norm:
        posts = [post for post in posts if safe_slug(post.category) == safe_slug(category_norm)]
    if tag_norm:
        posts = [post for post in posts if any(safe_slug(item) == safe_slug(tag_norm) for item in post.tags)]
    total = len(posts)
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    start = (page - 1) * page_size
    return {
        "items": posts[start:start + page_size],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        },
    }


def related_blog_posts(seed: BlogSeed, limit: int = 4) -> list[BlogSeed]:
    scored = []
    seed_tags = {safe_slug(tag) for tag in seed.tags}
    for post in BLOG_SEEDS:
        if post.slug == seed.slug:
            continue
        score = 0
        if post.category == seed.category:
            score += 4
        if safe_slug(post.locality) == safe_slug(seed.locality):
            score += 3
        score += len(seed_tags.intersection({safe_slug(tag) for tag in post.tags}))
        if score:
            scored.append((score, post.updated, post.title, post))
    return [post for _, _, _, post in sorted(scored, key=lambda item: (item[0], item[1], item[2]), reverse=True)[:limit]]


def blog_links_for_context(site_url: str, *, locality: str = "", category: str = "", limit: int = 4) -> list[dict[str, str]]:
    locality_slug = safe_slug(locality)
    category_slug = safe_slug(category)
    scored = []
    for post in BLOG_SEEDS:
        score = 0
        if locality_slug and locality_slug == safe_slug(post.locality):
            score += 5
        if category_slug and category_slug in {safe_slug(post.category), *(safe_slug(tag) for tag in post.tags)}:
            score += 3
        if not locality_slug and not category_slug:
            score += 1
        if score:
            scored.append((score, post.updated, post.title, post))
    return [
        {"label": post.title, "url": public_url(site_url, blog_path(post.slug)), "reason": "related_blog"}
        for _, _, _, post in sorted(scored, key=lambda item: (item[0], item[1], item[2]), reverse=True)[:limit]
    ]


def _property_cards(site_url: str, properties: list[Any]) -> list[dict[str, Any]]:
    cards = []
    for prop in properties[:8]:
        name = _clean(getattr(prop, "property_name", None))
        if not name:
            continue
        cards.append(
            {
                "id": getattr(prop, "id", None),
                "name": name,
                "url": canonical_property_url(site_url, prop),
                "location": _clean(getattr(prop, "location", None)),
                "property_type": _clean(getattr(prop, "property_type", None)),
                "starting_price": getattr(prop, "starting_price", None),
            }
        )
    return cards


def build_ai_content(seed: BlogSeed) -> dict[str, Any]:
    locality = seed.locality
    area = get_location_seed(locality)
    commute_targets = list(area.tech_parks[:3]) if area else ["major office corridors", "metro routes", "bus stops"]
    return {
        "faq_generation": [{"question": q, "answer": a} for q, a in seed.faqs],
        "area_guide": f"{locality} should be evaluated by commute reliability, verified inventory, safety, food access, and total monthly cost.",
        "property_tips": [
            "Verify rent, deposit, notice period, lock-in, and maintenance in writing.",
            "Check water, power backup, Wi-Fi, housekeeping, meals, parking, and entry rules during the visit.",
            "Compare total monthly cost instead of sorting only by headline rent.",
        ],
        "rental_guide": f"For {locality}, shortlist properties by commute first, then compare furnishing, building condition, agreement terms, and move-in timeline.",
        "commute_guide": f"Compare routes to {', '.join(commute_targets)} during office hours and late evenings before finalizing.",
        "lifestyle_guide": f"Balance daily food, gym, shopping, parks, healthcare, and nightlife access with rent and commute fit in {locality}.",
    }


def build_blog_post(site_url: str, slug: str, *, related_properties: Optional[list[Any]] = None) -> dict[str, Any]:
    seed = get_blog(slug)
    if not seed:
        raise ValueError("Unknown blog post")
    author = AUTHORS[seed.author]
    path = blog_path(seed.slug)
    related_posts = related_blog_posts(seed)
    location_seed = get_location_seed(seed.locality)
    locality_path = location_path("pg", safe_slug(seed.locality)) if location_seed else f"/properties?search={seed.locality.replace(' ', '+')}"
    related_localities = []
    if location_seed:
        related_localities = [
            {
                "label": f"PG in {item}",
                "url": public_url(site_url, location_path("pg", safe_slug(item))) if get_location_seed(item) else public_url(site_url, f"/properties?search={item.replace(' ', '+')}"),
                "reason": "related_locality",
            }
            for item in location_seed.nearby_areas[:4]
        ]
    related_property_cards = _property_cards(site_url, related_properties or [])
    internal_links = (
        [{"label": "Browse properties", "url": public_url(site_url, "/properties"), "reason": "property_index"}]
        + [{"label": f"Properties in {seed.locality}", "url": public_url(site_url, f"/properties?search={seed.locality.replace(' ', '+')}"), "reason": "city_or_area_page"}]
        + [{"label": f"PG in {seed.locality}", "url": public_url(site_url, locality_path), "reason": "location_page"}]
        + [{"label": post.title, "url": public_url(site_url, blog_path(post.slug)), "reason": "related_post"} for post in related_posts]
        + [{"label": card["name"], "url": card["url"], "reason": "related_property"} for card in related_property_cards]
        + related_localities
        + [{"label": f"{tag.title()} searches", "url": public_url(site_url, f"/properties?search={tag.replace(' ', '+')}"), "reason": "popular_search"} for tag in seed.tags[:3]]
    )
    return {
        "path": path,
        "title": seed.title,
        "description": truncate_text(seed.summary, 160),
        "canonical_path": path,
        "category": {"name": seed.category, "slug": safe_slug(seed.category)},
        "tags": [{"name": tag, "slug": safe_slug(tag)} for tag in seed.tags],
        "author": {
            "name": author.name,
            "slug": author.slug,
            "title": author.title,
            "bio": author.bio,
            "url": public_url(site_url, f"/blog/authors/{author.slug}"),
        },
        "intent": seed.intent,
        "locality": seed.locality,
        "reading_time_minutes": _reading_time(seed),
        "published_at": seed.published.isoformat(),
        "updated_at": seed.updated.isoformat(),
        "featured_image": public_url(site_url, seed.featured_image),
        "summary": seed.summary,
        "table_of_contents": _toc(seed),
        "sections": _body_sections(seed),
        "faqs": [{"question": q, "answer": a} for q, a in seed.faqs],
        "related_posts": [
            {"title": post.title, "url": public_url(site_url, blog_path(post.slug)), "category": post.category}
            for post in related_posts
        ],
        "related_properties": related_property_cards,
        "related_localities": related_localities,
        "share_links": {
            "whatsapp": f"https://wa.me/?text={public_url(site_url, path)}",
            "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={public_url(site_url, path)}",
            "x": f"https://twitter.com/intent/tweet?url={public_url(site_url, path)}&text={seed.title.replace(' ', '+')}",
        },
        "breadcrumbs": [
            {"name": "Home", "url": public_url(site_url, "/")},
            {"name": "Blog", "url": public_url(site_url, "/blog")},
            {"name": seed.category, "url": public_url(site_url, f"/blog/category/{safe_slug(seed.category)}")},
            {"name": seed.title, "url": public_url(site_url, path)},
        ],
        "internal_links": internal_links,
        "ai_content": build_ai_content(seed),
    }
