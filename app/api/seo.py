from __future__ import annotations

from html import escape
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.models.realty import Property
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
    truncate_text,
    xml_datetime,
)

seo_router = APIRouter(tags=["SEO"])

DEFAULT_DESCRIPTION = (
    "Find verified PGs, rooms, flats, and rental homes with MakeMyStay."
)
DEFAULT_IMAGE_PATH = "/og-image.jpg"
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
    errors = _validate_json_ld(json_ld)
    metadata["rich_results_validation"] = {"valid": not errors, "errors": errors}
    return metadata


@seo_router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt() -> str:
    site_url = normalize_site_url(settings.SITE_URL)
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /admin/",
            "Disallow: /docs",
            "Disallow: /redoc",
            "Disallow: /openapi.json",
            f"Sitemap: {site_url}/sitemap.xml",
            "",
        ]
    )


@seo_router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(db: Session = Depends(get_mysql_db)) -> Response:
    site_url = normalize_site_url(settings.SITE_URL)
    urls = [_sitemap_url(f"{site_url}{path}", priority="1.0" if path == "/" else "0.7") for path in PUBLIC_STATIC_PATHS]

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

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{''.join(urls)}"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


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


@seo_router.get("/api/v1/seo/metadata")
def metadata(
    path: str = Query("/", description="Public frontend path, for example / or /properties/pg/my-listing"),
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    site_url = normalize_site_url(settings.SITE_URL)
    normalized_path = path if path.startswith("/") else f"/{path}"

    if normalized_path in STATIC_PAGE_META:
        return _metadata_for_static_path(site_url, normalized_path)

    parts = [part for part in normalized_path.split("/") if part]
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
