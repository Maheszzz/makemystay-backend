"""Expand user search tokens with nearby localities and landmark → area aliases."""

from __future__ import annotations

from typing import Iterable, List, Set

# Locality ↔ nearby areas (Bangalore PG market)
NEARBY_MAPPING: dict[str, list[str]] = {
    "electronic city": ["bommasandra", "chandapura", "begur", "hebbagodi"],
    "bommasandra": ["electronic city", "chandapura", "hebbagodi"],
    "hsr layout": ["koramangala", "btm layout", "bellandur", "bommanahalli"],
    "koramangala": ["hsr layout", "btm layout", "indiranagar", "ejipura"],
    "whitefield": ["marathahalli", "bellandur", "mahadevapura", "itpl", "brookefield"],
    "marathahalli": ["whitefield", "bellandur", "kadubeesanahalli", "munnekollal", "kundalahalli"],
    "indiranagar": ["koramangala", "domlur", "hal", "cv raman nagar"],
    "btm layout": ["hsr layout", "koramangala", "jayanagar", "jp nagar"],
    "jayanagar": ["btm layout", "jp nagar", "basavanagudi", "banashankari"],
    "jp nagar": ["jayanagar", "btm layout", "bannerghatta road", "banashankari"],
}

# Landmarks / tech parks → listing localities (MakeMyStay PG near-* hubs)
LANDMARK_ALIASES: dict[str, list[str]] = {
    "ecospace": ["bellandur", "sarjapur", "sarjapur road"],
    "rmz ecoworld": ["bellandur"],
    "rmz": ["bellandur"],
    "wipro": ["electronic city", "bommasandra"],
    "electronic city phase": ["electronic city", "bommasandra"],
    "manyata": ["hebbal", "nagawara"],
    "manyata tech": ["hebbal"],
    "itpl": ["whitefield", "brookefield", "kadugodi"],
    "brookefield": ["whitefield", "itpl"],
    "embassy tech": ["bellandur"],
    "prestige tech": ["marathahalli", "kundalahalli"],
    "bagmane": ["cv raman nagar", "indiranagar"],
    "intel": ["bellandur", "sarjapur"],
    "google": ["bellandur", "kadubeesanahalli"],
    "amazon": ["bellandur", "haralur"],
    "flipkart": ["koramangala", "btm layout"],
    "mg road": ["mg road", "brigade road", "shivajinagar"],
    "forum mall": ["koramangala"],
    "phoenix": ["whitefield", "mahadevapura"],
    "metro": ["indiranagar", "mg road"],
}


def _add_neighbors(terms: Set[str], token: str) -> None:
    token = token.strip().lower()
    if not token:
        return
    terms.add(token)
    
    if len(token) < 3:
        return
        
    for key, neighbors in NEARBY_MAPPING.items():
        if key == token or token in key.split() or key in token:
            terms.update(neighbors)
    for key, aliases in LANDMARK_ALIASES.items():
        if key == token or token in key.split() or key in token:
            terms.update(aliases)


def expand_search_terms(parts: Iterable[str]) -> List[str]:
    """Unique lowercase search tokens including nearby localities and landmark aliases."""
    terms: Set[str] = set()
    for part in parts:
        raw = (part or "").strip().lower()
        if not raw:
            continue
        _add_neighbors(terms, raw)
    return sorted(terms)
