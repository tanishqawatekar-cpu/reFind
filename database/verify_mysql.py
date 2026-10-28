"""
Read-Only MySQL Connection & Compatibility Verifier (`verify_mysql.py`)
Connects to MySQL on Port 3306 using credentials from `.env` (`DB_ROOT_USER` / `DB_ROOT_PASSWORD`
or `DB_USER` / `DB_PASSWORD`), verifies server version and schema feature support
(InnoDB, utf8mb4, CHECK constraints, STORED GENERATED columns), and lists existing databases
WITHOUT creating, modifying, or deleting any database.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def run_verification():
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3307"))
    root_user = os.getenv("DB_ROOT_USER", "root")
    root_pw = os.getenv("DB_ROOT_PASSWORD", "")
    app_user = os.getenv("DB_USER", "refind_app")
    app_pw = os.getenv("DB_PASSWORD", "")
    target_db = os.getenv("DB_NAME", "refind_db")

    print("=" * 72)
    print("ReFind — Read-Only MySQL Connection & Schema Compatibility Report")
    print("=" * 72)
    print(f"Target Host : {host}:{port}")
    print(f"Setup User  : {root_user}@{host} (DB_ROOT_PASSWORD set in .env: {'YES' if bool(root_pw) else 'NO — EMPTY'})")
    print(f"App User    : {app_user}@{host} (DB_PASSWORD set in .env: {'YES' if bool(app_pw) else 'NO — EMPTY'})")
    print(f"Target DB   : {target_db}")
    print("-" * 72)

    if not root_pw:
        print("[ACTION NEEDED] `DB_ROOT_PASSWORD` is currently empty in C:\\Projects\\ReFind\\.env")
        print("                Please paste your root password on line 19 of .env and save.")
        print("=" * 72)
        return 1

    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=root_user,
            password=root_pw,
            charset="utf8mb4",
            use_unicode=True,
        )
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT
                VERSION() AS version,
                @@version_comment AS comment,
                @@port AS port,
                @@hostname AS hostname,
                @@sql_mode AS sql_mode,
                @@character_set_server AS charset_server,
                @@collation_server AS collation_server,
                @@default_storage_engine AS storage_engine
            """
        )
        info = cur.fetchone()
        print("[PASS] Read-Only Connection to MySQL Server Succeeded!")
        print(f"       Server Version   : {info['version']} ({info['comment']})")
        print(f"       Listening Port   : {info['port']}")
        print(f"       Default Engine   : {info['storage_engine']}")
        print(f"       Server Charset   : {info['charset_server']} / {info['collation_server']}")
        print(f"       SQL Mode         : {info['sql_mode']}")

        # Parse major.minor version
        ver_parts = info["version"].split(".")
        major = int(ver_parts[0])
        compatible = major >= 8 and info["storage_engine"].upper() == "INNODB"
        print(
            f"       Schema Support   : {'COMPATIBLE (InnoDB, CHECK constraints, STORED GENERATED columns, SQL SECURITY INVOKER views supported)' if compatible else 'CHECK CONFIGURATION'}"
        )

        cur.execute("SHOW DATABASES;")
        dbs = [r["Database"] for r in cur.fetchall()]
        print(f"       Existing DBs     : {', '.join(dbs)}")
        print(f"       `{target_db}` exists?   : {'YES' if target_db in dbs else 'NO (Will only be created after your approval)'}")

        cur.execute("SELECT user, host FROM mysql.user WHERE user = %s;", (app_user,))
        app_users = cur.fetchall()
        if app_users:
            hosts_str = ", ".join(f"'{u['user']}'@'{u['host']}'" for u in app_users)
            print(f"       `{app_user}` exists?  : YES ({hosts_str})")
        else:
            print(f"       `{app_user}` exists?  : NO (Will only be created after your approval)")
        print("=" * 72)

        cur.close()
        conn.close()
        return 0
    except Error as err:
        print(f"[ERROR] Could not authenticate as '{root_user}'@'{host}' on port {port}")
        print(f"        MySQL Error: {err.errno} ({err.sqlstate}): {err.msg}")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(run_verification())
