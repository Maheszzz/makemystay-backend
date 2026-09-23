import asyncio
from app.configs.db_config import SessionLocal
from app.models.realty import Property, PropertyImage

def cleanup_primaries():
    db = SessionLocal()
    props = db.query(Property).filter(Property.is_deleted == False).all()
    
    # User's explicitly chosen primary images for known duplicates
    chosen_primaries = {
        215: 1552,
        358: 3781,
        359: 3801,
        361: 3831
    }
    
    modified_count = 0

    for p in props:
        images = [img for img in p.images if not img.is_deleted]
        if not images:
            continue
            
        primary_images = [img for img in images if img.is_primary]
        
        # Rule 1: Zero primary images -> make the first active image primary
        if len(primary_images) == 0:
            first_image = images[0]
            first_image.is_primary = True
            db.add(first_image)
            modified_count += 1
            print(f"Fixed Property {p.id}: Set Image {first_image.id} as primary (previously 0 primaries)")
            
        # Rule 2: Multiple primary images
        elif len(primary_images) > 1:
            # If the user specified which one to keep, use it. Otherwise, use the first one.
            chosen_id = chosen_primaries.get(p.id, primary_images[0].id)
            
            for img in primary_images:
                if img.id == chosen_id:
                    img.is_primary = True
                else:
                    img.is_primary = False
                db.add(img)
            
            modified_count += 1
            print(f"Fixed Property {p.id}: Kept Image {chosen_id} as primary, set others to False")

    if modified_count > 0:
        db.commit()
        print(f"Successfully cleaned up {modified_count} properties.")
    else:
        print("No duplicate or missing primaries found.")

if __name__ == "__main__":
    cleanup_primaries()
