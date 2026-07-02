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

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.seo import seo_router
from app.configs.db_config import get_mysql_db
from app.models.realty import Property
from app.configs.db_config import MySQLBase


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
    db.query(Property).delete()
    db.add(
        Property(
            property_name="Sunrise PG",
            location="Koramangala",
            city="bangalore",
            property_type="PG",
            listing_type="rent",
            starting_price=12000,
            slug="sunrise-pg-koramangala",
            is_available=True,
            is_deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
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
    assert "Disallow: /api/" in response.text
    assert "Sitemap: https://example.com/sitemap.xml" in response.text


def test_sitemap_includes_public_and_available_canonical_property_urls():
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<loc>https://example.com/</loc>" in response.text
    assert "<loc>https://example.com/properties/pg/sunrise-pg-koramangala</loc>" in response.text
    assert "hidden-flat-indiranagar" not in response.text


def test_url_audit_reports_canonical_redirect_hints():
    response = client.get("/api/v1/seo/url-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["indexed_property_urls"] == 1
    assert body["issues"] == []
    assert body["canonical_redirect_hints"][0]["to"] == (
        "https://example.com/properties/pg/sunrise-pg-koramangala"
    )
