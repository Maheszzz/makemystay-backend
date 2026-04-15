"""
Server-generated long-form copy for property PDPs (~500 words), SEO-oriented, unique per listing via live data.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence

# Target band for total word count (user request: ~500 words for all listings).
_TARGET = 500
_MIN = 480
_MAX = 560


def _word_count(text: str) -> int:
    if not text or not text.strip():
        return 0
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _clean_html(text: Optional[str]) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(text))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _limit_words(text: str, max_words: int) -> str:
    words = re.findall(r"[A-Za-z0-9']+|[.,!?;:()\[\]\"'`—–-]", text)
    # Simpler: split on whitespace
    w = text.split()
    if len(w) <= max_words:
        return text
    return " ".join(w[:max_words]).rstrip(",;:") + "…"


def _fmt_inr(amount: Optional[Any]) -> str:
    if amount is None:
        return ""
    try:
        n = float(amount)
        if n <= 0:
            return ""
        # Indian-style grouping
        s = f"{int(round(n)):,}"
        return f"₹{s}"
    except (TypeError, ValueError):
        return ""


def _feature_list(property_obj: Any) -> List[str]:
    raw = getattr(property_obj, "features", None)
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def build_property_seo_about(property_obj: Any, target_words: int = _TARGET) -> str:
    """
    Build ~500 words of unique, crawlable copy using name, location, type, price, features, and listing notes.
    """
    name = (getattr(property_obj, "property_name", None) or "This listing").strip()
    loc = (getattr(property_obj, "location", None) or "Bangalore").strip()
    pt = (getattr(property_obj, "property_type", None) or "property").strip()
    listing = (getattr(property_obj, "listing_type", None) or "rent").lower()
    furn = (getattr(property_obj, "furnishing", None) or "fully_furnished")
    if hasattr(furn, "value"):
        furn = str(furn.value)
    furn_h = furn.replace("_", " ").lower()

    price = _fmt_inr(getattr(property_obj, "starting_price", None))
    priv = _fmt_inr(getattr(property_obj, "private_price", None))
    price_phrase = ""
    if listing == "buy":
        if priv:
            price_phrase = f"The listed price guidance starts around {priv}."
        elif price:
            price_phrase = f"Pricing is indicated from {price} onward for serious buyers."
        else:
            price_phrase = "Pricing is shared transparently on enquiry for qualified buyers."
    else:
        if price:
            price_phrase = f"Rental is positioned from {price} per month for the configured inventory, subject to room type and occupancy."
        elif priv:
            price_phrase = f"Monthly rent is typically discussed around {priv}, depending on configuration."
        else:
            price_phrase = "Monthly rent and inclusions are confirmed on enquiry so you can compare fairly against nearby options."

    avail = getattr(property_obj, "is_available", True)
    avail_phrase = (
        "The listing is marked available for enquiries and visits."
        if avail
        else "Availability can change quickly in popular micro-markets — confirm the latest status before planning a visit."
    )

    feats = _feature_list(property_obj)
    feat_sample = ", ".join(feats[:12]) if feats else "modern fixtures, power backup, and security-conscious access"
    feat_tail = ""
    if len(feats) > 12:
        feat_tail = f" Additional on-site amenities include {', '.join(feats[12:20])}."
    elif not feats:
        feat_tail = " Detailed amenity tags are maintained on the listing so you can match expectations before you visit."

    desc_raw = _clean_html(getattr(property_obj, "description", None))
    listing_notes = ""
    if desc_raw and len(desc_raw) > 40:
        excerpt = _limit_words(desc_raw, 130)
        listing_notes = (
            f"\n\nWhat the operator highlights: {excerpt}"
        )

    pt_l = pt.lower()
    is_pg = pt_l == "pg"
    is_plot = pt_l == "plot"

    if is_plot:
        body = _build_plot_narrative(name, loc, price_phrase, listing_notes, avail_phrase)
    elif is_pg:
        body = _build_pg_narrative(
            name, loc, pt, price_phrase, feat_sample, feat_tail, listing_notes, avail_phrase, furn_h
        )
    else:
        body = _build_home_narrative(
            name, loc, pt, listing, price_phrase, feat_sample, feat_tail, listing_notes, avail_phrase, furn_h
        )

    # Trim or pad to band
    wc = _word_count(body)
    if wc > _MAX:
        body = _limit_words(body, _MAX)
    elif wc < _MIN:
        pad = _padding_sentences(name, loc, pt, target_words=_MIN - wc)
        body = body.rstrip() + "\n\n" + pad

    # Final guardrail
    if _word_count(body) > _MAX:
        body = _limit_words(body, _MAX)
    return body.strip()


def _build_pg_narrative(
    name: str,
    loc: str,
    pt: str,
    price_phrase: str,
    feat_sample: str,
    feat_tail: str,
    listing_notes: str,
    avail_phrase: str,
    furn_h: str,
) -> str:
    return f"""**{name}** is a professionally managed **{pt}** in **{loc}**, structured for renters who want predictable monthly costs, daily meals or kitchen access (where applicable), and community-style living near Bangalore's employment corridors. {price_phrase} {avail_phrase}

When you evaluate paying-guest accommodation, the real comparison is not just headline rent but what is bundled: Wi‑Fi uptime, meal timings, housekeeping frequency, laundry options, and visitor policies. This listing is presented on MakeMyStay with structured fields so you can shortlist faster and ask sharper questions on your call or visit. Typical PG searches in {loc} combine keywords such as "PG near me", "coliving {loc}", "single occupancy PG", and "food included PG Bangalore" — this page is written to answer those intents with specific, verifiable details rather than generic filler.{listing_notes}

Amenities called out for this property include {feat_sample}.{feat_tail} If something matters for your routine — for example, night-shift friendly meal windows, biometric access, or dedicated study corners — use the enquiry flow to confirm operational rules with the operator.

Location-wise, {loc} remains one of Bangalore's active rental pockets, with demand from students, exam-prep residents, and early-career professionals who prioritize shorter commutes and safer night-time access. Many renters also compare PG offers against shared flats; the trade-off is usually bundled services versus extra flexibility. A PG wins when you want fewer household decisions and clearer monthly math.

From an SEO and discovery perspective, this page includes natural references to **Bangalore**, **{loc}**, **{pt} rental**, furnished stay, and verified listing context, because search engines and users alike reward pages that explain the offer plainly. You can cross-check photos, map links (when published), and ratings before paying any token.

MakeMyStay focuses on reducing broker noise: you see structured pricing signals, availability cues, and a consistent enquiry path across listings. Whether you are relocating from another city or switching micro-neighbourhoods within Bangalore, start by confirming deposit, notice period, and inclusions in writing.

Finally, booking discipline matters in high-churn corridors. If the room type you want is single occupancy or AC, ask what is allocated today — inventory moves weekly. Use this long-form guide as a checklist, then schedule a visit to validate lighting, ventilation, phone signal, and water pressure in person. Small details decide whether a place feels livable for months, not just photogenic for minutes."""


def _build_home_narrative(
    name: str,
    loc: str,
    pt: str,
    listing: str,
    price_phrase: str,
    feat_sample: str,
    feat_tail: str,
    listing_notes: str,
    avail_phrase: str,
    furn_h: str,
) -> str:
    rent_or_sale = "for rent" if listing != "buy" else "for sale"
    if "bhk" in pt.lower() or (pt or "").upper() in ("1RK", "1BHK", "2BHK", "3BHK", "4BHK"):
        unit_phrase = f"a **{pt}** home"
    else:
        unit_phrase = f"a **{pt}** property"

    return f"""**{name}** brings {unit_phrase} {rent_or_sale} in **{loc}**, aimed at renters and buyers who want a clear narrative before they shortlist visits. {price_phrase} {avail_phrase}

Urban housing search in Bangalore often stacks multiple intents: "fully furnished {pt} {loc}", "family {pt} near tech park", "no brokerage flat {loc}", and "ready-to-move {pt} Bangalore". This description is composed to surface those semantic signals while staying readable — search engines reward helpful, specific copy, and so do users comparing five tabs at once.{listing_notes}

The home is described as **{furn_h}**, which should set expectations on fixtures, wardrobes, and kitchen usability. Feature highlights include {feat_sample}.{feat_tail} For families, check schools and clinics nearby; for professionals, validate peak-hour routes to your office cluster.

Bellandur, Whitefield, HSR, Koramangala, and similar hubs each have different traffic patterns — {loc} has its own rhythm of metro access, ORR connectivity, and last-mile autos. Mention commute time honestly in your notes when you enquire so the operator can suggest the best unit orientation or floor.

Legal and commercial hygiene still matters: ask for owner documentation visibility, society NOC if applicable, maintenance splits, and what the monthly outflow truly is after utilities. MakeMyStay presents listings with verification cues where available; your final diligence happens on conversation and site visit.

From a content standpoint, long-form property pages help Google understand entities (project name + locality + configuration) and help users skim for decision criteria: budget fit, furnishing, security, parking, and timeline. This page intentionally repeats a few key phrases in natural contexts rather than stuffing keywords awkwardly.

If you are deciding between a slightly smaller furnished unit and a larger semi-furnished one, model the move-in cost: transportation, minor purchases, and brokerage if any. Our marketplace bias is transparency — you should leave the page knowing what to ask next.

Schedule a walkthrough to judge daylight, storage, and noise. Photos rarely capture lift wait times or balcony airflow. When you are ready, use the on-page actions to book a visit or call, and keep a checklist of must-haves so you can compare apples to apples across listings in {loc} and nearby pin codes."""

def _build_plot_narrative(
    name: str,
    loc: str,
    price_phrase: str,
    listing_notes: str,
    avail_phrase: str,
) -> str:
    return f"""**{name}** is a land listing in **{loc}**, positioned for buyers evaluating plot investments, self-build roadmaps, or long-hold appreciation plays around Bangalore's growth corridors. {price_phrase} {avail_phrase}

Plot purchases require a different diligence frame than flats: dimensions, facing, road width, approvals, zoning, and encumbrance checks. This page uses long-form SEO text so you can discover the listing via searches like "plot in {loc}", "Bangalore land for sale", and "approved layout {loc}" while still getting human-readable context.{listing_notes}

Use map and survey references early, and insist on lawyer-reviewed documents before token advances. MakeMyStay can facilitate structured enquiries; however, legal verification remains the buyer's responsibility with qualified counsel.

Infrastructure timing matters: water, electricity, and internal roads should be validated on-site, not assumed from brochures. Compare this plot against alternate micro-locations on total cost of ownership, not sticker price alone.

Whether you plan to build soon or hold the asset, clarity on encumbrances and developer reputation reduces surprises. Treat this narrative as a starting checklist, then escalate technical questions with your advisor."""


def _padding_sentences(name: str, loc: str, pt: str, target_words: int) -> str:
    """Add varied sentences until approximate word budget is met."""
    pool: Sequence[str] = (
        f"Renters researching **{loc}** often compare multiple **{pt}** listings side by side — use price, inclusions, and commute as tie-breakers.",
        f"If **{name}** matches your budget band, the next filter is usually furnishing depth and monthly outflow after utilities.",
        "MakeMyStay continues to refine listing quality signals so organic search surfaces pages that answer real questions, not thin placeholders.",
        f"Bookmark this **{loc}** page, share it with co-decision makers, and shortlist two backups — availability in Bangalore shifts weekly.",
        "For SEO transparency: this copy is generated from structured listing data and operator notes so it stays aligned with what you see in the product.",
        "Ask about move-in timelines, maintenance escalations, and visitor rules before you transfer a booking amount.",
        f"Neighbourhood keywords people use alongside **{loc}** include nearby tech parks, schools, hospitals, and metro phases — map your priorities accordingly.",
    )
    chunks: List[str] = []
    i = 0
    while _word_count(" ".join(chunks)) < target_words and i < len(pool) * 3:
        chunks.append(pool[i % len(pool)])
        i += 1
    text = " ".join(chunks)
    return _limit_words(text, max(target_words + 40, _word_count(text)))

