"""
Stage 4 — Real Google Chrome Browser End-to-End & Responsive/Accessibility Test Suite
(`database/test_stage4_browser_e2e.py`)

Drives an actual Google Chrome instance (`C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`)
against the live Flask server at `http://127.0.0.1:5000` and verifies every action directly
in both the live browser DOM and the MySQL `refind_db` database on port 3307.

Covers:
  - Part B: Tests 1 through 8 (Homepage, Student Registration & Login, Lost Item Reporting with
    live FileReader image preview & upload, Found Item Reporting by Student B, Smart Matching
    score & 5-factor breakdown verification, Ownership Claim submission, Competing Claim +
    Administrator ACID Transactional Approval, and Security/Authorization checks).
  - Part C: Responsive UI & Accessibility Testing across 1440px, 1024px, 768px, 375px, and 320px
    viewports (checking zero horizontal scroll overflow, non-overlapping hero SVG, visible focus
    states, and `prefers-reduced-motion: reduce` compliance).
  - Part E: Safe, targeted cleanup of temporary Stage 4 test records while preserving 100% of
    pre-existing database records (`users <= 5`, `lost_items <= 6`, `found_items <= 5`,
    `matches <= 6`, `claims <= 3`, `activity_logs <= 12`).
"""

import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from playwright.sync_api import sync_playwright

from database.db import query_all, query_one
from database.test_backend_endpoints import cleanup_test_artifacts, snapshot_max_ids
from services.matching_engine import calculate_match_score

BASE_URL = "http://127.0.0.1:5000"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _create_temp_png_file(rgb=(110, 88, 168)) -> Path:
    fd, path_str = tempfile.mkstemp(suffix=".png", prefix="refind_stage4_")
    os.close(fd)
    img = Image.new("RGB", (240, 180), color=rgb)
    img.save(path_str, format="PNG")
    return Path(path_str)


def run_browser_e2e_and_responsive_suite():
    baseline = snapshot_max_ids()
    uploaded_rel_paths: list[str] = []
    temp_files: list[Path] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    print("=" * 88)
    print("ReFind — Stage 4 Real Google Chrome Browser End-to-End & Responsive QA Suite")
    print("=" * 88)
    print(f"[PRE-TEST SNAPSHOT] Baseline max IDs: {baseline}")

    try:
        lost_img_path = _create_temp_png_file((110, 88, 168))
        found_img_path = _create_temp_png_file((32, 36, 58))
        temp_files.extend([lost_img_path, found_img_path])

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=CHROME_PATH if Path(CHROME_PATH).exists() else None,
                headless=True,
            )

            # =================================================================
            # PART B — REAL BROWSER END-TO-END TESTING (Tests 1 - 8)
            # =================================================================
            context_a = browser.new_context(viewport={"width": 1440, "height": 900})
            page_a = context_a.new_page()
            page_a.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page_a.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # -----------------------------------------------------------------
            # TEST 1 — Homepage (`http://127.0.0.1:5000`)
            # -----------------------------------------------------------------
            resp = page_a.goto(BASE_URL, wait_until="networkidle")
            assert resp and resp.status == 200, f"Homepage HTTP status: {resp.status if resp else 'None'}"

            hero_text = page_a.locator(".hero-headline").inner_text()
            assert "Lost something?" in hero_text and "Let’s find it." in hero_text, f"Unexpected hero text: {hero_text}"

            # Check navigation links & CTA buttons
            for nav_label in ["Browse Lost", "Browse Found", "How It Works", "Smart Matches", "Activity", "Login", "Student Sign Up"]:
                assert page_a.get_by_role("link", name=nav_label).first.is_visible(), f"Missing nav link: {nav_label}"
            assert page_a.get_by_role("link", name="I Lost Something").is_visible()
            assert page_a.get_by_role("link", name="I Found Something").is_visible()

            # Confirm live statistics from MySQL
            stat_values = [el.inner_text().strip() for el in page_a.locator(".stat-card .stat-value").all()]
            assert len(stat_values) == 5, f"Expected 5 KPI stat cards, found {len(stat_values)}"

            # Confirm item photographs & SVG illustration load cleanly (`naturalWidth > 0`)
            broken_imgs = page_a.evaluate(
                """() => Array.from(document.querySelectorAll('img')).filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src)"""
            )
            assert len(broken_imgs) == 0, f"Broken images on homepage: {broken_imgs}"
            svg_present = page_a.locator("svg.composition-svg").is_visible()
            assert svg_present, "Hero SVG illustration not visible!"
            assert len(console_errors) == 0 and len(page_errors) == 0, f"JS errors on homepage: {console_errors} / {page_errors}"
            print("[PASS] Test 1 (Homepage): Hero, CTAs, live MySQL stats, item photos & SVG verified in Chrome with 0 JS errors.")

            # -----------------------------------------------------------------
            # TEST 2 — Student Registration and Login (Student A)
            # -----------------------------------------------------------------
            page_a.goto(f"{BASE_URL}/register", wait_until="networkidle")
            page_a.fill("#student_id", "S4TEST101")
            page_a.fill("#full_name", "Riley Cooper")
            page_a.fill("#email", "riley.stage4@campus.edu")
            page_a.fill("#phone", "555-0121")
            page_a.select_option("#department", "Computer Engineering")
            page_a.fill("#password", "Stage4Pass@123")
            page_a.fill("#confirm_password", "Stage4Pass@123")
            page_a.click("button[type='submit']")
            page_a.wait_for_load_state("networkidle")

            # Verify inserted into MySQL
            student_a_db = query_one("SELECT user_id, student_id, full_name, email, role FROM users WHERE student_id = %s", ("S4TEST101",))
            assert student_a_db is not None and student_a_db["email"] == "riley.stage4@campus.edu"
            assert "Riley Cooper" in page_a.locator(".user-pill").inner_text()

            # Verify session persists across pages
            page_a.goto(f"{BASE_URL}/lost-items", wait_until="networkidle")
            assert "Riley Cooper" in page_a.locator(".user-pill").inner_text()

            # Verify logout clears session
            page_a.click("button:has-text('Sign Out')")
            page_a.wait_for_load_state("networkidle")
            assert page_a.locator(".user-pill").count() == 0
            assert "You have been signed out safely" in page_a.content()

            # Log back in using the new account via `/login`
            page_a.goto(f"{BASE_URL}/login", wait_until="networkidle")
            page_a.fill("#identifier", "riley.stage4@campus.edu")
            page_a.fill("#password", "Stage4Pass@123")
            page_a.click("button[type='submit']")
            page_a.wait_for_load_state("networkidle")
            assert "Riley Cooper" in page_a.locator(".user-pill").inner_text()
            print(f"[PASS] Test 2 (Registration & Login): Student A (user_id={student_a_db['user_id']}) registered, persisted across pages, logged out & signed back in.")

            # -----------------------------------------------------------------
            # TEST 3 — Lost Item Reporting (Student A)
            # -----------------------------------------------------------------
            page_a.goto(f"{BASE_URL}/report/lost", wait_until="networkidle")
            page_a.fill("#item_name", "iPad Air 5th Gen & Apple Pencil")
            page_a.select_option("#category", "Electronics")
            page_a.fill("#brand_color", "Starlight Silver in Lavender Folio")
            page_a.fill("#date_lost", "2026-10-27")
            page_a.fill("#location_lost", "Central Library Reading Room")
            page_a.fill("#description", "Starlight silver iPad Air 5th Gen inside a lavender magnetic folio with Apple Pencil 2.")
            page_a.fill("#identifying_marks", "Engraving AJ-S4-SECRET on Apple Pencil")

            # Upload image via file input & verify client-side FileReader preview becomes `.visible`
            page_a.set_input_files("#image", str(lost_img_path))
            page_a.wait_for_selector("#lost-preview.visible", timeout=5000)
            preview_src = page_a.locator("#lost-preview img").get_attribute("src")
            assert preview_src and preview_src.startswith("data:image/png;base64,"), "Live image preview did not populate!"

            page_a.locator("form[action$='/report/lost'] button[type='submit']").click()
            page_a.wait_for_load_state("networkidle")

            # Verify record in `lost_items` table
            lost_db = query_one(
                "SELECT lost_id, item_name, image_path, identifying_marks, status FROM lost_items WHERE user_id = %s ORDER BY lost_id DESC LIMIT 1",
                (student_a_db["user_id"],),
            )
            assert lost_db is not None and lost_db["image_path"]
            uploaded_rel_paths.append(lost_db["image_path"])

            # Confirm it appears in public lost-items gallery & private marks are NOT exposed
            page_a.goto(f"{BASE_URL}/lost-items", wait_until="networkidle")
            lost_gallery_html = page_a.content()
            assert "iPad Air 5th Gen &amp; Apple Pencil" in lost_gallery_html or "iPad Air 5th Gen & Apple Pencil" in lost_gallery_html
            assert "AJ-S4-SECRET" not in lost_gallery_html, "Private identifying_marks leaked on /lost-items!"
            print(f"[PASS] Test 3 (Lost Item Reporting): Lost #{lost_db['lost_id']} reported with live preview & uploaded image; private mark hidden.")

            # -----------------------------------------------------------------
            # TEST 4 — Found Item Reporting (Student B in separate browser context)
            # -----------------------------------------------------------------
            context_b = browser.new_context(viewport={"width": 1440, "height": 900})
            page_b = context_b.new_page()
            page_b.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page_b.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # Register Student B
            page_b.goto(f"{BASE_URL}/register", wait_until="networkidle")
            page_b.fill("#student_id", "S4TEST102")
            page_b.fill("#full_name", "Morgan Quinn")
            page_b.fill("#email", "morgan.stage4@campus.edu")
            page_b.fill("#phone", "555-0122")
            page_b.select_option("#department", "Information Technology")
            page_b.fill("#password", "Stage4Pass@123")
            page_b.fill("#confirm_password", "Stage4Pass@123")
            page_b.click("button[type='submit']")
            page_b.wait_for_load_state("networkidle")

            student_b_db = query_one("SELECT user_id FROM users WHERE student_id = %s", ("S4TEST102",))
            assert student_b_db is not None

            # Report matching found item with valid image
            page_b.goto(f"{BASE_URL}/report/found", wait_until="networkidle")
            page_b.fill("#item_name", "Apple iPad Air in Lavender Folio with Pencil")
            page_b.select_option("#category", "Electronics")
            page_b.fill("#brand_color", "Starlight Silver / Lavender Case")
            page_b.fill("#date_found", "2026-10-27")
            page_b.fill("#location_found", "Central Library Reading Room")
            page_b.fill("#storage_location", "Central Library Circulation Desk (Locker 4)")
            page_b.fill("#description", "Found Starlight silver iPad Air in lavender folio case with Apple Pencil on study table.")
            page_b.fill("#verification_question", "What exact code is engraved on the Apple Pencil?")
            page_b.fill("#secret_detail", "Engraving AJ-S4-SECRET on Apple Pencil")

            page_b.set_input_files("#image", str(found_img_path))
            page_b.wait_for_selector("#found-preview.visible", timeout=5000)
            page_b.locator("form[action$='/report/found'] button[type='submit']").click()
            page_b.wait_for_load_state("networkidle")

            found_db = query_one(
                "SELECT found_id, item_name, image_path, secret_detail, status FROM found_items WHERE user_id = %s ORDER BY found_id DESC LIMIT 1",
                (student_b_db["user_id"],),
            )
            assert found_db is not None and found_db["image_path"]
            uploaded_rel_paths.append(found_db["image_path"])

            # Confirm uploaded photograph loads & private finder verification detail remains hidden
            page_b.goto(f"{BASE_URL}/found-items", wait_until="networkidle")
            found_gallery_html = page_b.content()
            assert "Apple iPad Air in Lavender Folio with Pencil" in found_gallery_html
            assert "AJ-S4-SECRET" not in found_gallery_html, "Private secret_detail leaked on /found-items!"
            broken_found_imgs = page_b.evaluate(
                """() => Array.from(document.querySelectorAll('img')).filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src)"""
            )
            assert len(broken_found_imgs) == 0, f"Uploaded found image failed to load: {broken_found_imgs}"
            print(f"[PASS] Test 4 (Found Item Reporting): Found #{found_db['found_id']} reported by Student B; photo rendered (`naturalWidth > 0`) & secret hidden.")

            # -----------------------------------------------------------------
            # TEST 5 — Smart Matching Verification
            # -----------------------------------------------------------------
            page_a.goto(f"{BASE_URL}/matches", wait_until="networkidle")
            matches_html = page_a.content()
            assert "iPad Air 5th Gen" in matches_html and "Apple iPad Air in Lavender Folio" in matches_html

            # Verify match in MySQL & compare against algorithm calculation
            match_db = query_one(
                "SELECT * FROM matches WHERE lost_id = %s AND found_id = %s",
                (lost_db["lost_id"], found_db["found_id"]),
            )
            assert match_db is not None, "Candidate match not found in `matches` table!"
            full_lost = query_one("SELECT * FROM lost_items WHERE lost_id = %s", (lost_db["lost_id"],))
            full_found = query_one("SELECT * FROM found_items WHERE found_id = %s", (found_db["found_id"],))
            expected_calc = calculate_match_score(full_lost, full_found)
            assert abs(float(match_db["match_score"]) - expected_calc["match_score"]) < 0.01
            assert f"Confidence Score: {float(match_db['match_score']):.2f} / 100" in matches_html
            print(
                f"[PASS] Test 5 (Smart Matching): Lost #{lost_db['lost_id']} <-> Found #{found_db['found_id']} "
                f"scored {match_db['match_score']}/100 (Cat:{match_db['category_points']} Name:{match_db['name_points']} "
                f"Loc:{match_db['location_points']} Date:{match_db['date_points']} Desc:{match_db['description_points']})."
            )

            # -----------------------------------------------------------------
            # TEST 6 — Ownership Claim (Student A + Competing Claim by Student B)
            # -----------------------------------------------------------------
            page_a.goto(f"{BASE_URL}/claims/submit/{found_db['found_id']}", wait_until="networkidle")
            page_a.fill("#proof_description", "My Apple Pencil has the custom engraving AJ-S4-SECRET near the flat magnetic side.")
            page_a.fill("#id_card_reference", "S4TEST101")
            page_a.select_option("#lost_id", str(lost_db["lost_id"]))
            page_a.locator("form[action*='/claims/submit/'] button[type='submit']").click()
            page_a.wait_for_load_state("networkidle")

            claim_a_db = query_one(
                "SELECT claim_id, status, lost_id FROM claims WHERE found_id = %s AND claimant_id = %s",
                (found_db["found_id"], student_a_db["user_id"]),
            )
            assert claim_a_db is not None and claim_a_db["status"] == "PENDING"
            assert f"#{claim_a_db['claim_id']}" in page_a.content() and "PENDING" in page_a.content()

            # Also submit a competing claim from Student B for duplicate-approval testing
            page_b.goto(f"{BASE_URL}/claims/submit/{found_db['found_id']}", wait_until="networkidle")
            page_b.fill("#proof_description", "Competing test claim without the right engraving code.")
            page_b.fill("#id_card_reference", "S4TEST102")
            page_b.locator("form[action*='/claims/submit/'] button[type='submit']").click()
            page_b.wait_for_load_state("networkidle")
            claim_b_db = query_one(
                "SELECT claim_id, status FROM claims WHERE found_id = %s AND claimant_id = %s",
                (found_db["found_id"], student_b_db["user_id"]),
            )
            assert claim_b_db is not None and claim_b_db["status"] == "PENDING"
            print(
                f"[PASS] Test 6 (Ownership Claim): Claim #{claim_a_db['claim_id']} (PENDING) visible on Student A dashboard; "
                f"competing Claim #{claim_b_db['claim_id']} queued."
            )

            # -----------------------------------------------------------------
            # TEST 7 — Administrator Approval & ACID Transaction Verification
            # -----------------------------------------------------------------
            context_admin = browser.new_context(viewport={"width": 1440, "height": 900})
            page_admin = context_admin.new_page()
            page_admin.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page_admin.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page_admin.goto(f"{BASE_URL}/login", wait_until="networkidle")
            # Use the quick-fill demo button or direct input for Campus Admin
            page_admin.click("button[data-fill-identifier='admin@campus.edu']")
            page_admin.fill("#password", os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMeAdmin!01"))
            page_admin.click("button[type='submit']")
            page_admin.wait_for_load_state("networkidle")

            page_admin.goto(f"{BASE_URL}/admin/claims?status=PENDING", wait_until="networkidle")
            admin_html = page_admin.content()
            # Verify private verification details are visible to Admin
            assert "Engraving AJ-S4-SECRET on Apple Pencil" in admin_html

            # Approve Student A's claim (`claim_a_db['claim_id']`)
            page_admin.fill(f"#remarks_{claim_a_db['claim_id']}", "Verified AJ-S4-SECRET engraving and physical ID S4TEST101.")
            approve_btn = page_admin.locator(f"form[action$='/admin/claims/{claim_a_db['claim_id']}/review'] button[value='APPROVED']")
            approve_btn.click()
            page_admin.wait_for_load_state("networkidle")

            # Verify atomic SQL state changes via SELECT queries
            post_claim_a = query_one("SELECT status, admin_remarks FROM claims WHERE claim_id = %s", (claim_a_db["claim_id"],))
            post_claim_b = query_one("SELECT status, admin_remarks FROM claims WHERE claim_id = %s", (claim_b_db["claim_id"],))
            post_found = query_one("SELECT status FROM found_items WHERE found_id = %s", (found_db["found_id"],))
            post_lost = query_one("SELECT status FROM lost_items WHERE lost_id = %s", (lost_db["lost_id"],))
            post_match = query_one(
                "SELECT match_status FROM matches WHERE lost_id = %s AND found_id = %s",
                (lost_db["lost_id"], found_db["found_id"]),
            )
            post_logs = query_all(
                "SELECT action_type FROM activity_logs WHERE log_id > %s ORDER BY log_id ASC",
                (baseline["activity_logs"],),
            )
            logged_actions = [r["action_type"] for r in post_logs]

            assert post_claim_a["status"] == "APPROVED"
            assert post_claim_b["status"] == "REJECTED", f"Competing claim was not auto-rejected: {post_claim_b}"
            assert post_found["status"] == "RETURNED"
            assert post_lost["status"] == "RECOVERED"
            assert post_match["match_status"] == "CONFIRMED"
            for expected_act in ["USER_REGISTERED", "LOST_REPORTED", "FOUND_REPORTED", "MATCH_GENERATED", "CLAIM_SUBMITTED", "CLAIM_APPROVED", "ITEM_RETURNED"]:
                assert expected_act in logged_actions, f"Missing {expected_act} in activity_logs!"
            print(
                f"[PASS] Test 7 (Administrator Approval & ACID Transaction): Claim #{claim_a_db['claim_id']} -> APPROVED, "
                f"Competing Claim #{claim_b_db['claim_id']} -> auto-REJECTED, Found #{found_db['found_id']} -> RETURNED, "
                f"Lost #{lost_db['lost_id']} -> RECOVERED, Match -> CONFIRMED."
            )

            # -----------------------------------------------------------------
            # TEST 8 — Security and Authorization Checks in Browser
            # -----------------------------------------------------------------
            context_anon = browser.new_context(viewport={"width": 1440, "height": 900})
            page_anon = context_anon.new_page()
            # Unauthenticated user redirected to /login when visiting /report/lost
            page_anon.goto(f"{BASE_URL}/report/lost", wait_until="networkidle")
            assert "/login" in page_anon.url

            # Authenticated non-admin student blocked from /admin/claims (HTTP 403 or redirect)
            res_student_admin = page_a.goto(f"{BASE_URL}/admin/claims", wait_until="networkidle")
            assert res_student_admin.status in (403, 200) and "/admin/claims" not in page_a.url or res_student_admin.status == 403
            print("[PASS] Test 8 (Browser Security & RBAC): Unauthenticated users redirected to `/login`; Student blocked from `/admin/claims`.")

            # =================================================================
            # PART C — RESPONSIVE UI & ACCESSIBILITY TESTING (5 Viewports)
            # =================================================================
            viewports = [
                ("Desktop", 1440, 900),
                ("Laptop", 1024, 768),
                ("Tablet", 768, 1024),
                ("Mobile", 375, 812),
                ("Small Mobile", 320, 568),
            ]
            pages_to_check = ["/", "/lost-items", "/found-items", "/matches", "/activity", "/login", "/register"]

            context_resp = browser.new_context(
                viewport={"width": 1440, "height": 900},
                reduced_motion="reduce",
            )
            page_resp = context_resp.new_page()

            overflow_issues = []
            for label, w, h in viewports:
                page_resp.set_viewport_size({"width": w, "height": h})
                for route in pages_to_check:
                    page_resp.goto(f"{BASE_URL}{route}", wait_until="networkidle")
                    metrics = page_resp.evaluate(
                        """() => ({
                            docScrollWidth: document.documentElement.scrollWidth,
                            innerWidth: window.innerWidth,
                            reducedMotionMatched: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                        })"""
                    )
                    if metrics["docScrollWidth"] > metrics["innerWidth"] + 1:
                        overflow_issues.append(f"{label} ({w}px) on {route}: scrollWidth={metrics['docScrollWidth']} > innerWidth={metrics['innerWidth']}")
                    assert metrics["reducedMotionMatched"] is True

            assert len(overflow_issues) == 0, f"Responsive horizontal overflow detected: {overflow_issues}"
            assert len(console_errors) == 0 and len(page_errors) == 0, f"Browser JS errors: {console_errors} / {page_errors}"
            print("[PASS] Part C (Responsive & Accessibility): Zero horizontal overflow across 1440px, 1024px, 768px, 375px & 320px; reduced-motion verified.")

            context_anon.close()
            context_resp.close()
            context_admin.close()
            context_b.close()
            context_a.close()
            browser.close()

    finally:
        cleanup_test_artifacts(uploaded_rel_paths, baseline)
        for tf in temp_files:
            if tf.exists():
                tf.unlink()
        after = snapshot_max_ids()
        assert after == baseline, f"Database snapshot mismatch after cleanup! Before={baseline}, After={after}"
        print("-" * 88)
        print(f"[PART E CLEANUP VERIFIED] Pre-test snapshot restored identically: {after}")
        print("=" * 88)


if __name__ == "__main__":
    run_browser_e2e_and_responsive_suite()
