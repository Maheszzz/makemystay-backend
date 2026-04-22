import os
import sys

# Add app to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.city_mapping import find_city_for_location, get_localities_for_city

def test_city_mapping():
    print("🧪 Testing City Mapping...")
    
    # Test cases: (location, expected_city)
    cases = [
        ("Whitefield, Bangalore", "bangalore"),
        ("BTM Layout", "bangalore"),
        ("HSR Layout, Sector 7", "bangalore"),
        ("HiTech City, Hyderabad", "hyderabad"),
        ("Kukatpally", "hyderabad"),
        ("Hinjewadi Phase 1", "pune"),
        ("Wakad", "pune"),
        ("New York", None),
        ("", None),
    ]
    
    results = []
    for loc, expected in cases:
        actual = find_city_for_location(loc)
        status = "✅" if actual == expected else "❌"
        print(f"  {status} Location: '{loc}' -> Expected: {expected}, Actual: {actual}")
        results.append(actual == expected)
        
    bangalore_localities = get_localities_for_city("bangalore")
    print(f"\n📍 Bangalore sub-localities found: {len(bangalore_localities)}")
    
    if all(results):
        print("\n✨ All city mapping tests PASSED!")
    else:
        print("\n❌ One or more tests FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    test_city_mapping()
