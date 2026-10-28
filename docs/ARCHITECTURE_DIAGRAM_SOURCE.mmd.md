# ReFind — System Architecture Diagram Sources (`ARCHITECTURE_DIAGRAM_SOURCE.mmd.md`)

This file contains both the **Simplified Presentation-Friendly Architecture Diagram** (for 16:9 slide projection) and the **Detailed Technical Reference Architecture Diagram**, verified against the exact routes in [`app.py`](file:///C:/Projects/ReFind/app.py) and [`database/schema.sql`](file:///C:/Projects/ReFind/database/schema.sql).

---

## 1. Simplified Presentation-Friendly Architecture Diagram (Slide Version)

Rendered to [`docs/SYSTEM_ARCHITECTURE_PRESENTATION.svg`](file:///C:/Projects/ReFind/docs/SYSTEM_ARCHITECTURE_PRESENTATION.svg) and [`docs/SYSTEM_ARCHITECTURE_PRESENTATION.png`](file:///C:/Projects/ReFind/docs/SYSTEM_ARCHITECTURE_PRESENTATION.png) (`1920×1080` widescreen).

```mermaid
flowchart LR
    subgraph P1["Tier 1: Browser UI"]
        Views1["Jinja2 HTML5 Templates\n+ Editorial Minimalism CSS\n+ Vanilla JS (main.js)"]
    end

    subgraph P2["Tier 2: Flask Controller (app.py)"]
        Routes["SSR Page Routes & REST JSON APIs\n/, /lost-items, /found-items, /matches\n/api/lost-items, /api/found-items,\n/api/matches, /api/claims, /api/claims/mine"]
        Guards["Security & RBAC Guards\nSession Auth + HMAC CSRF + %s SQL"]
    end

    subgraph P3["Tier 3: Domain Services (services/)"]
        SecUp["security.py & upload_service.py\nscrypt Hashing + Magic-Byte Check"]
        Matcher["matching_engine.py\n0–100 Rule-Based Scoring (5 Factors)"]
        ClaimSvc["claim_service.py\nACID Transaction (SELECT FOR UPDATE)"]
    end

    subgraph P4["Tier 4: MySQL 3NF (refind_db :3307)"]
        SQLViews["4 SQL Views (SQL SECURITY INVOKER)\nHides identifying_marks & secret_detail"]
        Tables3NF["6 Normalized 3NF Tables (InnoDB)\n6 PKs • 9 FKs • 5 UQs • 8 CHECKs • 18 Indexes"]
    end

    P1 <-->|"HTTP + CSRF"| P2
    P2 <-->|"Domain Calls"| P3
    P3 <-->|"Parameterized SQL\n& ACID Transactions"| P4
```

---

## 2. Detailed Technical Reference Architecture Diagram (Documentation Version)

Rendered to [`docs/SYSTEM_ARCHITECTURE.svg`](file:///C:/Projects/ReFind/docs/SYSTEM_ARCHITECTURE.svg) and [`docs/SYSTEM_ARCHITECTURE.png`](file:///C:/Projects/ReFind/docs/SYSTEM_ARCHITECTURE.png).

```mermaid
flowchart LR
    subgraph Client["1. Client Presentation Layer (Browser)"]
        UI["HTML5 + Jinja2 Views (13 Templates)\nEditorial Minimalism CSS (#FAF9F6 / #20243A / #A895D6)"]
        JS["Vanilla JS (main.js)\n- FileReader Drag & Drop Preview\n- :user-invalid / aria-invalid sync\n- IntersectionObserver Motion"]
    end

    subgraph Controller["2. Web & API Layer (Flask app.py)"]
        HTMLRoutes["HTML Page Routes\n/, /dashboard, /login, /register, /logout,\n/lost-items, /found-items, /report/lost, /report/found,\n/matches, /matches/run, /claims/submit/<found_id>,\n/my-claims, /my-dashboard, /admin/claims,\n/admin/claims/<claim_id>/review, /activity"]
        APIRoutes["REST JSON Endpoints (/api/*)\n/api/auth/csrf, /api/auth/me, /api/auth/login,\n/api/auth/register, /api/auth/logout, /api/dashboard/stats,\n/api/lost-items, /api/found-items, /api/matches,\n/api/matches/run, /api/claims, /api/claims/mine,\n/api/admin/claims, /api/admin/claims/<claim_id>/review,\n/api/activity"]
    end

    subgraph Services["3. Domain & Security Services (services/)"]
        Sec["security.py\n- Werkzeug scrypt Hashing\n- Session Auth & RBAC\n- HMAC CSRF Protection"]
        Up["upload_service.py\n- Magic-Byte Header Inspection\n- UUID Filename Generation\n- static/uploads/ Storage"]
        Match["matching_engine.py\n- 5-Factor Rule Engine (0-100)\n  Cat(30) + Name(25) + Loc(20)\n  + Date(15) + Desc(10)"]
        Claim["claim_service.py\n- ACID Claim Approval Transaction\n- SELECT ... FOR UPDATE Locking\n- Competing Claim Auto-Rejection"]
    end

    subgraph Database["4. Relational Database Layer (MySQL 26.7 :3307 — refind_db)"]
        Views["4 SQL Views (SQL SECURITY INVOKER)\n- vw_public_lost_gallery (hides identifying_marks)\n- vw_public_found_gallery (hides secret_detail)\n- vw_detailed_matches (4 INNER JOINs across 4 tables, users ×2)\n- vw_dashboard_stats (11 real-time scalar subquery KPIs)"]
        Tables["6 Normalized 3NF Tables (InnoDB)\n- users (PK: user_id, UQ: student_id, email)\n- lost_items (PK: lost_id, FK: user_id)\n- found_items (PK: found_id, FK: user_id)\n- matches (PK: match_id, UQ: lost_id+found_id)\n- claims (PK: claim_id, UQ: found_id+claimant_id, UQ: approved_found_id)\n- activity_logs (PK: log_id, FK: user_id)\n[6 PKs • 9 FKs • 5 UQs • 8 CHECKs • 18 Secondary Indexes]"]
    end

    UI <-->|"HTTP GET / POST\n+ CSRF Token"| HTMLRoutes
    JS <-->|"Multipart Form / Fetch"| APIRoutes
    HTMLRoutes --> Sec
    APIRoutes --> Sec
    HTMLRoutes --> Up
    HTMLRoutes --> Match
    HTMLRoutes --> Claim
    HTMLRoutes -->|"Parameterized SQL\n(refind_app: SELECT, INSERT, UPDATE)"| Views
    Match -->|"UPSERT Candidate Scores"| Tables
    Claim -->|"BEGIN ... FOR UPDATE ... COMMIT"| Tables
    Views --> Tables
```
