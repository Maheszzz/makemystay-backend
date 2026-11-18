import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MAIL_USERNAME", "test@example.com")
os.environ.setdefault("MAIL_PASSWORD", "test")
os.environ.setdefault("MAIL_FROM", "test@example.com")
os.environ.setdefault("MAIL_PORT", "587")
os.environ.setdefault("MAIL_SERVER", "smtp.example.com")
os.environ.setdefault("MAIL_FROM_NAME", "Test")
os.environ.setdefault("SITE_URL", "https://example.com")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.seo as seo_module
from app.api.seo import seo_router
from app.configs.db_config import get_mysql_db
from app.models.realty import Property, PropertyImage
from app.configs.db_config import MySQLBase


@pytest.fixture(autouse=True)
def _use_example_site_url(monkeypatch):
    monkeypatch.setattr(seo_module.settings, "SITE_URL", "https://example.com", raising=False)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
MySQLBase.metadata.create_all(bind=engine)


def override_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(seo_router)
app.dependency_overrides[get_mysql_db] = override_db
client = TestClient(app)


def setup_function():
    db = SessionLocal()
    db.query(PropertyImage).delete()
    db.query(Property).delete()
    prop = Property(
        property_name="Sunrise PG",
        location="Koramangala",
        city="bangalore",
        property_type="PG",
        listing_type="rent",
        starting_price=12000,
        slug="sunrise-pg-koramangala",
        is_available=True,
        is_deleted=False,
        average_rating=4.5,
        review_count=12,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    db.add(prop)
    db.flush()
    db.add(
        PropertyImage(
            property_id=prop.id,
            image_url="https://cdn.example.com/sunrise.jpg",
            is_primary=True,
        )
    )
    db.add(
        Property(
            property_name="Bellandur Nest PG",
            location="Bellandur",
            locality="Bellandur",
            city="bangalore",
            property_type="PG",
            listing_type="rent",
            starting_price=15000,
            slug="bellandur-nest-pg",
            is_available=True,
            is_deleted=False,
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        )
    )
    db.add(
        Property(
            property_name="Hidden Flat",
            location="Indiranagar",
            city="bangalore",
            property_type="1BHK",
            listing_type="rent",
            starting_price=22000,
            slug="hidden-flat-indiranagar",
            is_available=False,
            is_deleted=False,
        )
    )
    db.commit()
    db.close()


def test_robots_txt_points_to_sitemap_and_blocks_api():
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"].startswith("public")
    assert response.headers["etag"].startswith('W/"')
    assert "Disallow: /api/" in response.text
    assert "Disallow: /dashboard/" in response.text
    assert "Disallow: /*?*filter=" in response.text
    assert "Sitemap: https://example.com/sitemap.xml" in response.text
    assert "Sitemap: https://example.com/sitemap-properties.xml" in response.text
    assert "Sitemap: https://example.com/sitemap-locations.xml" in response.text
    assert "Sitemap: https://example.com/sitemap-blog.xml" in response.text


def test_sitemap_index_points_to_segmented_sitemaps():
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["cache-control"].startswith("public")
    assert response.headers["etag"].startswith('W/"')
    assert "<sitemapindex" in response.text
    assert "<loc>https://example.com/sitemap-static.xml</loc>" in response.text
    assert "<loc>https://example.com/sitemap-properties.xml</loc>" in response.text
    assert "<loc>https://example.com/sitemap-cities.xml</loc>" in response.text
    assert "<loc>https://example.com/sitemap-locations.xml</loc>" in response.text
    assert "<loc>https://example.com/sitemap-blog.xml</loc>" in response.text


def test_property_sitemap_includes_only_available_canonical_property_urls():
    response = client.get("/sitemap-properties.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>https://example.com/properties/pg/sunrise-pg-koramangala</loc>" in response.text
    assert "<loc>https://example.com/properties/pg/bellandur-nest-pg</loc>" in response.text
    assert "hidden-flat-indiranagar" not in response.text


def test_static_sitemap_includes_public_static_urls():
    response = client.get("/sitemap-static.xml")

    assert response.status_code == 200
    assert "<loc>https://example.com/</loc>" in response.text
    assert "<loc>https://example.com/contact</loc>" in response.text


def test_city_sitemap_includes_city_cluster_urls():
    response = client.get("/sitemap-cities.xml")

    assert response.status_code == 200
    assert "<loc>https://example.com/properties?city=bangalore</loc>" in response.text


def test_location_sitemap_includes_generated_location_landing_pages():
    response = client.get("/sitemap-locations.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>https://example.com/locations/pg/bellandur</loc>" in response.text
    assert "<loc>https://example.com/locations/pg/embassy-tech-village</loc>" in response.text
    assert "<loc>https://example.com/locations/coliving/bangalore</loc>" in response.text


def test_blog_sitemap_includes_generated_blog_posts():
    response = client.get("/sitemap-blog.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>https://example.com/blog/moving-to-bangalore-rental-pg-guide</loc>" in response.text
    assert "<loc>https://example.com/blog/bellandur-area-guide-pg-coliving-1-bhk</loc>" in response.text


def test_url_audit_reports_canonical_redirect_hints():
    response = client.get("/api/v1/seo/url-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["indexed_property_urls"] == 2
    assert body["issues"] == []
    redirect_targets = {item["to"] for item in body["canonical_redirect_hints"]}
    assert "https://example.com/properties/pg/sunrise-pg-koramangala" in redirect_targets


def test_static_metadata_includes_social_and_search_action_schema():
    response = client.get("/api/v1/seo/metadata", params={"path": "/"})

    assert response.status_code == 200
    body = response.json()
    assert response.headers["cache-control"].startswith("public")
    assert body["canonical"] == "https://example.com/"
    assert body["language"] == "en-IN"
    assert body["theme_color"] == "#0f766e"
    assert body["geo"]["region"] == "IN-KA"
    assert body["open_graph"]["og:title"] == body["title"]
    assert body["twitter"]["twitter:card"] == "summary_large_image"
    assert body["rich_results_validation"]["valid"] is True
    assert [schema["@type"] for schema in body["json_ld"]] == [
        "Organization",
        "WebSite",
        "BreadcrumbList",
    ]
    assert body["json_ld"][1]["potentialAction"]["@type"] == "SearchAction"


def test_technical_audit_categorizes_indexability_issues():
    response = client.get("/api/v1/seo/technical-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["indexable_property_urls"] == 2
    assert body["summary"]["sitemap_files"] == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap-static.xml",
        "https://example.com/sitemap-properties.xml",
        "https://example.com/sitemap-cities.xml",
        "https://example.com/sitemap-locations.xml",
        "https://example.com/sitemap-blog.xml",
    ]
    assert body["summary"]["location_landing_pages"] >= 15
    assert body["summary"]["blog_posts"] >= 11
    assert body["summary"]["blog_authors"] >= 2
    assert body["critical"] == []
    assert body["high"] == []
    assert body["low"][0]["issue"] == "frontend_audit_required"


def test_property_metadata_includes_property_faq_breadcrumbs_and_primary_image():
    response = client.get(
        "/api/v1/seo/metadata",
        params={"path": "/properties/pg/sunrise-pg-koramangala"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["canonical"] == "https://example.com/properties/pg/sunrise-pg-koramangala"
    assert body["open_graph"]["og:image"] == "https://cdn.example.com/sunrise.jpg"
    assert body["twitter"]["twitter:image"] == "https://cdn.example.com/sunrise.jpg"
    assert [crumb["name"] for crumb in body["breadcrumbs"]] == ["Home", "PG", "Sunrise PG"]
    schema_types = [schema["@type"] for schema in body["json_ld"]]
    assert "Accommodation" in schema_types
    assert "FAQPage" in schema_types
    assert body["rich_results_validation"]["valid"] is True
    assert any(link["reason"] == "related_blog" for link in body["related_blogs"])


def test_location_metadata_includes_enterprise_schema_and_internal_links():
    response = client.get("/api/v1/seo/metadata", params={"path": "/locations/pg/bellandur"})

    assert response.status_code == 200
    body = response.json()
    assert body["canonical"] == "https://example.com/locations/pg/bellandur"
    assert body["title"].startswith("PG in Bellandur")
    schema_types = [schema["@type"] for schema in body["json_ld"]]
    assert schema_types == [
        "Organization",
        "BreadcrumbList",
        "FAQPage",
        "LocalBusiness",
        "CollectionPage",
    ]
    assert body["rich_results_validation"]["valid"] is True
    link_reasons = {link["reason"] for link in body["internal_links"]}
    assert {"featured_property", "nearby_area", "blog", "popular_search", "related_city"} <= link_reasons


def test_location_page_payload_contains_required_local_sections():
    response = client.get("/api/v1/seo/location-page", params={"path": "/locations/pg/bellandur"})

    assert response.status_code == 200
    body = response.json()
    sections = body["sections"]
    for key in [
        "nearby_tech_parks",
        "nearby_metro",
        "nearby_bus_stops",
        "schools",
        "hospitals",
        "restaurants",
        "shopping",
        "gyms",
        "parks",
        "safety",
        "nightlife",
        "cost_of_living",
        "rental_trends",
        "popular_property_types",
    ]:
        assert key in sections
    assert body["featured_properties"][0]["name"] == "Bellandur Nest PG"
    assert body["map"]["query"] == "Bellandur Bangalore"


def test_blog_metadata_includes_article_schema_and_content_platform_fields():
    response = client.get(
        "/api/v1/seo/metadata",
        params={"path": "/blog/bellandur-area-guide-pg-coliving-1-bhk"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["canonical"] == "https://example.com/blog/bellandur-area-guide-pg-coliving-1-bhk"
    assert body["open_graph"]["og:type"] == "article"
    schema_types = [schema["@type"] for schema in body["json_ld"]]
    assert schema_types == [
        "Organization",
        "BreadcrumbList",
        "FAQPage",
        "Article",
        "ImageObject",
        "Person",
        "WebPage",
    ]
    assert body["rich_results_validation"]["valid"] is True
    page = body["page"]
    assert page["category"]["name"] == "Area Guides"
    assert page["reading_time_minutes"] >= 4
    assert page["table_of_contents"]
    assert page["share_links"]["linkedin"].startswith("https://www.linkedin.com")
    reasons = {link["reason"] for link in page["internal_links"]}
    assert {"related_property", "location_page", "related_post", "popular_search"} <= reasons


def test_blog_index_supports_search_pagination_categories_and_tags():
    response = client.get("/api/v1/seo/blog", params={"q": "Bellandur", "page": 1, "page_size": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["total"] >= 1
    assert body["items"][0]["url"].startswith("https://example.com/blog/")
    assert "Area Guides" in body["categories"]
    assert "bellandur" in body["tags"]


def test_blog_post_payload_exposes_ai_content_engine_outputs():
    response = client.get(
        "/api/v1/seo/blog-post",
        params={"path": "/blog/moving-to-bangalore-rental-pg-guide"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_content"]["faq_generation"]
    assert body["ai_content"]["area_guide"]
    assert body["ai_content"]["property_tips"]
    assert body["ai_content"]["rental_guide"]
    assert body["ai_content"]["commute_guide"]
    assert body["ai_content"]["lifestyle_guide"]


def test_rich_results_endpoint_returns_schema_validation_summary():
    response = client.get(
        "/api/v1/seo/rich-results",
        params={"path": "/properties/pg/sunrise-pg-koramangala"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["schema_types"] == [
        "Organization",
        "WebSite",
        "BreadcrumbList",
        "Accommodation",
        "FAQPage",
    ]
