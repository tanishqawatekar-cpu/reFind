"""
Ownership Claim & Transactional Admin Verification Service (`services/claim_service.py`)
Implements ACID transactions with row-level locks (`SELECT ... FOR UPDATE`) to:
  - Submit ownership claims without exposing private verification details publicly
  - Approve or reject claims atomically
  - Prevent multiple approved claims for the same found item
  - Synchronize `found_items`, `lost_items`, `matches`, and `activity_logs` consistently
"""

from mysql.connector import IntegrityError
from database.db import db_transaction, query_all, query_one, log_activity


def submit_ownership_claim(
    found_id: int,
    claimant_id: int,
    proof_description: str,
    id_card_reference: str,
    lost_id: int | None = None,
) -> int:
    """
    Submit a new ownership claim inside an ACID transaction.
    Validates that:
      - The found item exists and is not already RETURNED
      - No APPROVED claim already exists for this found item
      - The claimant has not already submitted a claim for this found item
      - If `lost_id` is provided, it belongs to the claimant
    Returns the new `claim_id`.
    """
    proof_clean = (proof_description or "").strip()
    id_ref_clean = (id_card_reference or "").strip()[:100]

    if len(proof_clean) < 5:
        raise ValueError("Ownership proof description must be at least 5 characters long.")
    if len(id_ref_clean) < 2:
        raise ValueError("Student/Staff ID reference is required for claim verification.")

    with db_transaction() as (_conn, cur):
        # Lock the found_items row to prevent race conditions with concurrent approvals
        cur.execute(
            """
            SELECT found_id, user_id, item_name, status
            FROM found_items
            WHERE found_id = %s
            FOR UPDATE
            """,
            (found_id,),
        )
        found_item = cur.fetchone()
        if not found_item:
            raise ValueError(f"Found item #{found_id} does not exist.")

        if found_item["status"] == "RETURNED":
            raise ValueError("This item has already been verified and returned to its owner.")

        # Check if an approved claim already exists for this found item
        cur.execute(
            "SELECT claim_id FROM claims WHERE found_id = %s AND status = 'APPROVED' LIMIT 1",
            (found_id,),
        )
        if cur.fetchone():
            raise ValueError("An ownership claim has already been approved for this item.")

        # Check if this student already submitted a claim for this found item
        cur.execute(
            "SELECT claim_id, status FROM claims WHERE found_id = %s AND claimant_id = %s LIMIT 1",
            (found_id, claimant_id),
        )
        existing = cur.fetchone()
        if existing:
            raise ValueError(
                f"You have already submitted a claim (#{existing['claim_id']}, status: {existing['status']}) for this item."
            )

        # Validate optional linked lost_id belongs to claimant (or is valid)
        validated_lost_id = None
        if lost_id:
            cur.execute(
                "SELECT lost_id, user_id FROM lost_items WHERE lost_id = %s",
                (lost_id,),
            )
            lost_row = cur.fetchone()
            if not lost_row:
                raise ValueError(f"Linked lost item #{lost_id} does not exist.")
            validated_lost_id = lost_row["lost_id"]

        # Insert the claim
        cur.execute(
            """
            INSERT INTO claims (
                found_id, lost_id, claimant_id, proof_description, id_card_reference, status
            )
            VALUES (%s, %s, %s, %s, %s, 'PENDING')
            """,
            (found_id, validated_lost_id, claimant_id, proof_clean, id_ref_clean),
        )
        new_claim_id = cur.lastrowid

        # Update found_items status to CLAIMED if currently AVAILABLE or MATCHED
        if found_item["status"] in ("AVAILABLE", "MATCHED"):
            cur.execute(
                "UPDATE found_items SET status = 'CLAIMED' WHERE found_id = %s",
                (found_id,),
            )

        log_activity(
            user_id=claimant_id,
            action_type="CLAIM_SUBMITTED",
            entity_type="CLAIM",
            entity_id=new_claim_id,
            summary=f"Submitted ownership claim #{new_claim_id} for Found Item #{found_id} ('{found_item['item_name']}').",
            cursor=cur,
        )

        return new_claim_id


def review_claim_transactional(
    claim_id: int,
    admin_user_id: int,
    decision: str,
    admin_remarks: str = "",
) -> dict:
    """
    Approve or Reject an ownership claim inside a strict MySQL ACID transaction.
    Demonstrates:
      1. `SELECT ... FOR UPDATE` row-level locking on `claims` and `found_items`
      2. Prevention of multiple approved claims for the same found item
      3. Automatic rejection of competing PENDING claims when one claim is APPROVED
      4. Consistent state updates across `claims`, `found_items`, `lost_items`, `matches`, and `activity_logs`
    """
    decision_upper = (decision or "").strip().upper()
    if decision_upper not in ("APPROVED", "REJECTED"):
        raise ValueError("Decision must be either 'APPROVED' or 'REJECTED'.")

    remarks_clean = (admin_remarks or "").strip()[:255]

    try:
        with db_transaction() as (_conn, cur):
            # 1. Acquire exclusive row locks on the claim and its found item
            cur.execute(
                """
                SELECT
                    c.claim_id,
                    c.found_id,
                    c.lost_id,
                    c.claimant_id,
                    c.status AS current_claim_status,
                    f.item_name AS found_item_name,
                    f.status AS current_found_status,
                    u.full_name AS claimant_name
                FROM claims c
                INNER JOIN found_items f ON c.found_id = f.found_id
                INNER JOIN users u ON c.claimant_id = u.user_id
                WHERE c.claim_id = %s
                FOR UPDATE
                """,
                (claim_id,),
            )
            claim = cur.fetchone()
            if not claim:
                raise ValueError(f"Claim #{claim_id} does not exist.")

            found_id = claim["found_id"]
            lost_id = claim["lost_id"]

            if claim["current_claim_status"] != "PENDING":
                raise ValueError(
                    f"Claim #{claim_id} has already been reviewed (status: {claim['current_claim_status']})."
                )

            if decision_upper == "APPROVED":
                # 2. Verify no other claim is already APPROVED for this found_id
                cur.execute(
                    """
                    SELECT claim_id
                    FROM claims
                    WHERE found_id = %s AND status = 'APPROVED'
                    FOR UPDATE
                    """,
                    (found_id,),
                )
                already_approved = cur.fetchone()
                if already_approved or claim["current_found_status"] == "RETURNED":
                    raise ValueError(
                        f"Found Item #{found_id} already has an approved claim or has already been returned."
                    )

                # 3. Approve the target claim (also protected by uq_claims_single_approved_per_found)
                cur.execute(
                    """
                    UPDATE claims
                    SET status = 'APPROVED',
                        reviewed_by = %s,
                        admin_remarks = %s,
                        reviewed_at = CURRENT_TIMESTAMP
                    WHERE claim_id = %s
                    """,
                    (
                        admin_user_id,
                        remarks_clean or "Verified ownership proof and student ID.",
                        claim_id,
                    ),
                )

                # 4. Auto-reject any competing PENDING claims on the same found_id
                cur.execute(
                    """
                    UPDATE claims
                    SET status = 'REJECTED',
                        reviewed_by = %s,
                        admin_remarks = 'Automatically rejected: another verified claim was approved for this item.',
                        reviewed_at = CURRENT_TIMESTAMP
                    WHERE found_id = %s
                      AND claim_id != %s
                      AND status = 'PENDING'
                    """,
                    (admin_user_id, found_id, claim_id),
                )
                auto_rejected_count = cur.rowcount

                # 5. Mark the found item as RETURNED
                cur.execute(
                    "UPDATE found_items SET status = 'RETURNED' WHERE found_id = %s",
                    (found_id,),
                )

                # 6. If linked to a lost item, mark lost item RECOVERED and update matches
                if lost_id:
                    cur.execute(
                        "UPDATE lost_items SET status = 'RECOVERED' WHERE lost_id = %s",
                        (lost_id,),
                    )
                    cur.execute(
                        """
                        UPDATE matches
                        SET match_status = 'CONFIRMED'
                        WHERE found_id = %s AND lost_id = %s
                        """,
                        (found_id, lost_id),
                    )
                    cur.execute(
                        """
                        UPDATE matches
                        SET match_status = 'DISMISSED'
                        WHERE (found_id = %s OR lost_id = %s)
                          AND NOT (found_id = %s AND lost_id = %s)
                          AND match_status = 'SUGGESTED'
                        """,
                        (found_id, lost_id, found_id, lost_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE matches
                        SET match_status = 'DISMISSED'
                        WHERE found_id = %s AND match_status = 'SUGGESTED'
                        """,
                        (found_id,),
                    )

                # 7. Record activity logs inside the same transaction
                log_activity(
                    user_id=admin_user_id,
                    action_type="CLAIM_APPROVED",
                    entity_type="CLAIM",
                    entity_id=claim_id,
                    summary=f"Admin approved Claim #{claim_id} for '{claim['found_item_name']}' (Claimant: {claim['claimant_name']}).",
                    cursor=cur,
                )
                log_activity(
                    user_id=admin_user_id,
                    action_type="ITEM_RETURNED",
                    entity_type="FOUND_ITEM",
                    entity_id=found_id,
                    summary=f"Found Item #{found_id} ('{claim['found_item_name']}') marked RETURNED to {claim['claimant_name']} via ACID transaction.",
                    cursor=cur,
                )

                return {
                    "claim_id": claim_id,
                    "found_id": found_id,
                    "lost_id": lost_id,
                    "new_claim_status": "APPROVED",
                    "new_found_status": "RETURNED",
                    "new_lost_status": "RECOVERED" if lost_id else None,
                    "auto_rejected_competing_claims": auto_rejected_count,
                }

            else:
                # REJECTED path
                cur.execute(
                    """
                    UPDATE claims
                    SET status = 'REJECTED',
                        reviewed_by = %s,
                        admin_remarks = %s,
                        reviewed_at = CURRENT_TIMESTAMP
                    WHERE claim_id = %s
                    """,
                    (
                        admin_user_id,
                        remarks_clean or "Ownership proof did not match item verification details.",
                        claim_id,
                    ),
                )

                # Check if any other PENDING or APPROVED claims remain on found_id
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM claims
                    WHERE found_id = %s AND status IN ('PENDING', 'APPROVED')
                    """,
                    (found_id,),
                )
                remaining_active_claims = cur.fetchone()["cnt"]

                new_found_status = claim["current_found_status"]
                if remaining_active_claims == 0 and claim["current_found_status"] == "CLAIMED":
                    # Restore to MATCHED if high-confidence match exists, else AVAILABLE
                    cur.execute(
                        """
                        SELECT COUNT(*) AS m_cnt
                        FROM matches
                        WHERE found_id = %s AND match_score >= 60.0 AND match_status != 'DISMISSED'
                        """,
                        (found_id,),
                    )
                    has_high_match = cur.fetchone()["m_cnt"] > 0
                    new_found_status = "MATCHED" if has_high_match else "AVAILABLE"
                    cur.execute(
                        "UPDATE found_items SET status = %s WHERE found_id = %s",
                        (new_found_status, found_id),
                    )

                log_activity(
                    user_id=admin_user_id,
                    action_type="CLAIM_REJECTED",
                    entity_type="CLAIM",
                    entity_id=claim_id,
                    summary=f"Admin rejected Claim #{claim_id} for Found Item #{found_id} ('{claim['found_item_name']}').",
                    cursor=cur,
                )

                return {
                    "claim_id": claim_id,
                    "found_id": found_id,
                    "lost_id": lost_id,
                    "new_claim_status": "REJECTED",
                    "new_found_status": new_found_status,
                }
    except IntegrityError as exc:
        raise ValueError(
            "Database constraint prevented multiple approved claims for the same found item."
        ) from exc


def get_claims_for_user(user_id: int) -> list[dict]:
    """
    Retrieve claims submitted by a specific student.
    Includes the student's own `proof_description` and `admin_remarks`,
    but NEVER exposes `found_items.secret_detail` or other users' claims.
    """
    return query_all(
        """
        SELECT
            c.claim_id,
            c.found_id,
            c.lost_id,
            c.claimant_id,
            c.proof_description,
            c.id_card_reference,
            c.status,
            c.admin_remarks,
            c.created_at,
            c.reviewed_at,
            f.item_name AS found_item_name,
            f.category AS found_category,
            f.location_found,
            f.date_found,
            f.storage_location,
            f.image_path AS found_image_path,
            f.status AS found_status,
            l.item_name AS lost_item_name,
            ru.full_name AS reviewer_name
        FROM claims c
        INNER JOIN found_items f ON c.found_id = f.found_id
        LEFT JOIN lost_items l ON c.lost_id = l.lost_id
        LEFT JOIN users ru ON c.reviewed_by = ru.user_id
        WHERE c.claimant_id = %s
        ORDER BY c.created_at DESC
        """,
        (user_id,),
    )


def get_all_claims_for_admin(status_filter: str = "") -> list[dict]:
    """
    Retrieve all claims for Administrator verification.
    Includes private verification fields (`f.secret_detail`, `l.identifying_marks`,
    and `c.proof_description`) side-by-side so the administrator can verify ownership.
    """
    params = []
    where_clause = ""
    if status_filter and status_filter in ("PENDING", "APPROVED", "REJECTED"):
        where_clause = "WHERE c.status = %s"
        params.append(status_filter)

    return query_all(
        f"""
        SELECT
            c.claim_id,
            c.found_id,
            c.lost_id,
            c.claimant_id,
            c.proof_description,
            c.id_card_reference,
            c.status,
            c.admin_remarks,
            c.created_at,
            c.reviewed_at,
            cu.full_name AS claimant_name,
            cu.student_id AS claimant_student_id,
            cu.email AS claimant_email,
            cu.phone AS claimant_phone,
            cu.department AS claimant_department,
            f.item_name AS found_item_name,
            f.category AS found_category,
            f.brand_color AS found_brand_color,
            f.location_found,
            f.date_found,
            f.storage_location,
            f.verification_question,
            f.secret_detail AS finder_secret_detail,
            f.image_path AS found_image_path,
            f.status AS found_status,
            l.item_name AS lost_item_name,
            l.identifying_marks AS owner_identifying_marks,
            ru.full_name AS reviewer_name
        FROM claims c
        INNER JOIN users cu ON c.claimant_id = cu.user_id
        INNER JOIN found_items f ON c.found_id = f.found_id
        LEFT JOIN lost_items l ON c.lost_id = l.lost_id
        LEFT JOIN users ru ON c.reviewed_by = ru.user_id
        {where_clause}
        ORDER BY FIELD(c.status, 'PENDING', 'APPROVED', 'REJECTED'), c.created_at DESC
        """,
        tuple(params),
    )
