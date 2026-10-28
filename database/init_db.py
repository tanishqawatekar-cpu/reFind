import os
"""
Database Initialization & Campus Seed Script for ReFind (`refind_db`)
Executes `database/schema.sql`, generates sample item photographs in `static/uploads/`,
seeds realistic campus accounts, lost/found reports, runs the matching engine,
and creates sample ownership claims and activity logs.
"""

import re
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
ALLOWED_DB_HOSTS = ("localhost", "127.0.0.1")


def _validate_identifier(value: str, label: str) -> str:
    """Ensure SQL identifiers (database name, username) contain only safe alphanumeric/underscore chars."""
    if not value or not IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier for {label}: {value!r}")
    return value

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from database.db import get_server_connection, get_db_connection
from services.matching_engine import run_matching_engine


def generate_sample_images():
    """Generate clean, high-contrast sample item images in `static/uploads/` using Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    upload_dir = Path(Config.UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        ("sample_airpods.png", (42, 47, 79), (229, 217, 242), "Apple AirPods Pro (2nd Gen)", "White MagSafe Case"),
        ("sample_idcard.png", (59, 52, 134), (245, 239, 255), "Student ID Card", "CSE Dept Lanyard"),
        ("sample_calc.png", (30, 41, 59), (205, 193, 255), "Casio fx-991CW Calculator", "Black Scientific"),
        ("sample_bottle.png", (49, 46, 129), (238, 242, 255), "Milton Thermosteel Bottle", "Matte Navy 1L"),
        ("sample_wallet.png", (67, 56, 202), (243, 232, 255), "Brown Leather Bi-Fold Wallet", "Near Central Canteen"),
        ("sample_spectacles.png", (30, 27, 75), (224, 231, 255), "Lenskart Matte Black Glasses", "Blue-Cut Lenses"),
    ]

    for filename, bg_color, accent_color, title, subtitle in samples:
        target = upload_dir / filename
        if target.exists():
            continue
        img = Image.new("RGB", (640, 420), color=bg_color)
        draw = ImageDraw.Draw(img)
        # Decorative card frame
        draw.rounded_rectangle([(28, 28), (612, 392)], radius=24, outline=accent_color, width=3)
        draw.rounded_rectangle([(56, 60), (584, 245)], radius=16, fill=accent_color)
        # Inner icon badge
        draw.ellipse([(275, 105), (365, 195)], fill=bg_color)
        draw.text((304, 142), "ReFind", fill=accent_color)
        # Labels
        draw.text((60, 275), title, fill=(255, 255, 255))
        draw.text((60, 310), subtitle, fill=accent_color)
        draw.text((60, 348), "Verified Campus Lost & Found Photo", fill=(180, 185, 220))
        img.save(str(target), format="PNG")


def execute_schema_sql():
    """Execute `database/schema.sql` to create `refind_db`, tables, constraints, indexes, and views."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    sql_script = schema_path.read_text(encoding="utf-8")

    # Strip full-line SQL comments (`-- ...`) before splitting on `;` so semicolons in comments don't split statements
    cleaned_lines = [
        line for line in sql_script.splitlines() if not line.strip().startswith("--")
    ]
    cleaned_script = "\n".join(cleaned_lines)

    conn = get_server_connection()
    cursor = conn.cursor()
    try:
        statements = [stmt.strip() for stmt in cleaned_script.split(";") if stmt.strip()]
        for stmt in statements:
            cursor.execute(stmt)

        # Provision dedicated `refind_app` MySQL user with least-privilege permissions on `refind_db`
        app_user = _validate_identifier(Config.DB_USER, "DB_USER")
        db_name = _validate_identifier(Config.DB_NAME, "DB_NAME")
        app_pw = Config.DB_PASSWORD

        for host in ALLOWED_DB_HOSTS:
            cursor.execute(
                "SELECT 1 FROM mysql.user WHERE user = %s AND host = %s",
                (app_user, host),
            )
            user_exists = cursor.fetchone() is not None

            if not user_exists:
                if not app_pw:
                    raise ValueError(
                        f"DB_PASSWORD must be set in .env before creating new MySQL user '{app_user}'@'{host}'."
                    )
                # Account name is a validated SQL identifier; only the password literal uses %s binding
                cursor.execute(
                    f"CREATE USER '{app_user}'@'{host}' IDENTIFIED BY %s",
                    (app_pw,),
                )
                print(f"[OK] Created MySQL user '{app_user}'@'{host}'.")
            else:
                # Preserve existing user's password; do NOT run ALTER USER
                print(f"[INFO] MySQL user '{app_user}'@'{host}' already exists — preserving existing password.")

            # Least-privilege grant scoped strictly to `refind_db`:
            # - SELECT: read tables & SQL SECURITY INVOKER views
            # - INSERT: create users, lost/found reports, matches, claims, activity logs
            # - UPDATE: update item/match/claim statuses
            # (No DELETE, DROP, ALTER, or SHOW VIEW privileges granted)
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE ON `{db_name}`.* TO '{app_user}'@'{host}'"
            )

        conn.commit()
        print(
            f"[OK] Schema, constraints, inline indexes, views, and least-privilege grants for `{app_user}` verified in `{db_name}`."
        )
    finally:
        cursor.close()
        conn.close()


def seed_initial_data():
    """Insert realistic campus users, lost items, found items, matches, claims, and logs if empty."""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS cnt FROM users")
        if cur.fetchone()["cnt"] > 0:
            print("[INFO] Seed data already present in `refind_db` — preserving existing records.")
            return

        generate_sample_images()

        # 1. Seed Users (1 Admin + 4 Students)
        admin_pw = generate_password_hash(os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMeAdmin!01"))
        student_pw = generate_password_hash(os.getenv("DEMO_STUDENT_PASSWORD", "ChangeMeStudent!01"))

        users_data = [
            ("ADM-001", "Dr. Jordan Blake (Campus Admin)", "admin@campus.edu", "555-0100", "Administration", admin_pw, "ADMIN"),
            ("CS2024018", "Alex Rivera", "alex.rivera@campus.edu", "555-0101", "Computer Engineering", student_pw, "STUDENT"),
            ("IT2024042", "Sam Carter", "sam.carter@campus.edu", "555-0102", "Information Technology", student_pw, "STUDENT"),
            ("EN2023089", "Taylor Morgan", "taylor.morgan@campus.edu", "555-0103", "Electronics & Telecom", student_pw, "STUDENT"),
            ("ME2024105", "Casey Jordan", "casey.jordan@campus.edu", "555-0104", "Mechanical Engineering", student_pw, "STUDENT"),
        ]
        cur.executemany(
            """
            INSERT INTO users (student_id, full_name, email, phone, department, password_hash, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            users_data,
        )

        cur.execute("SELECT user_id, email FROM users")
        user_map = {row["email"]: row["user_id"] for row in cur.fetchall()}

        admin_id = user_map["admin@campus.edu"]
        alex_id = user_map["alex.rivera@campus.edu"]
        sam_id = user_map["sam.carter@campus.edu"]
        taylor_id = user_map["taylor.morgan@campus.edu"]
        casey_id = user_map["casey.jordan@campus.edu"]

        # 2. Seed Lost Items
        lost_data = [
            (
                alex_id,
                "Apple AirPods Pro (2nd Gen)",
                "Electronics",
                "White with Lavender Silicone Case",
                "Central Library Reading Room (2nd Floor)",
                "2026-10-24",
                "Lost my white Apple AirPods Pro inside a lavender silicone case near the charging tables in the Central Library reading room.",
                "Engraved initials 'DEMO-TAG-01' on back of charging case; serial ends in XYZ",
                "uploads/sample_airpods.png",
                "OPEN",
            ),
            (
                sam_id,
                "Casio fx-991CW Scientific Calculator",
                "Electronics",
                "Black Matte",
                "Block B Computer Lab 2",
                "2026-10-25",
                "Black Casio fx-991CW non-programmable scientific calculator left on desk row 3 after Numerical Methods lab.",
                "Small white sticker on back cover with roll number IT2024042",
                "uploads/sample_calc.png",
                "OPEN",
            ),
            (
                taylor_id,
                "Milton Thermosteel 1L Water Bottle",
                "Water Bottles & Umbrellas",
                "Matte Navy Blue",
                "Main Auditorium Seminar Hall",
                "2026-10-23",
                "Matte navy blue 1-liter insulated bottle left near front row seats during IEEE guest lecture.",
                "Has a small dent near bottom rim and an IEEE sticker on cap",
                "uploads/sample_bottle.png",
                "RECOVERED",
            ),
            (
                casey_id,
                "Brown Leather Bi-Fold Wallet",
                "Bags & Wallets",
                "Dark Brown Tommy Hilfiger",
                "Central Canteen Food Court",
                "2026-10-26",
                "Dark brown leather bi-fold wallet lost near the juice counter in the campus canteen.",
                "Contains sample transit card #0000, gym receipt, and ₹450 cash",
                "uploads/sample_wallet.png",
                "OPEN",
            ),
            (
                alex_id,
                "Lenskart Blu-Cut Spectacles in Case",
                "Clothing & Eyewear",
                "Matte Black Rectangular Frame",
                "Block A Tutorial Room 104",
                "2026-10-26",
                "Matte black rectangular frame spectacles inside a grey hard Lenskart zipper case.",
                "Blue microfiber cloth with name written in corner",
                "uploads/sample_spectacles.png",
                "OPEN",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO lost_items (
                user_id, item_name, category, brand_color, location_lost,
                date_lost, description, identifying_marks, image_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            lost_data,
        )

        # 3. Seed Found Items
        found_data = [
            (
                sam_id,
                "AirPods Pro in Lavender Case",
                "Electronics",
                "White / Lavender Silicone Cover",
                "Central Library 2nd Floor Study Hall",
                "2026-10-24",
                "Found a pair of Apple AirPods Pro in a soft lavender silicone cover plugged in near window table 6 in the Central Library.",
                "Campus Lost & Found Desk (Main Admin Block, Room 102)",
                "What initials or engraving are printed on the charging case, or what are the last 3 characters of the serial number?",
                "Engraving says DEMO-TAG-01 on back under silicone case",
                "uploads/sample_airpods.png",
                "AVAILABLE",
            ),
            (
                taylor_id,
                "Casio fx-991CW Scientific Calculator",
                "Electronics",
                "Black",
                "Block B Computer Lab 2",
                "2026-10-25",
                "Found a black Casio fx-991CW scientific calculator on workstation 14 after the afternoon lab session.",
                "IT Department Office (Block B, Ground Floor)",
                "What roll number or sticker is affixed to the back of the calculator?",
                "White label with IT2024042",
                "uploads/sample_calc.png",
                "AVAILABLE",
            ),
            (
                casey_id,
                "Navy Blue Milton Insulated Bottle",
                "Water Bottles & Umbrellas",
                "Navy Blue",
                "Main Auditorium Stage Left",
                "2026-10-23",
                "Found a navy blue Milton metal bottle near the front row after the seminar.",
                "Campus Lost & Found Desk (Main Admin Block, Room 102)",
                "Describe any sticker on the cap or physical mark on the bottle.",
                "IEEE sticker on cap and small dent at base",
                "uploads/sample_bottle.png",
                "RETURNED",
            ),
            (
                alex_id,
                "Dark Brown Leather Wallet",
                "Bags & Wallets",
                "Dark Brown",
                "Campus Canteen Outdoor Tables",
                "2026-10-26",
                "Found a dark brown leather bi-fold wallet under the table near the canteen juice counter.",
                "Campus Security Office (Main Gate 1)",
                "State the brand of the wallet, approximate cash amount, and any pass/receipt inside.",
                "Tommy Hilfiger, sample transit card #0000, ₹450",
                "uploads/sample_wallet.png",
                "AVAILABLE",
            ),
            (
                sam_id,
                "College Student ID Card & Lanyard",
                "ID & Cards",
                "Blue Campus Lanyard",
                "Sports Complex Basketball Court",
                "2026-10-26",
                "Found a college ID card holder with a blue lanyard and a metro card tucked behind it.",
                "Sports Gymkhana Office",
                "State the student roll number and the last 4 digits of the metro card tucked inside.",
                "Metro card ends in 0000",
                "uploads/sample_idcard.png",
                "AVAILABLE",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO found_items (
                user_id, item_name, category, brand_color, location_found,
                date_found, description, storage_location, verification_question,
                secret_detail, image_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            found_data,
        )

        # Fetch inserted IDs
        cur.execute("SELECT lost_id, item_name FROM lost_items ORDER BY lost_id")
        lost_rows = cur.fetchall()
        cur.execute("SELECT found_id, item_name FROM found_items ORDER BY found_id")
        found_rows = cur.fetchall()

        # 4. Seed Ownership Claims (1 PENDING on AirPods, 1 PENDING on Calculator, 1 APPROVED on Bottle)
        claims_data = [
            (
                found_rows[0]["found_id"],  # AirPods Pro
                lost_rows[0]["lost_id"],
                alex_id,
                "The charging case has 'DEMO-TAG-01' laser-engraved on the back beneath the lavender silicone cover, and the serial number ends with XYZ.",
                "CS2024018",
                "PENDING",
                None,
                None,
                None,
            ),
            (
                found_rows[1]["found_id"],  # Casio Calculator
                lost_rows[1]["lost_id"],
                sam_id,
                "There is a small white label on the back cover with my roll number IT2024042 written in blue ink.",
                "IT2024042",
                "PENDING",
                None,
                None,
                None,
            ),
            (
                found_rows[2]["found_id"],  # Navy Bottle (Already APPROVED & RETURNED)
                lost_rows[2]["lost_id"],
                taylor_id,
                "The cap has a silver IEEE student branch sticker and there is a small dent on the bottom rim.",
                "EN2023089",
                "APPROVED",
                admin_id,
                "Verified IEEE sticker and roll card in person at Admin Block Desk.",
                "2026-10-24 14:30:00",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO claims (
                found_id, lost_id, claimant_id, proof_description, id_card_reference,
                status, reviewed_by, admin_remarks, reviewed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            claims_data,
        )

        # 5. Seed Activity Logs
        logs_data = [
            (alex_id, "LOST_REPORTED", "LOST_ITEM", lost_rows[0]["lost_id"], "Alex Rivera reported lost 'Apple AirPods Pro (2nd Gen)' at Central Library Reading Room."),
            (sam_id, "FOUND_REPORTED", "FOUND_ITEM", found_rows[0]["found_id"], "Sam Carter reported found 'AirPods Pro in Lavender Case' at Central Library 2nd Floor Study Hall."),
            (alex_id, "CLAIM_SUBMITTED", "CLAIM", 1, "Alex Rivera submitted an ownership claim for Found Item #1 (AirPods Pro in Lavender Case)."),
            (sam_id, "LOST_REPORTED", "LOST_ITEM", lost_rows[1]["lost_id"], "Sam Carter reported lost 'Casio fx-991CW Scientific Calculator' at Block B Computer Lab 2."),
            (taylor_id, "FOUND_REPORTED", "FOUND_ITEM", found_rows[1]["found_id"], "Taylor Morgan reported found 'Casio fx-991CW Scientific Calculator' at Block B Computer Lab 2."),
            (taylor_id, "CLAIM_SUBMITTED", "CLAIM", 3, "Taylor Morgan submitted an ownership claim for Found Item #3 (Navy Blue Milton Insulated Bottle)."),
            (admin_id, "CLAIM_APPROVED", "CLAIM", 3, "Admin Dr. Jordan Blake approved Claim #3 and verified return of 'Navy Blue Milton Insulated Bottle' to Taylor Morgan."),
            (admin_id, "ITEM_RETURNED", "FOUND_ITEM", found_rows[2]["found_id"], "Found Item #3 marked as RETURNED and Lost Item #3 marked as RECOVERED via ACID transaction."),
        ]
        cur.executemany(
            """
            INSERT INTO activity_logs (user_id, action_type, entity_type, entity_id, summary)
            VALUES (%s, %s, %s, %s, %s)
            """,
            logs_data,
        )

        conn.commit()
        print("[OK] Seeded users, lost_items, found_items, claims, and activity_logs.")
    finally:
        cur.close()
        conn.close()

    # Run rule-based matching engine to populate `matches`
    total_matches = run_matching_engine()
    print(f"[OK] Rule-based matching engine generated {total_matches} candidate match(es).")


if __name__ == "__main__":
    execute_schema_sql()
    seed_initial_data()
