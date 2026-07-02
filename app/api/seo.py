from __future__ import annotations

from html import escape
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.models.realty import Property
from app.utils.seo import (
    PUBLIC_STATIC_PATHS,
    canonical_property_path,
    canonical_property_url,
    normalize_site_url,
    property_slug,
    xml_datetime,
)

seo_router = APIRouter(tags=["SEO"])


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
