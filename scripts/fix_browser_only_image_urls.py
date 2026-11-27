"""
Find (and optionally remove) property images saved with browser-only URLs.

When a photo upload failed, older admin builds saved the browser's temporary preview
address (blob:https://admin.makemystay.ai/...) instead of an S3/CloudFront URL.
Those images can never load (CloudFront answers 403). This script lists them so the
photos can be re-uploaded, and with --apply deletes the broken rows and strips them
from properties.metadata.uploaded_images.

Usage (from the repo root, with the usual .env / DB tunnel):
    python scripts/fix_browser_only_image_urls.py            # report only
    python scripts/fix_browser_only_image_urls.py --apply    # delete broken rows
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import or_  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.configs.db_config import MySQLSessionLocal  # noqa: E402
from app.models.realty import Property, PropertyImage  # noqa: E402

LOCAL_PREFIXES = ("blob:", "data:")


def is_local(url) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(LOCAL_PREFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="delete broken image rows and clean metadata")
    args = parser.parse_args()

    db = MySQLSessionLocal()
    try:
        bad_rows = (
            db.query(PropertyImage)
            .filter(or_(PropertyImage.image_url.like("blob:%"), PropertyImage.image_url.like("data:%")))
            .all()
        )
        by_property: dict = {}
        for row in bad_rows:
            by_property.setdefault(row.property_id, 0)
            by_property[row.property_id] += 1

        meta_fixes = []
        for prop in db.query(Property).filter(Property.metadata_json.isnot(None)).all():
            meta = prop.metadata_json if isinstance(prop.metadata_json, dict) else None
            imgs = (meta or {}).get("uploaded_images")
            if isinstance(imgs, list):
                bad = [i for i in imgs if isinstance(i, dict) and is_local(i.get("public_url"))]
                if bad:
                    meta_fixes.append((prop, bad))
                    by_property.setdefault(prop.id, 0)

        if not by_property:
            print("No browser-only image URLs found.")
            return

        names = {p.id: p.property_name for p in db.query(Property).filter(Property.id.in_(list(by_property))).all()}
        print(f"{len(bad_rows)} broken image row(s); {len(meta_fixes)} propert(ies) with broken gallery entries:\n")
        for pid in sorted(by_property):
            print(f"  #{pid:<6} {names.get(pid, '?')}  ({by_property[pid]} image row(s))")

        if not args.apply:
            print("\nReport only. Re-run with --apply to delete these rows, then re-upload the photos in the admin.")
            return

        for row in bad_rows:
            db.delete(row)
        for prop, bad in meta_fixes:
            meta = dict(prop.metadata_json)
            meta["uploaded_images"] = [i for i in meta["uploaded_images"] if i not in bad]
            prop.metadata_json = meta
            flag_modified(prop, "metadata_json")
        db.commit()
        print(f"\nDeleted {len(bad_rows)} image row(s) and cleaned {len(meta_fixes)} gallery list(s).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
