from typing import Optional

# Mapping of sub-localities to their parent cities.
# Based on pg-locations.json
LOCALITY_TO_CITY = {
    # Bangalore Localities
    "whitefield": "bangalore",
    "marathahalli": "bangalore",
    "btm": "bangalore",
    "btm layout": "bangalore",
    "electronic city": "bangalore",
    "indiranagar": "bangalore",
    "koramangala": "bangalore",
    "hsr layout": "bangalore",
    "bellandur": "bangalore",
    "sarjapur": "bangalore",
    "sarjapur road": "bangalore",
    "hebbal": "bangalore",
    "yelahanka": "bangalore",
    "kr puram": "bangalore",
    "banaswadi": "bangalore",
    "ramamurthy nagar": "bangalore",
    "cv raman nagar": "bangalore",
    "malleshwaram": "bangalore",
    "rajajinagar": "bangalore",
    "vijayanagar": "bangalore",
    "basavanagudi": "bangalore",
    "jayanagar": "bangalore",
    "jp nagar": "bangalore",
    "banashankari": "bangalore",
    "uttarahalli": "bangalore",
    "kengeri": "bangalore",
    "rr nagar": "bangalore",
    "nayandahalli": "bangalore",
    "mysore road": "bangalore",
    "magadi road": "bangalore",
    "tumkur road": "bangalore",
    "nelamangala": "bangalore",
    "hosur road": "bangalore",
    "bommanahalli": "bangalore",
    "silk board": "bangalore",
    "domlur": "bangalore",
    "ulsoor": "bangalore",
    "frazer town": "bangalore",
    "shivajinagar": "bangalore",
    "richmond town": "bangalore",
    "mg road": "bangalore",
    "brigade road": "bangalore",
    "sadashivanagar": "bangalore",
    "rt nagar": "bangalore",
    "sanjay nagar": "bangalore",
    "new bel road": "bangalore",
    "mathikere": "bangalore",
    "yeshwanthpur": "bangalore",
    "peenya": "bangalore",
    "jalahalli": "bangalore",
    "vidyaranyapura": "bangalore",
    "bagalur": "bangalore",
    "bannerghatta road": "bangalore",
    "kadugodi": "bangalore",
    "brookefield": "bangalore",
    "hoodi": "bangalore",
    "mahadevapura": "bangalore",
    "aecs layout": "bangalore",
    "itpl": "bangalore",
    "munnekolala": "bangalore",
    "kundalahalli": "bangalore",
    "varthur": "bangalore",
    "panathur": "bangalore",
    "kaikondrahalli": "bangalore",
    "kasavanahalli": "bangalore",
    "haralur": "bangalore",
    "akshaya nagar": "bangalore",
    "begur": "bangalore",
    "hulimavu": "bangalore",
    "gottigere": "bangalore",
    "arekere": "bangalore",
    "bilekahalli": "bangalore",
    "tavarekere": "bangalore",
    "ejipura": "bangalore",
    "koramangala 4th block": "bangalore",
    "koramangala 1st block": "bangalore",
    "hebbal kempapura": "bangalore",
    # Aliases / common typos in imported listings
    "munnekollal": "bangalore",
    "silkboard": "bangalore",
    "whitefeild": "bangalore",
    "kadubeesanahalli": "bangalore",
    "kadubesanahalli": "bangalore",
    "kodbisanhalli": "bangalore",
    "madiwala": "bangalore",
    "marathalli": "bangalore",
    "doddanekkundi": "bangalore",
    "bommasandra": "bangalore",
    "halasuru": "bangalore",
    "hosapalaya": "bangalore",
    "garvebhavi": "bangalore",
    "garvebhavi palya": "bangalore",
    "pattandur": "bangalore",
    "pattandur agrahara": "bangalore",
    "shajapur": "bangalore",
    "embassy tech": "bangalore",
    "embassy tec": "bangalore",
    "neeladri": "bangalore",
    "beml layout": "bangalore",
    "brigade tech": "bangalore",
    "new tippasandra": "bangalore",
    "tippasandra": "bangalore",
    "aecs": "bangalore",
    "e city": "bangalore",
    "ecity": "bangalore",
    "chandapura": "bangalore",
    "hebbagodi": "bangalore",
    "muneshwara nagar": "bangalore",
    "kammanahalli": "bangalore",
    "kalyan nagar": "bangalore",
    "gunjur": "bangalore",
    "murugeshpalya": "bangalore",
    "kaggadasapura": "bangalore",
    "gm palya": "bangalore",

    # Hyderabad Localities
    "hitech city": "hyderabad",
    "gachibowli": "hyderabad",
    "kondapur": "hyderabad",
    "madhapur": "hyderabad",
    "kukatpally": "hyderabad",

    # Pune Localities
    "hinjewadi": "pune",
    "kharadi": "pune",
    "wakad": "pune",
    "viman nagar": "pune",
    "baner": "pune",
}

def find_city_for_location(location: Optional[str]) -> Optional[str]:
    """
    Attempts to find a parent city for a given location string.
    Returns normalized city name (e.g., 'bangalore') or None.
    """
    if not location or not str(location).strip():
        return None
    
    norm = str(location).lower().strip()
    
    # 1. Direct match with a major city
    if "bengaluru" in norm:
        return "bangalore"
    for city in ["bangalore", "hyderabad", "pune"]:
        if city in norm:
            return city
            
    # 2. Check for sub-localities
    # Sort keys by length descending to match longest locality first
    sorted_localities = sorted(LOCALITY_TO_CITY.keys(), key=len, reverse=True)
    for loc in sorted_localities:
        if loc in norm:
            return LOCALITY_TO_CITY[loc]
            
    return None

def get_localities_for_city(city: str) -> list[str]:
    """Returns a list of sub-localities for a given parent city."""
    c = city.lower().strip()
    return [loc for loc, parent in LOCALITY_TO_CITY.items() if parent == c]
