from __future__ import annotations

from html import escape
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.models.realty import Property
from app.utils.blog_content_engine import (
    AUTHORS,
    blog_links_for_context,
    blog_path,
    build_blog_post,
    get_blog,
    iter_blog_posts,
    search_blogs,
)
from app.utils.location_seo_engine import (
    SEARCH_INTENTS,
    build_location_page,
    find_location_page,
    get_location_seed,
    iter_location_pages,
)
from app.utils.performance import PUBLIC_CRAWLER_CACHE, PUBLIC_SHORT_CACHE, set_public_cache_headers, weak_etag
from app.utils.seo import (
    PUBLIC_STATIC_PATHS,
    canonical_property_path,
    canonical_property_type,
    canonical_property_url,
    money_value,
    normalize_site_url,
    primary_image_url,
    property_slug,
    public_url,
    safe_slug,
    truncate_text,
    xml_datetime,
)

seo_router = APIRouter(tags=["SEO"])

DEFAULT_DESCRIPTION = (
    "Find verified PGs, rooms, flats, and rental homes with MakeMyStay."
)
DEFAULT_IMAGE_PATH = "/og-image.jpg"
PRIVATE_ROBOTS_PATHS = (
    "/admin/",
    "/dashboard/",
    "/login",
    "/private/",
    "/api/",
    "/docs",
    "/redoc",
    "/openapi.json",
)
PARAMETER_ROBOTS_RULES = (
    "/*?*sort=",
    "/*?*filter=",
    "/*?*filters=",
    "/*?*page=",
    "/*?*utm_",
    "/*?*ref=",
)
STATIC_PAGE_META = {
    "/": ("MakeMyStay | Verified PGs, Rooms and Rentals", DEFAULT_DESCRIPTION),
    "/properties": ("Properties on MakeMyStay", "Browse verified stays, PGs, flats, and rental homes."),
    "/pg": ("PG Accommodation on MakeMyStay", "Find verified PG accommodation with pricing, ratings, and locality details."),
    "/rent": ("Rental Homes on MakeMyStay", "Explore verified rental homes, rooms, and apartments."),
    "/buy": ("Homes for Sale on MakeMyStay", "Discover verified homes and plots available to buy."),
    "/plots": ("Plots on MakeMyStay", "Browse verified residential plots and land listings."),
    "/contact": ("Contact MakeMyStay", "Contact MakeMyStay for verified stays and property support."),
}


def _public_properties_query(db: Session):
    return (
        db.query(Property)
        .filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712
        .filter(func.coalesce(Property.is_available, True) == True)  # noqa: E712
        .filter(Property.property_name.isnot(None))
    )


def _sitemap_url(loc: str, lastmod: str | None = None, priority: str = "0.8") -> str:
    lastmod_xml = f"<lastmod>{escape(lastmod)}</lastmod>" if lastmod else ""
    return (
        "<url>"
        f"<loc>{escape(loc)}</loc>"
        f"{lastmod_xml}"
        "<changefreq>weekly</changefreq>"
        f"<priority>{priority}</priority>"
        "</url>"
    )


def _sitemap_document(urls: list[str]) -> Response:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{''.join(urls)}"
        "</urlset>"
    )
    return set_public_cache_headers(
        Response(content=xml, media_type="application/xml"),
        cache_control=PUBLIC_CRAWLER_CACHE,
        etag=weak_etag(xml),
    )


def _sitemap_index(site_url: str, paths: list[str]) -> Response:
    entries = "".join(
        f"<sitemap><loc>{escape(public_url(site_url, path))}</loc></sitemap>"
        for path in paths
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}"
        "</sitemapindex>"
    )
    return set_public_cache_headers(
        Response(content=xml, media_type="application/xml"),
        cache_control=PUBLIC_CRAWLER_CACHE,
        etag=weak_etag(xml),
    )


def _static_sitemap_urls(site_url: str) -> list[str]:
    return [
        _sitemap_url(f"{site_url}{path}", priority="1.0" if path == "/" else "0.7")
        for path in PUBLIC_STATIC_PATHS
    ]


def _property_sitemap_urls(site_url: str, db: Session) -> list[str]:
    urls: list[str] = []
    properties = (
        _public_properties_query(db)
        .order_by(Property.updated_at.desc(), Property.id.desc())
        .limit(settings.SEO_SITEMAP_MAX_URLS)
        .all()
    )
    for prop in properties:
        urls.append(
            _sitemap_url(
                canonical_property_url(site_url, prop),
                lastmod=xml_datetime(prop.updated_at or prop.created_at),
                priority="0.9",
            )
        )
    return urls


def _city_sitemap_urls(site_url: str, db: Session) -> list[str]:
    rows = (
        _public_properties_query(db)
        .with_entities(Property.city, func.max(Property.updated_at))
        .filter(Property.city.isnot(None))
        .group_by(Property.city)
        .all()
    )
    urls = []
    for city, updated_at in rows:
        city_slug = safe_slug(city)
        if city_slug:
            urls.append(
                _sitemap_url(
                    public_url(site_url, f"/properties?city={city_slug}"),
                    lastmod=xml_datetime(updated_at),
                    priority="0.6",
                )
            )
    return urls


def _location_sitemap_urls(site_url: str) -> list[str]:
    return [_sitemap_url(public_url(site_url, page["path"]), priority="0.8") for page in iter_location_pages()]


def _blog_sitemap_urls(site_url: str) -> list[str]:
    return [
        _sitemap_url(public_url(site_url, blog_path(post.slug)), lastmod=post.updated.isoformat(), priority="0.75")
        for post in iter_blog_posts()
    ]


def _organization_schema(site_url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": f"{site_url}/#organization",
        "name": "MakeMyStay",
        "url": site_url,
        "logo": public_url(site_url, "/logo.svg"),
        "sameAs": [],
    }


def _search_action_schema(site_url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{site_url}/#website",
        "url": site_url,
        "name": "MakeMyStay",
        "publisher": {"@id": f"{site_url}/#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{site_url}/properties?search={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }


def _breadcrumb_schema(site_url: str, crumbs: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": public_url(site_url, path),
            }
            for index, (name, path) in enumerate(crumbs, start=1)
        ],
    }


def _location_faq_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": f"{canonical}#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in page["faqs"]
        ],
    }


def _local_business_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    map_data = page["map"]
    return {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "@id": f"{canonical}#local-business",
        "name": page["hero"]["h1"],
        "url": canonical,
        "description": page["description"],
        "image": public_url(site_url, DEFAULT_IMAGE_PATH),
        "areaServed": {"@type": "City", "name": "Bangalore"},
        "address": {
            "@type": "PostalAddress",
            "addressLocality": map_data["query"],
            "addressRegion": "Karnataka",
            "addressCountry": "IN",
        },
        "parentOrganization": {"@id": f"{site_url}/#organization"},
    }


def _collection_page_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    items = [
        {
            "@type": "ListItem",
            "position": index,
            "name": item["label"],
            "url": item["url"],
        }
        for index, item in enumerate(page["internal_links"][:12], start=1)
    ]
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": f"{canonical}#collection",
        "name": page["title"],
        "url": canonical,
        "description": page["description"],
        "isPartOf": {"@id": f"{site_url}/#website"},
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }


def _author_schema(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": f"{author['url']}#author",
        "name": author["name"],
        "url": author["url"],
        "jobTitle": author["title"],
        "description": author["bio"],
    }


def _image_schema(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "ImageObject",
        "@id": f"{page['featured_image']}#image",
        "url": page["featured_image"],
        "caption": page["title"],
    }


def _webpage_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "@id": f"{canonical}#webpage",
        "url": canonical,
        "name": page["title"],
        "description": page["description"],
        "isPartOf": {"@id": f"{site_url}/#website"},
        "breadcrumb": {"@id": f"{canonical}#breadcrumb"},
    }


def _article_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "@id": f"{canonical}#article",
        "headline": page["title"],
        "description": page["description"],
        "image": [page["featured_image"]],
        "datePublished": page["published_at"],
        "dateModified": page["updated_at"],
        "author": {"@id": f"{page['author']['url']}#author"},
        "publisher": {"@id": f"{site_url}/#organization"},
        "mainEntityOfPage": {"@id": f"{canonical}#webpage"},
    }


def _property_title(prop: Property) -> str:
    location = f" in {prop.location}" if prop.location else ""
    return truncate_text(f"{prop.property_name}{location} | MakeMyStay", 70)


def _property_description(prop: Property) -> str:
    fallback = (
        f"Explore {prop.property_name}"
        f"{' in ' + prop.location if prop.location else ''}"
        f" starting at Rs. {money_value(prop.starting_price):,.0f}"
        if money_value(prop.starting_price) is not None
        else f"Explore {prop.property_name} on MakeMyStay"
    )
    return truncate_text(prop.description or fallback, 160)


def _property_schema(site_url: str, prop: Property) -> dict[str, Any]:
    canonical = canonical_property_url(site_url, prop)
    schema_type = "Accommodation" if canonical_property_type(prop) in ("pg", "rent") else "Residence"
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "@id": f"{canonical}#property",
        "name": prop.property_name,
        "url": canonical,
        "description": _property_description(prop),
        "address": {
            "@type": "PostalAddress",
            "addressLocality": prop.locality or prop.location,
            "addressRegion": prop.city or "Bangalore",
            "addressCountry": "IN",
        },
    }
    image = primary_image_url(prop)
    if image:
        schema["image"] = [image]
    price = money_value(prop.starting_price)
    if price is not None:
        schema["offers"] = {
            "@type": "Offer",
            "url": canonical,
            "price": price,
            "priceCurrency": "INR",
            "availability": "https://schema.org/InStock" if prop.is_available else "https://schema.org/OutOfStock",
        }
    if prop.average_rating and prop.review_count:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": float(prop.average_rating),
            "reviewCount": int(prop.review_count),
        }
    return schema


def _faq_schema(site_url: str, prop: Property) -> dict[str, Any]:
    canonical = canonical_property_url(site_url, prop)
    price = money_value(prop.starting_price)
    questions = [
        (
            f"What is the price for {prop.property_name}?",
            (
                f"{prop.property_name} starts at Rs. {price:,.0f}."
                if price is not None
                else f"Contact MakeMyStay for the latest price for {prop.property_name}."
            ),
        ),
        (
            f"Where is {prop.property_name} located?",
            f"{prop.property_name} is located in {prop.location or prop.city or 'Bangalore'}.",
        ),
        (
            f"Is {prop.property_name} available?",
            "This listing is currently marked as available." if prop.is_available else "This listing is currently not available.",
        ),
    ]
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": f"{canonical}#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in questions
        ],
    }


def _base_metadata(site_url: str, path: str, title: str, description: str, image: str | None = None) -> dict[str, Any]:
    canonical = public_url(site_url, path)
    image_url = image or public_url(site_url, DEFAULT_IMAGE_PATH)
    return {
        "title": title,
        "description": description,
        "canonical": canonical,
        "robots": "index,follow",
        "theme_color": "#0f766e",
        "language": "en-IN",
        "author": "MakeMyStay",
        "publisher": "MakeMyStay",
        "viewport": "width=device-width, initial-scale=1",
        "geo": {
            "region": "IN-KA",
            "placename": "Bangalore",
            "position": "12.9716;77.5946",
        },
        "open_graph": {
            "og:type": "website",
            "og:site_name": "MakeMyStay",
            "og:title": title,
            "og:description": description,
            "og:url": canonical,
            "og:image": image_url,
        },
        "twitter": {
            "twitter:card": "summary_large_image",
            "twitter:title": title,
            "twitter:description": description,
            "twitter:image": image_url,
        },
    }


def _validate_json_ld(json_ld: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, schema in enumerate(json_ld):
        prefix = f"json_ld[{index}]"
        if schema.get("@context") != "https://schema.org":
            errors.append(f"{prefix}: missing schema.org context")
        if not schema.get("@type"):
            errors.append(f"{prefix}: missing @type")
        schema_type = schema.get("@type")
        if schema_type == "BreadcrumbList" and not schema.get("itemListElement"):
            errors.append(f"{prefix}: BreadcrumbList requires itemListElement")
        if schema_type == "FAQPage" and not schema.get("mainEntity"):
            errors.append(f"{prefix}: FAQPage requires mainEntity")
        if schema_type in ("Accommodation", "Residence") and not schema.get("name"):
            errors.append(f"{prefix}: property schema requires name")
        if schema_type == "LocalBusiness" and not schema.get("address"):
            errors.append(f"{prefix}: LocalBusiness requires address")
        if schema_type == "CollectionPage" and not schema.get("mainEntity"):
            errors.append(f"{prefix}: CollectionPage requires mainEntity")
        if schema_type == "Article" and not schema.get("headline"):
            errors.append(f"{prefix}: Article requires headline")
        if schema_type == "ImageObject" and not schema.get("url"):
            errors.append(f"{prefix}: ImageObject requires url")
        if schema_type == "Person" and not schema.get("name"):
            errors.append(f"{prefix}: Person requires name")
        if schema_type == "WebPage" and not schema.get("url"):
            errors.append(f"{prefix}: WebPage requires url")
    return errors


def _metadata_for_static_path(site_url: str, path: str) -> dict[str, Any]:
    normalized_path = path if path in STATIC_PAGE_META else "/"
    title, description = STATIC_PAGE_META[normalized_path]
    crumbs = [("Home", "/")]
    if normalized_path != "/":
        crumbs.append((title.split("|")[0].strip(), normalized_path))
    json_ld = [
        _organization_schema(site_url),
        _search_action_schema(site_url),
        _breadcrumb_schema(site_url, crumbs),
    ]
    metadata = _base_metadata(site_url, normalized_path, title, description)
    metadata["breadcrumbs"] = [{"name": name, "url": public_url(site_url, crumb_path)} for name, crumb_path in crumbs]
    metadata["json_ld"] = json_ld
    metadata["rich_results_validation"] = {
        "valid": not _validate_json_ld(json_ld),
        "errors": _validate_json_ld(json_ld),
    }
    return metadata


def _metadata_for_property(site_url: str, prop: Property) -> dict[str, Any]:
    path = canonical_property_path(prop)
    title = _property_title(prop)
    description = _property_description(prop)
    image = primary_image_url(prop)
    category = canonical_property_type(prop)
    category_label = {"pg": "PG", "rent": "Rent", "buy": "Buy", "plot": "Plots"}.get(category, "Properties")
    crumbs = [
        ("Home", "/"),
        (category_label, f"/{category if category != 'plot' else 'plots'}"),
        (prop.property_name, path),
    ]
    json_ld = [
        _organization_schema(site_url),
        _search_action_schema(site_url),
        _breadcrumb_schema(site_url, crumbs),
        _property_schema(site_url, prop),
        _faq_schema(site_url, prop),
    ]
    metadata = _base_metadata(site_url, path, title, description, image=image)
    metadata["open_graph"]["og:type"] = "article"
    metadata["breadcrumbs"] = [{"name": name, "url": public_url(site_url, crumb_path)} for name, crumb_path in crumbs]
    metadata["json_ld"] = json_ld
    metadata["related_blogs"] = blog_links_for_context(site_url, locality=prop.locality or prop.location or prop.city or "", category=category)
    errors = _validate_json_ld(json_ld)
    metadata["rich_results_validation"] = {"valid": not errors, "errors": errors}
    return metadata


def _featured_properties_for_location(db: Session, intent: str, slug: str) -> list[Property]:
    seed = get_location_seed(slug)
    if not seed:
        return []
    query = _public_properties_query(db).options(joinedload(Property.images))
    intent_meta = SEARCH_INTENTS[intent]
    if intent_meta["property_type"] == "PG":
        query = query.filter(func.lower(Property.property_type) == "pg")
    elif intent_meta["property_type"] == "1BHK":
        query = query.filter(func.lower(Property.property_type).in_(("1bhk", "1 bhk")))
    if seed.name.lower() != "bangalore":
        tokens = [seed.name, *seed.aliases, *seed.nearby_areas[:2]]
        conditions = []
        for token in tokens:
            like = f"%{token.lower()}%"
            conditions.append(func.lower(func.coalesce(Property.location, "")).like(like))
            conditions.append(func.lower(func.coalesce(Property.locality, "")).like(like))
        if conditions:
            query = query.filter(or_(*conditions))
    return query.order_by(Property.updated_at.desc(), Property.id.desc()).limit(8).all()


def _metadata_for_location(site_url: str, path: str, db: Session) -> dict[str, Any]:
    target = find_location_page(path)
    if not target:
        raise HTTPException(status_code=404, detail="SEO metadata target not found")
    featured = _featured_properties_for_location(db, target["intent"], target["slug"])
    seed = get_location_seed(target["slug"])
    blog_links = [
        {**link, "reason": "blog"}
        for link in blog_links_for_context(site_url, locality=seed.name if seed else "", category=target["intent"])
    ]
    page = build_location_page(site_url, target["intent"], target["slug"], featured_properties=featured, blog_links=blog_links)
    label = page["hero"]["primary_search"]
    crumbs = [("Home", "/"), ("Locations", "/locations"), (label, page["path"])]
    json_ld = [
        _organization_schema(site_url),
        _breadcrumb_schema(site_url, crumbs),
        _location_faq_schema(site_url, page),
        _local_business_schema(site_url, page),
        _collection_page_schema(site_url, page),
    ]
    metadata = _base_metadata(site_url, page["path"], page["title"], page["description"])
    metadata["open_graph"]["og:type"] = "website"
    metadata["breadcrumbs"] = [{"name": name, "url": public_url(site_url, crumb_path)} for name, crumb_path in crumbs]
    metadata["json_ld"] = json_ld
    metadata["page"] = page
    metadata["internal_links"] = page["internal_links"]
    errors = _validate_json_ld(json_ld)
    metadata["rich_results_validation"] = {"valid": not errors, "errors": errors}
    return metadata


def _related_properties_for_blog(db: Session, slug: str) -> list[Property]:
    post = get_blog(slug)
    if not post:
        return []
    query = _public_properties_query(db).options(joinedload(Property.images))
    tokens = [post.locality, *post.tags[:3]]
    conditions = []
    for token in tokens:
        like = f"%{token.lower()}%"
        conditions.append(func.lower(func.coalesce(Property.location, "")).like(like))
        conditions.append(func.lower(func.coalesce(Property.locality, "")).like(like))
        conditions.append(func.lower(func.coalesce(Property.property_type, "")).like(like))
    if conditions:
        query = query.filter(or_(*conditions))
    return query.order_by(Property.updated_at.desc(), Property.id.desc()).limit(8).all()


def _blog_faq_schema(site_url: str, page: dict[str, Any]) -> dict[str, Any]:
    canonical = public_url(site_url, page["path"])
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": f"{canonical}#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in page["faqs"]
        ],
    }


def _metadata_for_blog(site_url: str, slug: str, db: Session) -> dict[str, Any]:
    related_properties = _related_properties_for_blog(db, slug)
    page = build_blog_post(site_url, slug, related_properties=related_properties)
    crumbs = [(item["name"], item["url"].replace(site_url, "") or "/") for item in page["breadcrumbs"]]
    json_ld = [
        _organization_schema(site_url),
        _breadcrumb_schema(site_url, crumbs),
        _blog_faq_schema(site_url, page),
        _article_schema(site_url, page),
        _image_schema(page),
        _author_schema(page["author"]),
        _webpage_schema(site_url, page),
    ]
    metadata = _base_metadata(site_url, page["path"], page["title"], page["description"], image=page["featured_image"])
    metadata["open_graph"]["og:type"] = "article"
    metadata["open_graph"]["article:published_time"] = page["published_at"]
    metadata["open_graph"]["article:modified_time"] = page["updated_at"]
    metadata["open_graph"]["article:author"] = page["author"]["name"]
    metadata["twitter"]["twitter:label1"] = "Reading time"
    metadata["twitter"]["twitter:data1"] = f"{page['reading_time_minutes']} min read"
    metadata["breadcrumbs"] = page["breadcrumbs"]
    metadata["json_ld"] = json_ld
    metadata["page"] = page
    metadata["internal_links"] = page["internal_links"]
    errors = _validate_json_ld(json_ld)
    metadata["rich_results_validation"] = {"valid": not errors, "errors": errors}
    return metadata


@seo_router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt(response: Response) -> str:
    site_url = normalize_site_url(settings.SITE_URL)
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /assets/",
        "Allow: /*.css$",
        "Allow: /*.js$",
        "Allow: /*.png$",
        "Allow: /*.jpg$",
        "Allow: /*.jpeg$",
        "Allow: /*.webp$",
    ]
    lines.extend(f"Disallow: {path}" for path in PRIVATE_ROBOTS_PATHS)
    lines.extend(f"Disallow: {rule}" for rule in PARAMETER_ROBOTS_RULES)
    lines.extend(
        [
            f"Sitemap: {site_url}/sitemap.xml",
            f"Sitemap: {site_url}/sitemap-properties.xml",
            f"Sitemap: {site_url}/sitemap-cities.xml",
            f"Sitemap: {site_url}/sitemap-locations.xml",
            f"Sitemap: {site_url}/sitemap-blog.xml",
            f"Sitemap: {site_url}/sitemap-static.xml",
            "",
        ]
    )
    body = "\n".join(lines)
    set_public_cache_headers(response, cache_control=PUBLIC_CRAWLER_CACHE, etag=weak_etag(body))
    return body


@seo_router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(db: Session = Depends(get_mysql_db)) -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_index(site_url, ["/sitemap-static.xml", "/sitemap-properties.xml", "/sitemap-cities.xml", "/sitemap-locations.xml", "/sitemap-blog.xml"])


@seo_router.get("/sitemap-static.xml", include_in_schema=False)
def sitemap_static_xml() -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_document(_static_sitemap_urls(site_url))


@seo_router.get("/sitemap-properties.xml", include_in_schema=False)
def sitemap_properties_xml(db: Session = Depends(get_mysql_db)) -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_document(_property_sitemap_urls(site_url, db))


@seo_router.get("/sitemap-cities.xml", include_in_schema=False)
def sitemap_cities_xml(db: Session = Depends(get_mysql_db)) -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_document(_city_sitemap_urls(site_url, db))


@seo_router.get("/sitemap-locations.xml", include_in_schema=False)
def sitemap_locations_xml() -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_document(_location_sitemap_urls(site_url))


@seo_router.get("/sitemap-blog.xml", include_in_schema=False)
def sitemap_blog_xml() -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    return _sitemap_document(_blog_sitemap_urls(site_url))


@seo_router.get("/api/v1/seo/url-audit")
def url_audit(db: Session = Depends(get_mysql_db)) -> dict[str, Any]:
    site_url = normalize_site_url(settings.SITE_URL)
    rows = _public_properties_query(db).all()
    seen: dict[str, int] = {}
    broken: list[dict[str, Any]] = []
    redirects: list[dict[str, str]] = []

    for prop in rows:
        slug = property_slug(prop)
        path = canonical_property_path(prop)
        if not slug:
            broken.append({"id": prop.id, "issue": "missing_slug"})
        if path in seen:
            broken.append({"id": prop.id, "issue": "duplicate_canonical", "canonical": path, "duplicate_of": seen[path]})
        seen[path] = prop.id
        api_path = f"/api/v1/realty/properties/{prop.id}"
        redirects.append({"from": api_path, "to": f"{site_url}{path}", "type": "canonical"})

    return {
        "site_url": site_url,
        "indexed_static_urls": [f"{site_url}{path}" for path in PUBLIC_STATIC_PATHS],
        "indexed_property_urls": len(rows),
        "issues": broken,
        "canonical_redirect_hints": redirects,
    }


@seo_router.get("/api/v1/seo/technical-audit")
def technical_audit(db: Session = Depends(get_mysql_db)) -> dict[str, Any]:
    site_url = normalize_site_url(settings.SITE_URL)
    rows = _public_properties_query(db).options(joinedload(Property.images)).all()
    missing_slug = []
    duplicate_canonicals = []
    missing_descriptions = []
    missing_images = []
    seen: dict[str, int] = {}

    for prop in rows:
        path = canonical_property_path(prop)
        if path in seen:
            duplicate_canonicals.append({"id": prop.id, "canonical": path, "duplicate_of": seen[path]})
        seen[path] = prop.id
        if not property_slug(prop):
            missing_slug.append(prop.id)
        if not (prop.description or "").strip():
            missing_descriptions.append(prop.id)
        if not primary_image_url(prop):
            missing_images.append(prop.id)

    critical = []
    high = []
    medium = []
    low = []
    if duplicate_canonicals:
        critical.append({"issue": "duplicate_canonical_property_urls", "count": len(duplicate_canonicals), "examples": duplicate_canonicals[:10]})
    if missing_slug:
        high.append({"issue": "missing_property_slugs", "count": len(missing_slug), "examples": missing_slug[:20]})
    if missing_descriptions:
        medium.append({"issue": "missing_property_descriptions", "count": len(missing_descriptions), "examples": missing_descriptions[:20]})
    if missing_images:
        medium.append({"issue": "missing_primary_images", "count": len(missing_images), "examples": missing_images[:20]})
    low.append({"issue": "frontend_audit_required", "detail": "React/Vite source is not present in this backend workspace."})

    return {
        "site_url": site_url,
        "summary": {
            "public_static_urls": len(PUBLIC_STATIC_PATHS),
            "indexable_property_urls": len(rows),
            "sitemap_files": [
                f"{site_url}/sitemap.xml",
                f"{site_url}/sitemap-static.xml",
                f"{site_url}/sitemap-properties.xml",
                f"{site_url}/sitemap-cities.xml",
                f"{site_url}/sitemap-locations.xml",
                f"{site_url}/sitemap-blog.xml",
            ],
            "location_landing_pages": len(list(iter_location_pages())),
            "blog_posts": len(list(iter_blog_posts())),
            "blog_authors": len(AUTHORS),
        },
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
    }


@seo_router.get("/api/v1/seo/metadata")
def metadata(
    path: str = Query("/", description="Public frontend path, for example / or /properties/pg/my-listing"),
    response: Response = None,
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    if response is not None:
        set_public_cache_headers(response, cache_control=PUBLIC_SHORT_CACHE)
    site_url = normalize_site_url(settings.SITE_URL)
    normalized_path = path if path.startswith("/") else f"/{path}"

    if normalized_path in STATIC_PAGE_META:
        return _metadata_for_static_path(site_url, normalized_path)

    if find_location_page(normalized_path):
        return _metadata_for_location(site_url, normalized_path, db)

    blog_parts = [part for part in normalized_path.split("/") if part]
    if len(blog_parts) == 2 and blog_parts[0] == "blog" and get_blog(blog_parts[1]):
        return _metadata_for_blog(site_url, blog_parts[1], db)

    parts = blog_parts
    if len(parts) == 3 and parts[0] == "properties":
        _, property_type, slug = parts
        prop = (
            _public_properties_query(db)
            .options(joinedload(Property.images))
            .filter(Property.slug == slug)
            .first()
        )
        if not prop:
            raise HTTPException(status_code=404, detail="SEO metadata target not found")
        canonical_type = canonical_property_type(prop)
        if property_type != canonical_type:
            raise HTTPException(
                status_code=308,
                detail={
                    "canonical": canonical_property_url(site_url, prop),
                    "canonical_path": canonical_property_path(prop),
                },
            )
        return _metadata_for_property(site_url, prop)

    raise HTTPException(status_code=404, detail="SEO metadata target not found")


@seo_router.get("/api/v1/seo/location-page")
def location_page(
    path: str = Query(..., description="Location landing path, for example /locations/pg/bellandur"),
    response: Response = None,
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    if response is not None:
        set_public_cache_headers(response, cache_control=PUBLIC_SHORT_CACHE)
    site_url = normalize_site_url(settings.SITE_URL)
    normalized_path = path if path.startswith("/") else f"/{path}"
    payload = _metadata_for_location(site_url, normalized_path, db)
    return payload["page"]


@seo_router.get("/api/v1/seo/blog")
def blog_index(
    q: str = Query("", description="Search query"),
    category: str = Query("", description="Blog category slug or name"),
    tag: str = Query("", description="Blog tag slug or name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    response: Response = None,
) -> dict[str, Any]:
    if response is not None:
        set_public_cache_headers(response, cache_control=PUBLIC_SHORT_CACHE)
    site_url = normalize_site_url(settings.SITE_URL)
    result = search_blogs(q, category, tag, page, page_size)
    return {
        "items": [
            {
                "title": post.title,
                "description": truncate_text(post.summary, 160),
                "url": public_url(site_url, blog_path(post.slug)),
                "category": post.category,
                "tags": list(post.tags),
                "author": AUTHORS[post.author].name,
                "reading_time_minutes": build_blog_post(site_url, post.slug)["reading_time_minutes"],
                "featured_image": public_url(site_url, post.featured_image),
                "updated_at": post.updated.isoformat(),
            }
            for post in result["items"]
        ],
        "pagination": result["pagination"],
        "categories": sorted({post.category for post in iter_blog_posts()}),
        "tags": sorted({tag for post in iter_blog_posts() for tag in post.tags}),
    }


@seo_router.get("/api/v1/seo/blog-post")
def blog_post(
    path: str = Query(..., description="Blog path, for example /blog/moving-to-bangalore-rental-pg-guide"),
    response: Response = None,
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    if response is not None:
        set_public_cache_headers(response, cache_control=PUBLIC_SHORT_CACHE)
    site_url = normalize_site_url(settings.SITE_URL)
    normalized_path = path if path.startswith("/") else f"/{path}"
    parts = [part for part in normalized_path.split("/") if part]
    if len(parts) != 2 or parts[0] != "blog" or not get_blog(parts[1]):
        raise HTTPException(status_code=404, detail="Blog post not found")
    payload = _metadata_for_blog(site_url, parts[1], db)
    return payload["page"]


@seo_router.get("/api/v1/seo/rich-results")
def rich_results(
    path: str = Query("/", description="Public frontend path to validate"),
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    payload = metadata(path=path, db=db)
    validation = payload["rich_results_validation"]
    return {
        "path": path,
        "canonical": payload["canonical"],
        "valid": validation["valid"],
        "errors": validation["errors"],
        "schema_types": [schema.get("@type") for schema in payload.get("json_ld", [])],
    }
