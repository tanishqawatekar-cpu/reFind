"""
ReFind — Rule-Based Matching Engine (0–100 Score Calculation)
Evaluates Lost & Found item pairs across 5 weighted criteria:
  1. Category Compatibility       (0 - 30 points)
  2. Item Name & Brand Similarity (0 - 25 points)
  3. Campus Location Proximity    (0 - 20 points)
  4. Date Compatibility           (0 - 15 points)
  5. Description Keyword Overlap  (0 - 10 points)
Total Possible Score = 100.00 points
"""

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from database.db import query_all, db_transaction, log_activity

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "my", "near", "of", "on", "or", "some", "that", "the",
    "their", "there", "this", "to", "was", "were", "with", "lost", "found", "item",
    "please", "help", "around", "inside", "outside", "floor", "room", "college", "campus"
}

CAMPUS_ZONES = {
    "library": ["library", "reading room", "central library", "digital library", "study hall"],
    "canteen": ["canteen", "cafeteria", "food court", "mess", "coffee", "nescafe", "amul"],
    "academic_a": ["block a", "a block", "main building", "admin block", "dean office"],
    "academic_b": ["block b", "b block", "cs department", "computer lab", "it lab", "lab 1", "lab 2", "lab 3"],
    "academic_c": ["block c", "c block", "electronics lab", "mechanical workshop", "drawing hall"],
    "auditorium": ["auditorium", "seminar hall", "amphitheatre", "main stage", "convocation"],
    "sports": ["sports", "gymkhana", "ground", "basketball", "football", "cricket", "badminton", "gym"],
    "hostel": ["hostel", "boys hostel", "girls hostel", "warden", "common room"],
    "parking": ["parking", "main gate", "gate 1", "gate 2", "bike stand", "bus stop", "corridor"],
}

RELATED_CATEGORIES = {
    ("Bags & Wallets", "ID & Cards"),
    ("ID & Cards", "Bags & Wallets"),
    ("Electronics", "Keys & Accessories"),
    ("Keys & Accessories", "Electronics"),
    ("Bags & Wallets", "Keys & Accessories"),
    ("Keys & Accessories", "Bags & Wallets"),
}

MATCH_THRESHOLD = 35.0
HIGH_CONFIDENCE_THRESHOLD = 60.0


def tokenize(text: str) -> set[str]:
    """Extract normalized alphanumeric tokens excluding common stop words."""
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in STOP_WORDS}


def detect_campus_zones(location_text: str) -> set[str]:
    """Map free-text campus location to canonical campus zones."""
    if not location_text:
        return set()
    loc_lower = location_text.lower()
    matched_zones = set()
    for zone_name, keywords in CAMPUS_ZONES.items():
        if any(kw in loc_lower for kw in keywords):
            matched_zones.add(zone_name)
    return matched_zones


def _to_date(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def calculate_match_score(lost: dict, found: dict) -> dict:
    """
    Compute the 0–100 rule-based match score between a lost item and a found item.
    Returns a dictionary containing total score, component scores, and explanation.
    """
    reasons = []

    # -------------------------------------------------------------------------
    # 1. Category Score (Max 30 points)
    # -------------------------------------------------------------------------
    lost_cat = (lost.get("category") or "").strip()
    found_cat = (found.get("category") or "").strip()
    if lost_cat and lost_cat == found_cat:
        category_pts = 30.0
        reasons.append(f"Category: 30/30 (Exact match '{lost_cat}')")
    elif (lost_cat, found_cat) in RELATED_CATEGORIES:
        category_pts = 12.0
        reasons.append(f"Category: 12/30 (Related '{lost_cat}' & '{found_cat}')")
    else:
        category_pts = 0.0
        reasons.append("Category: 0/30 (Different categories)")

    # -------------------------------------------------------------------------
    # 2. Item Name & Brand/Color Similarity (Max 25 points)
    # -------------------------------------------------------------------------
    lost_title_tokens = tokenize(f"{lost.get('item_name', '')} {lost.get('brand_color', '')}")
    found_title_tokens = tokenize(f"{found.get('item_name', '')} {found.get('brand_color', '')}")

    shared_title = lost_title_tokens & found_title_tokens
    union_title = lost_title_tokens | found_title_tokens

    seq_ratio = SequenceMatcher(
        None,
        (lost.get("item_name") or "").lower().strip(),
        (found.get("item_name") or "").lower().strip(),
    ).ratio()

    if union_title:
        jaccard = len(shared_title) / len(union_title)
        recall = len(shared_title) / max(1, min(len(lost_title_tokens), len(found_title_tokens)))
        combined_name_sim = max(seq_ratio, (0.5 * jaccard + 0.5 * recall))
    else:
        combined_name_sim = seq_ratio

    name_pts = round(min(25.0, combined_name_sim * 25.0), 2)
    if shared_title:
        shared_str = ", ".join(sorted(list(shared_title))[:4])
        reasons.append(f"Item/Brand: {name_pts:.0f}/25 (Shared terms: {shared_str})")
    else:
        reasons.append(f"Item/Brand: {name_pts:.0f}/25 (String similarity {seq_ratio:.0%})")

    # -------------------------------------------------------------------------
    # 3. Location Proximity (Max 20 points)
    # -------------------------------------------------------------------------
    loc_lost = (lost.get("location_lost") or "").strip()
    loc_found = (found.get("location_found") or "").strip()
    zones_lost = detect_campus_zones(loc_lost)
    zones_found = detect_campus_zones(loc_found)
    loc_tokens_lost = tokenize(loc_lost)
    loc_tokens_found = tokenize(loc_found)
    shared_loc_tokens = loc_tokens_lost & loc_tokens_found

    if loc_lost and loc_found and loc_lost.lower() == loc_found.lower():
        location_pts = 20.0
        reasons.append(f"Location: 20/20 (Exact '{loc_found}')")
    elif zones_lost and (zones_lost & zones_found):
        common_zone = sorted(list(zones_lost & zones_found))[0].replace("_", " ").title()
        location_pts = 18.0 if shared_loc_tokens else 15.0
        reasons.append(f"Location: {location_pts:.0f}/20 (Same campus zone: {common_zone})")
    elif shared_loc_tokens:
        overlap_ratio = len(shared_loc_tokens) / max(1, min(len(loc_tokens_lost), len(loc_tokens_found)))
        location_pts = round(min(16.0, 8.0 + overlap_ratio * 8.0), 2)
        reasons.append(f"Location: {location_pts:.0f}/20 (Shared: {', '.join(sorted(shared_loc_tokens)[:3])})")
    else:
        location_pts = 0.0
        reasons.append("Location: 0/20 (Different campus locations)")

    # -------------------------------------------------------------------------
    # 4. Date Compatibility (Max 15 points)
    # -------------------------------------------------------------------------
    d_lost = _to_date(lost.get("date_lost"))
    d_found = _to_date(found.get("date_found"))

    if d_lost and d_found:
        day_diff = (d_found - d_lost).days
        if day_diff == 0:
            date_pts = 15.0
            reasons.append("Date: 15/15 (Found on exact same day)")
        elif 1 <= day_diff <= 2:
            date_pts = 13.0
            reasons.append(f"Date: 13/15 (Found {day_diff}d after lost)")
        elif 3 <= day_diff <= 5:
            date_pts = 10.0
            reasons.append(f"Date: 10/15 (Found {day_diff}d after lost)")
        elif 6 <= day_diff <= 14:
            date_pts = 7.0
            reasons.append(f"Date: 7/15 (Found {day_diff}d after lost)")
        elif 15 <= day_diff <= 45:
            date_pts = 4.0
            reasons.append(f"Date: 4/15 (Found {day_diff}d after lost)")
        elif day_diff == -1:
            # Allow 1-day tolerance if student estimated date_lost slightly off
            date_pts = 5.0
            reasons.append("Date: 5/15 (Within 1-day date tolerance)")
        else:
            date_pts = 0.0
            reasons.append(f"Date: 0/15 (Incompatible timeline: {day_diff}d gap)")
    else:
        date_pts = 0.0
        reasons.append("Date: 0/15 (Missing date)")

    # -------------------------------------------------------------------------
    # 5. Description & Detail Keyword Overlap (Max 10 points)
    # -------------------------------------------------------------------------
    desc_lost_tokens = tokenize(f"{lost.get('description', '')} {lost.get('brand_color', '')}")
    desc_found_tokens = tokenize(f"{found.get('description', '')} {found.get('brand_color', '')}")
    shared_desc = desc_lost_tokens & desc_found_tokens

    if shared_desc:
        desc_ratio = len(shared_desc) / max(1, min(len(desc_lost_tokens), len(desc_found_tokens)))
        description_pts = round(min(10.0, 3.0 + desc_ratio * 7.0), 2)
        sample_kw = ", ".join(sorted(list(shared_desc))[:4])
        reasons.append(f"Description: {description_pts:.0f}/10 (Keywords: {sample_kw})")
    else:
        description_pts = 0.0
        reasons.append("Description: 0/10 (No shared keywords)")

    # If the date is strictly incompatible (found >1 day before lost), cap score
    total_score = round(
        category_pts + name_pts + location_pts + date_pts + description_pts, 2
    )
    if d_lost and d_found and (d_found - d_lost).days < -1:
        total_score = round(total_score * 0.35, 2)
        reasons.append("[Timeline Penalty Applied: Found before Lost date]")

    total_score = max(0.0, min(100.0, total_score))

    return {
        "match_score": total_score,
        "category_points": category_pts,
        "name_points": name_pts,
        "location_points": location_pts,
        "date_points": date_pts,
        "description_points": description_pts,
        "score_explanation": " | ".join(reasons)[:500],
    }


def run_matching_engine(triggered_by_user_id: int | None = None) -> int:
    """
    Evaluate all active Lost & Found item pairs, persist candidate matches
    scoring >= MATCH_THRESHOLD into `matches`, and update item statuses when
    high-confidence matches are discovered.
    Returns the number of candidate matches created or updated.
    """
    lost_items = query_all(
        """
        SELECT lost_id, user_id, item_name, category, brand_color,
               location_lost, date_lost, description, status
        FROM lost_items
        WHERE status IN ('OPEN', 'MATCHED')
        """
    )
    found_items = query_all(
        """
        SELECT found_id, user_id, item_name, category, brand_color,
               location_found, date_found, description, status
        FROM found_items
        WHERE status IN ('AVAILABLE', 'MATCHED')
        """
    )

    matches_saved = 0
    with db_transaction() as (_conn, cur):
        for lost in lost_items:
            for found in found_items:
                result = calculate_match_score(lost, found)
                score = result["match_score"]
                if score < MATCH_THRESHOLD:
                    continue

                cur.execute(
                    """
                    INSERT INTO matches (
                        lost_id, found_id, match_score, score_explanation,
                        category_points, name_points, location_points,
                        date_points, description_points, match_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'SUGGESTED')
                    ON DUPLICATE KEY UPDATE
                        match_score = VALUES(match_score),
                        score_explanation = VALUES(score_explanation),
                        category_points = VALUES(category_points),
                        name_points = VALUES(name_points),
                        location_points = VALUES(location_points),
                        date_points = VALUES(date_points),
                        description_points = VALUES(description_points)
                    """,
                    (
                        lost["lost_id"],
                        found["found_id"],
                        score,
                        result["score_explanation"],
                        result["category_points"],
                        result["name_points"],
                        result["location_points"],
                        result["date_points"],
                        result["description_points"],
                    ),
                )
                matches_saved += 1

                # Promote OPEN / AVAILABLE items to MATCHED when score >= 60
                if score >= HIGH_CONFIDENCE_THRESHOLD:
                    if lost["status"] == "OPEN":
                        cur.execute(
                            "UPDATE lost_items SET status = 'MATCHED' WHERE lost_id = %s AND status = 'OPEN'",
                            (lost["lost_id"],),
                        )
                    if found["status"] == "AVAILABLE":
                        cur.execute(
                            "UPDATE found_items SET status = 'MATCHED' WHERE found_id = %s AND status = 'AVAILABLE'",
                            (found["found_id"],),
                        )

        if matches_saved > 0 and triggered_by_user_id is not None:
            log_activity(
                user_id=triggered_by_user_id,
                action_type="MATCH_GENERATED",
                entity_type="MATCH",
                entity_id=matches_saved,
                summary=f"Rule-based matching engine evaluated active items and updated {matches_saved} candidate match(es).",
                cursor=cur,
            )

    return matches_saved
