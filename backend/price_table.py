"""
Price table matching engine.
Takes extracted work items from Gemini and matches them to the
handyman's price table using keyword similarity.
"""

import re
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    """Normalize text for matching (lowercase, strip, remove common noise)."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def keyword_overlap(description_a: str, description_b: str) -> float:
    """Score how well two descriptions match based on keyword overlap."""
    a_words = set(normalize(description_a).split())
    b_words = set(normalize(description_b).split())

    # Remove very short words
    a_words = {w for w in a_words if len(w) > 2}
    b_words = {w for w in b_words if len(w) > 2}

    if not a_words or not b_words:
        return 0.0

    intersection = a_words & b_words
    # Score: harmonic mean of precision and recall
    precision = len(intersection) / len(a_words) if a_words else 0
    recall = len(intersection) / len(b_words) if b_words else 0
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def find_best_match(description: str, services: list[dict]) -> dict | None:
    """
    Find the best matching service in the price table for a description.
    Returns the service dict with an added 'match_score' field, or None if no match.
    """
    if not services:
        return None

    best = None
    best_score = 0.0

    for svc in services:
        score = keyword_overlap(description, svc.get("description", ""))
        if score > best_score:
            best_score = score
            best = svc

    # Threshold: require at least 0.3 overlap
    if best_score >= 0.3:
        result = dict(best)
        result["match_score"] = round(best_score, 3)
        return result
    return None


def match_items(
    extracted_items: list[dict],
    price_table: dict,
) -> list[dict]:
    """
    Match extracted work items to price table services.
    Returns items with prices filled in where matched.
    Unmatched items keep their original data.
    """
    services = price_table.get("standard_services", [])
    hourly_rate = price_table.get("hourly_rate", 0)
    materials_markup = price_table.get("materials_markup", 1.0)

    results = []

    for item in extracted_items:
        desc = item.get("beschreibung", "")

        # Try to find a match
        match = find_best_match(desc, services)

        if match:
            results.append({
                "beschreibung": f"{item['beschreibung']} (lt. Preisliste)",
                "menge": item.get("menge", 1),
                "einheit": match["unit"],
                "einzelpreis_netto": match["price"],
                "match_source": "price_table",
            })
        elif item.get("category") == "material" or "Material" in item.get("beschreibung", ""):
            # Material with markup
            results.append({
                "beschreibung": item["beschreibung"],
                "menge": item.get("menge", 1),
                "einheit": "pauschal",
                "einzelpreis_netto": round(item.get("einzelpreis_netto", 0) * materials_markup, 2),
                "match_source": "materials_markup",
            })
        else:
            # Unmatched - keep as-is (Gemini's estimate)
            results.append({
                "beschreibung": item["beschreibung"],
                "menge": item.get("menge", 1),
                "einheit": item.get("einheit", "h" if hourly_rate else "Stk"),
                "einzelpreis_netto": item.get("einzelpreis_netto", hourly_rate),
                "match_source": "llm_estimate",
            })

    return results