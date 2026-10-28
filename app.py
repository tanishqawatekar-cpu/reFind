"""
ReFind — Smart Campus Lost & Found System
Main Flask Application & Route Controllers (`app.py`)
"""

from datetime import date, datetime
from decimal import Decimal
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask.json.provider import DefaultJSONProvider
from mysql.connector import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from database.db import query_all, query_one, execute_write, log_activity
from services.security import (
    EMAIL_RE,
    STUDENT_ID_RE,
    PHONE_RE,
    VALID_CATEGORIES,
    wants_json_response,
    get_csrf_token,
    verify_csrf_token,
    current_user,
    login_required,
    admin_required,
    validate_date_str,
    clean_str,
)
from services.upload_service import save_uploaded_image
from services.matching_engine import run_matching_engine
from services.claim_service import (
    submit_ownership_claim,
    review_claim_transactional,
    get_claims_for_user,
    get_all_claims_for_admin,
)


class CustomJSONProvider(DefaultJSONProvider):
    """Serialize MySQL `Decimal`, `date`, and `datetime` objects cleanly to JSON."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def create_app() -> Flask:
    app = Flask(__name__)
    app.json = CustomJSONProvider(app)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # -------------------------------------------------------------------------
    # Global CSRF & Template Context Hooks
    # -------------------------------------------------------------------------
    @app.before_request
    def enforce_csrf():
        verify_csrf_token()

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_csrf_token,
            "current_user": current_user(),
            "categories": sorted(list(VALID_CATEGORIES)),
            "today_iso": date.today().isoformat(),
        }

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        if wants_json_response():
            return jsonify({"ok": False, "error": exc.description, "code": exc.code}), exc.code
        flash(exc.description, "danger")
        return redirect(request.referrer or url_for("dashboard_page"))

    @app.errorhandler(413)
    def handle_large_file(_exc):
        msg = "Uploaded image exceeds the 5 MB maximum size limit."
        if wants_json_response():
            return jsonify({"ok": False, "error": msg}), 413
        flash(msg, "danger")
        return redirect(request.referrer or url_for("dashboard_page"))

    # =========================================================================
    # 1. AUTHENTICATION & SESSION ENDPOINTS
    # =========================================================================
    @app.route("/api/auth/csrf", methods=["GET"])
    def api_csrf_token():
        return jsonify({"ok": True, "csrf_token": get_csrf_token()})

    @app.route("/api/auth/me", methods=["GET"])
    def api_auth_me():
        user = current_user()
        return jsonify({"ok": True, "authenticated": user is not None, "user": user})

    @app.route("/register", methods=["GET", "POST"])
    @app.route("/api/auth/register", methods=["POST"], endpoint="api_auth_register")
    def register_page():
        if request.method == "GET":
            if current_user():
                return redirect(url_for("dashboard_page"))
            return render_template("register.html")

        payload = request.get_json(silent=True) if request.is_json else request.form
        student_id = clean_str(payload.get("student_id"), 30).upper()
        full_name = clean_str(payload.get("full_name"), 100)
        email = clean_str(payload.get("email"), 120).lower()
        phone = clean_str(payload.get("phone"), 20)
        department = clean_str(payload.get("department"), 80)
        password = payload.get("password") or ""
        confirm_password = payload.get("confirm_password") or password

        errors = []
        if not STUDENT_ID_RE.match(student_id):
            errors.append("Student/Roll ID must be 3–30 alphanumeric characters.")
        if len(full_name) < 2:
            errors.append("Full name must be at least 2 characters.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid campus email address.")
        if not PHONE_RE.match(phone):
            errors.append("Please enter a valid contact phone number (7–20 digits).")
        if len(department) < 2:
            errors.append("Department is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if password != confirm_password:
            errors.append("Password and confirmation do not match.")

        if errors:
            err_msg = " ".join(errors)
            if wants_json_response():
                return jsonify({"ok": False, "error": err_msg}), 400
            flash(err_msg, "danger")
            return render_template("register.html", form_data=payload), 400

        password_hash = generate_password_hash(password)
        try:
            new_user_id = execute_write(
                """
                INSERT INTO users (student_id, full_name, email, phone, department, password_hash, role)
                VALUES (%s, %s, %s, %s, %s, %s, 'STUDENT')
                """,
                (student_id, full_name, email, phone, department, password_hash),
            )
        except IntegrityError:
            err_msg = "An account with this Student ID or Email already exists."
            if wants_json_response():
                return jsonify({"ok": False, "error": err_msg}), 409
            flash(err_msg, "danger")
            return render_template("register.html", form_data=payload), 409

        log_activity(
            user_id=new_user_id,
            action_type="USER_REGISTERED",
            entity_type="USER",
            entity_id=new_user_id,
            summary=f"Student {full_name} ({student_id}, {department}) registered on ReFind.",
        )

        session["user_id"] = new_user_id
        session["student_id"] = student_id
        session["full_name"] = full_name
        session["email"] = email
        session["department"] = department
        session["role"] = "STUDENT"
        get_csrf_token()

        if wants_json_response():
            return (
                jsonify(
                    {
                        "ok": True,
                        "message": "Registration successful.",
                        "user": current_user(),
                    }
                ),
                201,
            )

        flash(f"Welcome to ReFind, {full_name}!", "success")
        return redirect(url_for("dashboard_page"))

    @app.route("/login", methods=["GET", "POST"])
    @app.route("/api/auth/login", methods=["POST"], endpoint="api_auth_login")
    def login_page():
        if request.method == "GET":
            if current_user():
                return redirect(url_for("dashboard_page"))
            return render_template("login.html")

        payload = request.get_json(silent=True) if request.is_json else request.form
        identifier = clean_str(payload.get("identifier") or payload.get("email"), 120)
        password = payload.get("password") or ""

        if not identifier or not password:
            msg = "Please enter both your Email/Student ID and password."
            if wants_json_response():
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg, "danger")
            return render_template("login.html"), 400

        user_row = query_one(
            """
            SELECT user_id, student_id, full_name, email, department, password_hash, role, is_active
            FROM users
            WHERE LOWER(email) = LOWER(%s) OR UPPER(student_id) = UPPER(%s)
            LIMIT 1
            """,
            (identifier, identifier),
        )

        if not user_row or not check_password_hash(user_row["password_hash"], password):
            msg = "Invalid Email/Student ID or password."
            if wants_json_response():
                return jsonify({"ok": False, "error": msg}), 401
            flash(msg, "danger")
            return render_template("login.html"), 401

        if not user_row["is_active"]:
            msg = "This account has been deactivated. Contact campus administration."
            if wants_json_response():
                return jsonify({"ok": False, "error": msg}), 403
            flash(msg, "danger")
            return render_template("login.html"), 403

        session["user_id"] = user_row["user_id"]
        session["student_id"] = user_row["student_id"]
        session["full_name"] = user_row["full_name"]
        session["email"] = user_row["email"]
        session["department"] = user_row["department"]
        session["role"] = user_row["role"]
        get_csrf_token()

        log_activity(
            user_id=user_row["user_id"],
            action_type="USER_LOGIN",
            entity_type="USER",
            entity_id=user_row["user_id"],
            summary=f"{user_row['full_name']} ({user_row['role']}) signed in.",
        )

        if wants_json_response():
            return jsonify({"ok": True, "message": "Login successful.", "user": current_user()})

        flash(f"Signed in as {user_row['full_name']}.", "success")
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("dashboard_page"))

    @app.route("/logout", methods=["POST"])
    @app.route("/api/auth/logout", methods=["POST"], endpoint="api_auth_logout")
    def logout_action():
        session.clear()
        if wants_json_response():
            return jsonify({"ok": True, "message": "Logged out successfully."})
        flash("You have been signed out safely.", "info")
        return redirect(url_for("login_page"))

    # =========================================================================
    # 2. DASHBOARD & REAL-TIME STATISTICS (SQL VIEWS + AGGREGATIONS)
    # =========================================================================
    def _build_dashboard_data() -> dict:
        stats = query_one("SELECT * FROM vw_dashboard_stats") or {}
        total_found = stats.get("total_found") or 0
        returned_found = stats.get("returned_found") or 0
        stats["recovery_rate"] = (
            round((returned_found / total_found) * 100, 1) if total_found > 0 else 0.0
        )

        category_breakdown = query_all(
            """
            SELECT
                c.category,
                COALESCE(l.lost_count, 0) AS lost_count,
                COALESCE(f.found_count, 0) AS found_count
            FROM (
                SELECT category FROM lost_items
                UNION
                SELECT category FROM found_items
            ) c
            LEFT JOIN (
                SELECT category, COUNT(*) AS lost_count
                FROM lost_items
                GROUP BY category
            ) l ON c.category = l.category
            LEFT JOIN (
                SELECT category, COUNT(*) AS found_count
                FROM found_items
                GROUP BY category
            ) f ON c.category = f.category
            ORDER BY (COALESCE(l.lost_count, 0) + COALESCE(f.found_count, 0)) DESC
            """
        )

        top_matches = query_all(
            """
            SELECT *
            FROM vw_detailed_matches
            WHERE match_status != 'DISMISSED'
            ORDER BY match_score DESC, matched_at DESC
            LIMIT 5
            """
        )

        recent_activity = query_all(
            """
            SELECT
                a.log_id,
                a.action_type,
                a.entity_type,
                a.entity_id,
                a.summary,
                a.created_at,
                u.full_name AS actor_name,
                u.role AS actor_role
            FROM activity_logs a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.created_at DESC, a.log_id DESC
            LIMIT 8
            """
        )

        return {
            "stats": stats,
            "category_breakdown": category_breakdown,
            "top_matches": top_matches,
            "recent_activity": recent_activity,
        }

    @app.route("/", methods=["GET"])
    @app.route("/dashboard", methods=["GET"])
    def dashboard_page():
        data = _build_dashboard_data()
        if wants_json_response():
            return jsonify({"ok": True, **data})
        return render_template("dashboard.html", **data)

    @app.route("/api/dashboard/stats", methods=["GET"])
    def api_dashboard_stats():
        data = _build_dashboard_data()
        return jsonify({"ok": True, **data})

    # =========================================================================
    # 3. LOST ITEMS GALLERY & REPORTING (WITH OPTIONAL IMAGE UPLOAD)
    # =========================================================================
    def _filter_lost_items(args) -> tuple[list[dict], dict]:
        q = clean_str(args.get("q"), 100)
        category = clean_str(args.get("category"), 60)
        status = clean_str(args.get("status"), 30)
        location = clean_str(args.get("location"), 100)
        date_from = clean_str(args.get("date_from"), 10)
        date_to = clean_str(args.get("date_to"), 10)

        # Uses `vw_public_lost_gallery` which strictly excludes private `identifying_marks`
        conditions = []
        params = []

        if q:
            like_q = f"%{q}%"
            conditions.append(
                "(item_name LIKE %s OR description LIKE %s OR COALESCE(brand_color, '') LIKE %s OR location_lost LIKE %s)"
            )
            params.extend([like_q, like_q, like_q, like_q])
        if category and category in VALID_CATEGORIES:
            conditions.append("category = %s")
            params.append(category)
        if status and status in ("OPEN", "MATCHED", "RECOVERED", "CLOSED"):
            conditions.append("status = %s")
            params.append(status)
        if location:
            conditions.append("location_lost LIKE %s")
            params.append(f"%{location}%")
        if date_from:
            conditions.append("date_lost >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("date_lost <= %s")
            params.append(date_to)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        items = query_all(
            f"""
            SELECT *
            FROM vw_public_lost_gallery
            {where_sql}
            ORDER BY date_lost DESC, lost_id DESC
            """,
            tuple(params),
        )
        filters = {
            "q": q,
            "category": category,
            "status": status,
            "location": location,
            "date_from": date_from,
            "date_to": date_to,
        }
        return items, filters

    @app.route("/lost-items", methods=["GET"])
    @app.route("/api/lost-items", methods=["GET"], endpoint="api_lost_items_list")
    def lost_items_gallery():
        items, filters = _filter_lost_items(request.args)
        if wants_json_response():
            return jsonify({"ok": True, "count": len(items), "filters": filters, "items": items})
        return render_template("lost_gallery.html", items=items, filters=filters)

    @app.route("/report/lost", methods=["GET", "POST"])
    @app.route("/api/lost-items", methods=["POST"], endpoint="api_lost_items_create")
    @login_required
    def report_lost_item():
        if request.method == "GET":
            return render_template("report_lost.html")

        payload = request.get_json(silent=True) if request.is_json else request.form
        item_name = clean_str(payload.get("item_name"), 120)
        category = clean_str(payload.get("category"), 60)
        brand_color = clean_str(payload.get("brand_color"), 100) or None
        location_lost = clean_str(payload.get("location_lost"), 120)
        date_lost_raw = clean_str(payload.get("date_lost"), 20)
        description = clean_str(payload.get("description"), 2000)
        identifying_marks = clean_str(payload.get("identifying_marks"), 255) or None

        errors = []
        if len(item_name) < 2:
            errors.append("Item name must be at least 2 characters.")
        if category not in VALID_CATEGORIES:
            errors.append("Please select a valid item category.")
        if len(location_lost) < 2:
            errors.append("Location lost must be at least 2 characters.")
        if len(description) < 5:
            errors.append("Please provide a clear description (at least 5 characters).")

        parsed_date = None
        try:
            parsed_date = validate_date_str(date_lost_raw, "Date lost")
        except ValueError as err:
            errors.append(str(err))

        image_path = None
        if not errors and "image" in request.files:
            try:
                image_path = save_uploaded_image(request.files.get("image"), prefix="lost")
            except ValueError as err:
                errors.append(str(err))

        if errors:
            err_msg = " ".join(errors)
            if wants_json_response():
                return jsonify({"ok": False, "error": err_msg}), 400
            flash(err_msg, "danger")
            return render_template("report_lost.html", form_data=payload), 400

        user = current_user()
        new_lost_id = execute_write(
            """
            INSERT INTO lost_items (
                user_id, item_name, category, brand_color, location_lost,
                date_lost, description, identifying_marks, image_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN')
            """,
            (
                user["user_id"],
                item_name,
                category,
                brand_color,
                location_lost,
                parsed_date.isoformat(),
                description,
                identifying_marks,
                image_path,
            ),
        )

        log_activity(
            user_id=user["user_id"],
            action_type="LOST_REPORTED",
            entity_type="LOST_ITEM",
            entity_id=new_lost_id,
            summary=f"{user['full_name']} reported lost '{item_name}' at {location_lost}.",
        )

        # Trigger Rule-Based Matching Engine
        updated_matches = run_matching_engine(triggered_by_user_id=user["user_id"])

        if wants_json_response():
            return (
                jsonify(
                    {
                        "ok": True,
                        "message": "Lost item reported and evaluated by matching engine.",
                        "lost_id": new_lost_id,
                        "image_path": image_path,
                        "matches_evaluated": updated_matches,
                    }
                ),
                201,
            )

        flash(
            f"Lost item '{item_name}' reported! ReFind evaluated active items and updated candidate matches.",
            "success",
        )
        return redirect(url_for("lost_items_gallery"))

    # =========================================================================
    # 4. FOUND ITEMS GALLERY & REPORTING (WITH OPTIONAL IMAGE UPLOAD)
    # =========================================================================
    def _filter_found_items(args) -> tuple[list[dict], dict]:
        q = clean_str(args.get("q"), 100)
        category = clean_str(args.get("category"), 60)
        status = clean_str(args.get("status"), 30)
        location = clean_str(args.get("location"), 100)
        date_from = clean_str(args.get("date_from"), 10)
        date_to = clean_str(args.get("date_to"), 10)

        # Uses `vw_public_found_gallery` which strictly excludes private `secret_detail`
        conditions = []
        params = []

        if q:
            like_q = f"%{q}%"
            conditions.append(
                "(item_name LIKE %s OR description LIKE %s OR COALESCE(brand_color, '') LIKE %s OR location_found LIKE %s)"
            )
            params.extend([like_q, like_q, like_q, like_q])
        if category and category in VALID_CATEGORIES:
            conditions.append("category = %s")
            params.append(category)
        if status and status in ("AVAILABLE", "MATCHED", "CLAIMED", "RETURNED"):
            conditions.append("status = %s")
            params.append(status)
        if location:
            conditions.append("location_found LIKE %s")
            params.append(f"%{location}%")
        if date_from:
            conditions.append("date_found >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("date_found <= %s")
            params.append(date_to)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        items = query_all(
            f"""
            SELECT *
            FROM vw_public_found_gallery
            {where_sql}
            ORDER BY date_found DESC, found_id DESC
            """,
            tuple(params),
        )
        filters = {
            "q": q,
            "category": category,
            "status": status,
            "location": location,
            "date_from": date_from,
            "date_to": date_to,
        }
        return items, filters

    @app.route("/found-items", methods=["GET"])
    @app.route("/api/found-items", methods=["GET"], endpoint="api_found_items_list")
    def found_items_gallery():
        items, filters = _filter_found_items(request.args)
        if wants_json_response():
            return jsonify({"ok": True, "count": len(items), "filters": filters, "items": items})
        return render_template("found_gallery.html", items=items, filters=filters)

    @app.route("/report/found", methods=["GET", "POST"])
    @app.route("/api/found-items", methods=["POST"], endpoint="api_found_items_create")
    @login_required
    def report_found_item():
        if request.method == "GET":
            return render_template("report_found.html")

        payload = request.get_json(silent=True) if request.is_json else request.form
        item_name = clean_str(payload.get("item_name"), 120)
        category = clean_str(payload.get("category"), 60)
        brand_color = clean_str(payload.get("brand_color"), 100) or None
        location_found = clean_str(payload.get("location_found"), 120)
        date_found_raw = clean_str(payload.get("date_found"), 20)
        description = clean_str(payload.get("description"), 2000)
        storage_location = (
            clean_str(payload.get("storage_location"), 150)
            or "Campus Lost & Found Desk (Main Admin Block)"
        )
        verification_question = (
            clean_str(payload.get("verification_question"), 255)
            or "Describe any unique mark, lock-screen wallpaper, contents, or serial/ID detail to prove ownership."
        )
        secret_detail = clean_str(payload.get("secret_detail"), 255) or None

        errors = []
        if len(item_name) < 2:
            errors.append("Item name must be at least 2 characters.")
        if category not in VALID_CATEGORIES:
            errors.append("Please select a valid item category.")
        if len(location_found) < 2:
            errors.append("Location found must be at least 2 characters.")
        if len(description) < 5:
            errors.append("Please provide a clear description (at least 5 characters).")

        parsed_date = None
        try:
            parsed_date = validate_date_str(date_found_raw, "Date found")
        except ValueError as err:
            errors.append(str(err))

        image_path = None
        if not errors and "image" in request.files:
            try:
                image_path = save_uploaded_image(request.files.get("image"), prefix="found")
            except ValueError as err:
                errors.append(str(err))

        if errors:
            err_msg = " ".join(errors)
            if wants_json_response():
                return jsonify({"ok": False, "error": err_msg}), 400
            flash(err_msg, "danger")
            return render_template("report_found.html", form_data=payload), 400

        user = current_user()
        new_found_id = execute_write(
            """
            INSERT INTO found_items (
                user_id, item_name, category, brand_color, location_found,
                date_found, description, storage_location, verification_question,
                secret_detail, image_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'AVAILABLE')
            """,
            (
                user["user_id"],
                item_name,
                category,
                brand_color,
                location_found,
                parsed_date.isoformat(),
                description,
                storage_location,
                verification_question,
                secret_detail,
                image_path,
            ),
        )

        log_activity(
            user_id=user["user_id"],
            action_type="FOUND_REPORTED",
            entity_type="FOUND_ITEM",
            entity_id=new_found_id,
            summary=f"{user['full_name']} reported found '{item_name}' at {location_found}.",
        )

        # Trigger Rule-Based Matching Engine
        updated_matches = run_matching_engine(triggered_by_user_id=user["user_id"])

        if wants_json_response():
            return (
                jsonify(
                    {
                        "ok": True,
                        "message": "Found item reported and evaluated by matching engine.",
                        "found_id": new_found_id,
                        "image_path": image_path,
                        "matches_evaluated": updated_matches,
                    }
                ),
                201,
            )

        flash(
            f"Found item '{item_name}' reported! ReFind evaluated active items and updated candidate matches.",
            "success",
        )
        return redirect(url_for("found_items_gallery"))

    # =========================================================================
    # 5. RULE-BASED MATCHING ENGINE & SCORE EXPLANATION ENDPOINTS
    # =========================================================================
    SCORING_FORMULA_RUBRIC = {
        "total_max_points": 100,
        "threshold_saved": 35,
        "high_confidence_threshold": 60,
        "criteria": [
            {"name": "Category Compatibility", "max_points": 30, "rule": "Exact category match = 30 pts; related category group = 12 pts."},
            {"name": "Item Name & Brand Similarity", "max_points": 25, "rule": "Token Jaccard/recall overlap + sequence similarity on normalized item name & brand/color."},
            {"name": "Campus Location Proximity", "max_points": 20, "rule": "Exact location = 20 pts; same canonical campus zone = 15–18 pts; shared location keywords = 8–16 pts."},
            {"name": "Date Compatibility", "max_points": 15, "rule": "Same day = 15 pts; 1–2d after lost = 13 pts; 3–5d = 10 pts; 6–14d = 7 pts; 1-day early tolerance = 5 pts; found >1d before lost applies timeline penalty."},
            {"name": "Description Keyword Overlap", "max_points": 10, "rule": "Shared meaningful tokens between lost and found descriptions (excluding stop words) = up to 10 pts."},
        ],
    }

    @app.route("/matches", methods=["GET"])
    @app.route("/api/matches", methods=["GET"], endpoint="api_matches_list")
    def matches_page():
        min_score_raw = clean_str(request.args.get("min_score"), 10)
        category = clean_str(request.args.get("category"), 60)
        status = clean_str(request.args.get("status"), 30)

        conditions = ["match_status != 'DISMISSED'"]
        params = []

        if min_score_raw:
            try:
                min_score_val = float(min_score_raw)
                conditions.append("match_score >= %s")
                params.append(min_score_val)
            except ValueError:
                pass

        if category and category in VALID_CATEGORIES:
            conditions.append("(lost_category = %s OR found_category = %s)")
            params.extend([category, category])

        if status and status in ("SUGGESTED", "CONFIRMED", "DISMISSED"):
            conditions = ["match_status = %s"] + conditions[1:]
            params.insert(0, status)

        where_sql = f"WHERE {' AND '.join(conditions)}"
        matches = query_all(
            f"""
            SELECT *
            FROM vw_detailed_matches
            {where_sql}
            ORDER BY match_score DESC, matched_at DESC
            """,
            tuple(params),
        )
        filters = {"min_score": min_score_raw, "category": category, "status": status}

        if wants_json_response():
            return jsonify(
                {
                    "ok": True,
                    "count": len(matches),
                    "scoring_rubric": SCORING_FORMULA_RUBRIC,
                    "filters": filters,
                    "matches": matches,
                }
            )
        return render_template(
            "matches.html",
            matches=matches,
            scoring_rubric=SCORING_FORMULA_RUBRIC,
            filters=filters,
        )

    @app.route("/matches/run", methods=["POST"])
    @app.route("/api/matches/run", methods=["POST"], endpoint="api_matches_run")
    @login_required
    def trigger_matching_engine():
        user = current_user()
        count = run_matching_engine(triggered_by_user_id=user["user_id"])
        if wants_json_response():
            return jsonify({"ok": True, "matches_evaluated": count})
        flash(f"Matching engine executed: {count} candidate match pair(s) evaluated and updated.", "info")
        return redirect(url_for("matches_page"))

    # =========================================================================
    # 6. OWNERSHIP CLAIMS & TRANSACTIONAL ADMIN VERIFICATION
    # =========================================================================
    @app.route("/claims/submit/<int:found_id>", methods=["GET", "POST"])
    @app.route("/api/claims", methods=["POST"], endpoint="api_claims_create")
    @login_required
    def submit_claim_route(found_id: int | None = None):
        user = current_user()

        if request.method == "GET":
            item = query_one(
                "SELECT * FROM vw_public_found_gallery WHERE found_id = %s",
                (found_id,),
            )
            if not item:
                flash("Found item not found.", "danger")
                return redirect(url_for("found_items_gallery"))

            my_lost_items = query_all(
                """
                SELECT lost_id, item_name, category, date_lost, location_lost
                FROM lost_items
                WHERE user_id = %s AND status IN ('OPEN', 'MATCHED')
                ORDER BY date_lost DESC
                """,
                (user["user_id"],),
            )
            return render_template("claim_submit.html", item=item, my_lost_items=my_lost_items)

        payload = request.get_json(silent=True) if request.is_json else request.form
        target_found_id = found_id or int(payload.get("found_id") or 0)
        proof_description = clean_str(payload.get("proof_description"), 2000)
        id_card_reference = clean_str(payload.get("id_card_reference") or user["student_id"], 100)
        lost_id_raw = payload.get("lost_id")
        lost_id = int(lost_id_raw) if lost_id_raw and str(lost_id_raw).isdigit() else None

        try:
            new_claim_id = submit_ownership_claim(
                found_id=target_found_id,
                claimant_id=user["user_id"],
                proof_description=proof_description,
                id_card_reference=id_card_reference,
                lost_id=lost_id,
            )
        except ValueError as err:
            if wants_json_response():
                return jsonify({"ok": False, "error": str(err)}), 400
            flash(str(err), "danger")
            return redirect(url_for("submit_claim_route", found_id=target_found_id))

        if wants_json_response():
            return (
                jsonify(
                    {
                        "ok": True,
                        "message": "Ownership claim submitted for administrator verification.",
                        "claim_id": new_claim_id,
                        "found_id": target_found_id,
                    }
                ),
                201,
            )

        flash(
            f"Ownership claim #{new_claim_id} submitted! A campus administrator will verify your proof.",
            "success",
        )
        return redirect(url_for("my_claims_page"))

    @app.route("/my-claims", methods=["GET"])
    @app.route("/my-dashboard", methods=["GET"], endpoint="my_dashboard_page")
    @app.route("/api/claims/mine", methods=["GET"], endpoint="api_claims_mine")
    @login_required
    def my_claims_page():
        user = current_user()
        claims = get_claims_for_user(user["user_id"])
        my_lost_items = query_all(
            """
            SELECT *
            FROM vw_public_lost_gallery
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user["user_id"],),
        )
        my_found_items = query_all(
            """
            SELECT *
            FROM vw_public_found_gallery
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user["user_id"],),
        )
        if wants_json_response():
            return jsonify(
                {
                    "ok": True,
                    "count": len(claims),
                    "claims": claims,
                    "my_lost_items": my_lost_items,
                    "my_found_items": my_found_items,
                }
            )
        return render_template(
            "my_claims.html",
            claims=claims,
            my_lost_items=my_lost_items,
            my_found_items=my_found_items,
        )

    @app.route("/admin/claims", methods=["GET"])
    @app.route("/api/admin/claims", methods=["GET"], endpoint="api_admin_claims_list")
    @admin_required
    def admin_claims_page():
        status_filter = clean_str(request.args.get("status"), 20).upper()
        claims = get_all_claims_for_admin(status_filter)
        if wants_json_response():
            return jsonify({"ok": True, "count": len(claims), "status_filter": status_filter, "claims": claims})
        return render_template("admin_claims.html", claims=claims, status_filter=status_filter)

    @app.route("/admin/claims/<int:claim_id>/review", methods=["POST"])
    @app.route("/api/admin/claims/<int:claim_id>/review", methods=["POST"], endpoint="api_admin_review_claim")
    @admin_required
    def admin_review_claim(claim_id: int):
        user = current_user()
        payload = request.get_json(silent=True) if request.is_json else request.form
        decision = clean_str(payload.get("decision"), 20).upper()
        admin_remarks = clean_str(payload.get("admin_remarks"), 255)

        try:
            outcome = review_claim_transactional(
                claim_id=claim_id,
                admin_user_id=user["user_id"],
                decision=decision,
                admin_remarks=admin_remarks,
            )
        except ValueError as err:
            if wants_json_response():
                return jsonify({"ok": False, "error": str(err)}), 400
            flash(str(err), "danger")
            return redirect(url_for("admin_claims_page"))

        if wants_json_response():
            return jsonify({"ok": True, "message": f"Claim #{claim_id} {decision.lower()}.", "outcome": outcome})

        flash(
            f"Claim #{claim_id} marked as {decision}. Item and match statuses updated atomically.",
            "success" if decision == "APPROVED" else "info",
        )
        return redirect(url_for("admin_claims_page"))

    # =========================================================================
    # 7. ACTIVITY LOGS TIMELINE
    # =========================================================================
    @app.route("/activity", methods=["GET"])
    @app.route("/api/activity", methods=["GET"], endpoint="api_activity_list")
    def activity_page():
        action_filter = clean_str(request.args.get("action_type"), 40).upper()
        params = []
        where_sql = ""
        if action_filter:
            where_sql = "WHERE a.action_type = %s"
            params.append(action_filter)

        logs = query_all(
            f"""
            SELECT
                a.log_id,
                a.user_id,
                a.action_type,
                a.entity_type,
                a.entity_id,
                a.summary,
                a.created_at,
                u.full_name AS actor_name,
                u.student_id AS actor_student_id,
                u.role AS actor_role
            FROM activity_logs a
            LEFT JOIN users u ON a.user_id = u.user_id
            {where_sql}
            ORDER BY a.created_at DESC, a.log_id DESC
            LIMIT 100
            """,
            tuple(params),
        )
        if wants_json_response():
            return jsonify({"ok": True, "count": len(logs), "action_type": action_filter, "logs": logs})
        return render_template("activity.html", logs=logs, action_filter=action_filter)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=Config.PORT, debug=Config.DEBUG)
