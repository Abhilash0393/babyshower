import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PHOTO_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPT_LIMIT = 5


def configured_database_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def create_app(test_config=None):
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    secret_key = os.getenv("SECRET_KEY")
    admin_pin = os.getenv("ADMIN_PIN")
    public_url = urlparse(public_base_url)
    if public_base_url and (public_url.scheme != "https" or not public_url.netloc):
        raise RuntimeError("PUBLIC_BASE_URL must use HTTPS for a deployed service.")
    if public_base_url and (
        not secret_key or not admin_pin or os.getenv("COOKIE_SECURE") != "1"
    ):
        raise RuntimeError(
            "Set SECRET_KEY, ADMIN_PIN, and COOKIE_SECURE=1 when PUBLIC_BASE_URL is configured."
        )
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret_key or secrets.token_hex(32),
        ADMIN_PIN=admin_pin or "2468",
        PUBLIC_BASE_URL=public_base_url,
        DATABASE_PATH=str(configured_database_path(os.getenv(
            "DATABASE_PATH", "instance/baby_votes.sqlite3"
        ))),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect_db():
        conn = sqlite3.connect(app.config["DATABASE_PATH"], timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db():
        with connect_db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS votes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                choice TEXT NOT NULL CHECK(choice IN ('girl','boy')),
                source TEXT NOT NULL CHECK(source IN ('qr','booth')),
                browser_token TEXT,
                created_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS admin_login_attempts(
                ip_address TEXT PRIMARY KEY,
                window_started_at TEXT NOT NULL,
                attempts INTEGER NOT NULL
            )""")
            for key, value in {
                "voting_open": "1",
                "display_mode": "auto",
                "special_message": "A little more love is on the way",
                "version": "0",
            }.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                    (key, value),
                )

    def get_setting(conn, key, default=""):
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(conn, key, value):
        conn.execute("""INSERT INTO settings(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value)))

    def results_payload(conn=None):
        if conn is None:
            with connect_db() as connection:
                return results_payload(connection)
        row = conn.execute("""SELECT COUNT(*) total,
            SUM(CASE WHEN choice='girl' THEN 1 ELSE 0 END) girl,
            SUM(CASE WHEN choice='boy' THEN 1 ELSE 0 END) boy,
            SUM(CASE WHEN source='qr' THEN 1 ELSE 0 END) qr,
            SUM(CASE WHEN source='booth' THEN 1 ELSE 0 END) booth,
            COALESCE(MAX(id),0) last_id FROM votes""").fetchone()
        total = row["total"] or 0
        girl = row["girl"] or 0
        boy = row["boy"] or 0
        return {
            "total": total,
            "girl": girl,
            "boy": boy,
            "qr": row["qr"] or 0,
            "booth": row["booth"] or 0,
            "girl_percent": round(girl * 100 / total) if total else 0,
            "boy_percent": round(boy * 100 / total) if total else 0,
            "last_id": row["last_id"],
            "version": int(get_setting(conn, "version", "0")),
            "voting_open": get_setting(conn, "voting_open", "1") == "1",
            "display_mode": get_setting(conn, "display_mode", "auto"),
            "special_message": get_setting(
                conn, "special_message", "A little more love is on the way"
            ),
            "server_time": utc_now(),
        }

    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    @app.context_processor
    def template_security_context():
        return {"csrf_token": csrf_token()}

    @app.before_request
    def protect_mutations():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if expected and supplied and secrets.compare_digest(expected, supplied):
            return None
        if request.path == "/admin":
            return render_template(
                "admin.html",
                logged_in=bool(session.get("is_admin")),
                error="Your session expired. Please reload and try again.",
                base_url=app.config["PUBLIC_BASE_URL"] or request.url_root.rstrip("/"),
            ), 400
        return jsonify({"error": "Invalid or expired request token. Reload and try again."}), 400

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("is_admin"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Admin login required"}), 401
                return redirect(url_for("admin"))
            return fn(*args, **kwargs)
        return wrapper

    def json_object():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def login_status(ip_address):
        now = datetime.now(timezone.utc)
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT window_started_at, attempts FROM admin_login_attempts WHERE ip_address=?",
                (ip_address,),
            ).fetchone()
            if row:
                started = datetime.fromisoformat(row["window_started_at"])
                if now - started < LOGIN_WINDOW and row["attempts"] >= LOGIN_ATTEMPT_LIMIT:
                    return False
        return True

    def record_login_attempt(ip_address, succeeded):
        now = datetime.now(timezone.utc)
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT window_started_at, attempts FROM admin_login_attempts WHERE ip_address=?",
                (ip_address,),
            ).fetchone()
            if succeeded:
                conn.execute("DELETE FROM admin_login_attempts WHERE ip_address=?", (ip_address,))
            elif row and now - datetime.fromisoformat(row["window_started_at"]) < LOGIN_WINDOW:
                conn.execute(
                    "UPDATE admin_login_attempts SET attempts=attempts+1 WHERE ip_address=?",
                    (ip_address,),
                )
            else:
                conn.execute("""INSERT INTO admin_login_attempts(
                    ip_address,window_started_at,attempts) VALUES(?,?,1)
                    ON CONFLICT(ip_address) DO UPDATE SET
                    window_started_at=excluded.window_started_at,attempts=1""",
                    (ip_address, now.isoformat()),
                )

    def admin_action(data):
        action = data.get("action")
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if action == "open":
                set_setting(conn, "voting_open", "1")
            elif action == "close":
                set_setting(conn, "voting_open", "0")
            elif action == "reset":
                if data.get("confirm") is not True:
                    return jsonify({"error": "Explicit confirmation required"}), 400
                conn.execute("DELETE FROM votes")
                set_setting(conn, "version", str(int(get_setting(conn, "version", "0")) + 1))
            elif action == "display":
                mode = data.get("mode")
                if mode not in ("auto", "slideshow", "meter", "special"):
                    return jsonify({"error": "Unsupported display mode"}), 400
                set_setting(conn, "display_mode", mode)
                if "special_message" in data:
                    message = data["special_message"]
                    if not isinstance(message, str):
                        return jsonify({"error": "Special message must be text"}), 400
                    set_setting(conn, "special_message", message.strip()[:240])
            elif action == "logout":
                session.clear()
                return jsonify({"logged_out": True})
            else:
                return jsonify({"error": "Unsupported action"}), 400
            return jsonify(results_payload(conn))

    @app.get("/")
    def home():
        return redirect(url_for("vote", mode="qr"))

    @app.get("/vote")
    def vote():
        mode = "booth" if request.args.get("mode") == "booth" else "qr"
        if not session.get("browser_token"):
            session["browser_token"] = secrets.token_urlsafe(24)
        csrf_token()
        return render_template("vote.html", mode=mode)

    @app.get("/display")
    def display():
        return render_template("display.html")

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        error = None
        if request.method == "POST":
            ip_address = request.remote_addr or "unknown"
            if not login_status(ip_address):
                error = "Too many incorrect attempts. Please wait 15 minutes before trying again."
                return render_template(
                    "admin.html", logged_in=False, error=error,
                    base_url=app.config["PUBLIC_BASE_URL"] or request.url_root.rstrip("/"),
                ), 429
            valid = secrets.compare_digest(request.form.get("pin", ""), app.config["ADMIN_PIN"])
            record_login_attempt(ip_address, valid)
            if valid:
                session.clear()
                session["is_admin"] = True
                return redirect(url_for("admin"))
            error = "Incorrect PIN. Please try again."
        csrf_token()
        return render_template(
            "admin.html",
            logged_in=bool(session.get("is_admin")),
            error=error,
            base_url=app.config["PUBLIC_BASE_URL"] or request.url_root.rstrip("/"),
        )

    @app.post("/api/vote")
    def api_vote():
        data = json_object()
        choice = data.get("choice")
        source = data.get("source", "qr")
        if choice not in ("girl", "boy") or source not in ("qr", "booth"):
            return jsonify({"error": "Choose Baby Girl or Baby Boy."}), 400

        token = session.get("browser_token")
        if not token:
            token = secrets.token_urlsafe(24)
            session["browser_token"] = token
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if get_setting(conn, "voting_open", "1") != "1":
                return jsonify({"error": "Voting is closed. Thank you for joining!"}), 403
            if source == "qr":
                existing = conn.execute(
                    "SELECT choice FROM votes WHERE source='qr' AND browser_token=?",
                    (token,),
                ).fetchone()
                if existing:
                    return jsonify({
                        "error": "A prediction was already recorded in this browser.",
                        "already_voted": True,
                        "recorded_choice": existing["choice"],
                    }), 409
            conn.execute(
                "INSERT INTO votes(choice,source,browser_token,created_at) VALUES(?,?,?,?)",
                (choice, source, token, utc_now()),
            )
            set_setting(conn, "version", str(int(get_setting(conn, "version", "0")) + 1))
            payload = results_payload(conn)
        payload["accepted"] = True
        return jsonify(payload), 201

    @app.get("/api/results")
    def api_results():
        return jsonify(results_payload())

    @app.route("/api/admin", methods=["GET", "POST"])
    @admin_required
    def api_admin():
        if request.method == "GET":
            return jsonify(results_payload())
        return admin_action(json_object())

    @app.post("/api/voting-control")
    @admin_required
    def voting_control():
        data = json_object()
        if data.get("action") not in ("open", "close", "reset"):
            return jsonify({"error": "Unsupported action"}), 400
        return admin_action(data)

    @app.post("/api/display-settings")
    @admin_required
    def display_settings():
        data = json_object()
        data["action"] = "display"
        return admin_action(data)

    @app.get("/api/photos")
    def api_photos():
        photo_dir = Path(app.static_folder) / "photos"
        photos = sorted(
            (path for path in photo_dir.iterdir()
             if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS),
            key=lambda path: path.name.casefold(),
        )
        return jsonify({
            "photos": [
                url_for("static", filename=f"photos/{path.name}") for path in photos
            ]
        })

    @app.get("/qr.png")
    def qr_png():
        base = app.config["PUBLIC_BASE_URL"] or request.url_root.rstrip("/")
        image = qrcode.make(base + url_for("vote", mode="qr"))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", download_name="baby-prediction-qr.png")

    @app.get("/health")
    def health():
        with connect_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok"})

    init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
