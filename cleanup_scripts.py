import os
import glob

def cleanup():
    print("🧹 Cleaning up temporary scripts...")
    patterns = [
        "populate_*.py",
        "update_*_bulk.py",
        "delete_properties.py",
        "clean_*.py",
        "add_heaven_homes.py",
        "add_features_column.py",
        "list_all_props.py",
        "recreate_missing_props.py",
        "restore_connect_properties.py",
        "fix_connect_coliving.py",
        "force_update_connect_image.py",
        "link_images.py", # Keeping this one might be useful? No, user has specific script now.
        "import_properties.py",
        "insert_bulk_properties.py",
        "debug_broken_image.py",
        "verify_prod_db.py",
        "test_*.py" # Careful with tests
    ]
    
    # Specific list to be safe
    files_to_remove = [
        "populate_content.py",
        "populate_all_content_final.py",
        "populate_missing_content.py",
        "populate_missing_ids.py",
        "update_properties_bulk.py",
        "update_bulk_properties.py",
        "delete_properties.py",
        "clean_and_update_db.py",
        "clean_description_text.py",
        "add_heaven_homes.py",
        "add_features_column.py",
        "list_all_props.py",
        "recreate_missing_props.py",
        "restore_connect_properties.py",
        "fix_connect_coliving.py",
        "force_update_connect_image.py",
        "debug_broken_image.py"
    ]

    for file in files_to_remove:
        try:
            if os.path.exists(file):
                os.remove(file)
                print(f"   🗑️ Removed {file}")
            else:
                print(f"   ⚠️ {file} not found")
        except Exception as e:
            print(f"   ❌ Error removing {file}: {e}")

    print("\n✨ Cleanup complete!")

if __name__ == "__main__":
    cleanup()
