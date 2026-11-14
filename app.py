import json
import math
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlparse

import qrcode
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PHOTO_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPT_LIMIT = 5
INVITE_VERSION = "5"


def configured_database_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def format_display_date(value):
    day = value.day
    ordinal = "th" if 11 <= day % 100 <= 13 else {
        1: "st", 2: "nd", 3: "rd"
    }.get(day % 10, "th")
    return f"{value.strftime('%A')}, {day}{ordinal} {value.strftime('%B')}"


def normalized_slide_layout(value):
    layout = value if isinstance(value, dict) else {}
    positions = {
        "top-left", "top-right", "center-left", "center-right",
        "bottom-left", "bottom-right", "center",
    }
    alignments = {"left", "center", "right"}
    shadows = {"none", "light", "dark"}
    overlays = {
        "none", "left-light", "right-light", "top-light", "bottom-light",
        "left-dark", "right-dark", "top-dark", "bottom-dark",
    }
    object_positions = {
        f"{horizontal} {vertical}"
        for horizontal in ("left", "center", "right")
        for vertical in ("top", "center", "bottom")
    }

    def bounded_number(key, default, minimum, maximum):
        candidate = layout.get(key, default)
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
            return default
        try:
            if not math.isfinite(candidate):
                return default
        except OverflowError:
            return default
        return min(maximum, max(minimum, candidate))

    color = layout.get("color", "#fffaf0")
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#fffaf0"
    position = layout.get("position")
    alignment = layout.get("alignment")
    shadow = layout.get("shadow")
    overlay = layout.get("overlay")
    font_family = layout.get("fontFamily")
    object_position = layout.get("objectPosition")
    subject_area = layout.get("subjectArea", {})
    if not isinstance(subject_area, dict):
        subject_area = {}

    minimum_font = bounded_number("minFontPx", 20, 12, 72)
    maximum_font = max(minimum_font, bounded_number("maxFontPx", 54, 18, 88))
    safe_area = {
        edge: bounded_number_from(subject_area.get(edge), fallback)
        for edge, fallback in (("left", 0), ("top", 0), ("right", 100), ("bottom", 100))
    }
    if safe_area["right"] < safe_area["left"]:
        safe_area["right"] = safe_area["left"]
    if safe_area["bottom"] < safe_area["top"]:
        safe_area["bottom"] = safe_area["top"]

    return {
        "position": (
            position if isinstance(position, str) and position in positions else "center"
        ),
        "alignment": (
            alignment if isinstance(alignment, str) and alignment in alignments else "center"
        ),
        "maxWidthPct": bounded_number("maxWidthPct", 48, 18, 80),
        "mobileMaxWidthPct": bounded_number(
            "mobileMaxWidthPct",
            bounded_number("maxWidthPct", 48, 18, 80),
            12,
            80,
        ),
        "minFontPx": minimum_font,
        "preferredFontVw": bounded_number("preferredFontVw", 3.2, 0.8, 8),
        "maxFontPx": maximum_font,
        "color": color,
        "shadow": shadow if isinstance(shadow, str) and shadow in shadows else "dark",
        "lineHeight": bounded_number("lineHeight", 1.15, 0.9, 1.8),
        "paddingPx": bounded_number("paddingPx", 0, 0, 32),
        "insetXVw": bounded_number("insetXVw", 5, 1, 15),
        "insetYVh": bounded_number("insetYVh", 5, 1, 15),
        "mobileInsetYVh": bounded_number(
            "mobileInsetYVh",
            bounded_number("insetYVh", 5, 1, 15),
            1,
            15,
        ),
        "overlay": (
            overlay if isinstance(overlay, str) and overlay in overlays else "none"
        ),
        "fontFamily": (
            font_family
            if isinstance(font_family, str) and font_family in {"serif", "sans"}
            else "serif"
        ),
        "fontWeight": int(bounded_number("fontWeight", 600, 300, 800)),
        "objectPosition": (
            object_position
            if isinstance(object_position, str) and object_position in object_positions
            else "center center"
        ),
        "subjectArea": safe_area,
    }


def bounded_number_from(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        if not math.isfinite(value):
            return default
    except OverflowError:
        return default
    return min(100, max(0, value))


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
        EVENT_TITLE=os.getenv("EVENT_TITLE", "Monica's Baby Shower"),
        EVENT_DATE=os.getenv("EVENT_DATE", "2026-11-22"),
        EVENT_VENUE=os.getenv("EVENT_VENUE", "Highland Hotel"),
        EVENT_TIME=os.getenv("EVENT_TIME", "11:00 AM onwards"),
        EVENT_DIRECTIONS_QUERY=os.getenv(
            "EVENT_DIRECTIONS_QUERY",
            "Highland Hotel, Opp. Sapthagiri College, Chikkasandra",
        ),
        PHOTO_DIR=str(Path(app.static_folder) / "photos"),
        PHOTO_MANIFEST_PATH=os.getenv(
            "PHOTO_MANIFEST_PATH",
            str(Path(app.static_folder) / "photos" / "manifest.json"),
        ),
        DISPLAY_MUSIC_FILE=os.getenv(
            "DISPLAY_MUSIC_FILE",
            "alex-morgan-india-drums-tabla-sitar-ethnic-mood-587419.mp3",
        ).strip(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    try:
        event_date = date.fromisoformat(app.config["EVENT_DATE"])
    except (TypeError, ValueError) as error:
        raise RuntimeError("EVENT_DATE must use YYYY-MM-DD format.") from error

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
                "slide_duration": "15",
                "slideshow_paused": "0",
                "music_enabled": "1",
                "display_command": "",
                "command_version": "0",
                "current_slide_id": "",
                "control_version": "0",
                "version": "0",
                "vote_sequence": "0",
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

    def configured_music_url():
        filename = app.config["DISPLAY_MUSIC_FILE"]
        if not isinstance(filename, str) or not filename.strip():
            return ""
        relative_path = Path(filename)
        music_root = (Path(app.static_folder) / "music").resolve()
        music_path = (music_root / relative_path).resolve()
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not music_path.is_relative_to(music_root)
            or music_path.suffix.lower() not in {".mp3", ".ogg", ".wav"}
            or not music_path.is_file()
        ):
            app.logger.warning("Configured display music file is unavailable or invalid.")
            return ""
        return url_for("static", filename=f"music/{relative_path.as_posix()}")

    def slides_payload():
        manifest_path = Path(app.config["PHOTO_MANIFEST_PATH"])
        photo_root = Path(app.config["PHOTO_DIR"]).resolve()
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            app.logger.warning("Slideshow manifest is missing: %s", manifest_path)
            return []
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            app.logger.warning("Could not read slideshow manifest: %s", error)
            return []
        if not isinstance(entries, list):
            app.logger.warning("Slideshow manifest must contain a JSON list.")
            return []

        slides = []
        seen_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            slide_id = entry.get("id")
            image = entry.get("image")
            if (
                not isinstance(slide_id, str)
                or not slide_id.strip()
                or slide_id in seen_ids
                or not isinstance(image, str)
                or not image.startswith("/static/photos/")
            ):
                continue
            relative_path = Path(image.removeprefix("/static/photos/"))
            image_path = (photo_root / relative_path).resolve()
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or not image_path.is_relative_to(photo_root)
                or image_path.suffix.lower() not in PHOTO_EXTENSIONS
                or not image_path.is_file()
            ):
                app.logger.warning("Skipping invalid slideshow image entry: %s", slide_id)
                continue
            seen_ids.add(slide_id)
            slides.append({
                "id": slide_id,
                "image": url_for(
                    "static", filename=f"photos/{relative_path.as_posix()}"
                ),
                "caption": str(entry.get("caption", "")).strip()[:240],
                "category": str(entry.get("category", "")).strip()[:80],
                "author": str(entry.get("author", "")).strip()[:100],
                "text_layout": normalized_slide_layout(entry.get("textLayout")),
            })
        return slides

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
            "vote_sequence": int(get_setting(conn, "vote_sequence", "0")),
            "voting_open": get_setting(conn, "voting_open", "1") == "1",
            "display_mode": get_setting(conn, "display_mode", "auto"),
            "special_message": get_setting(
                conn, "special_message", "A little more love is on the way"
            ),
            "slide_duration": int(get_setting(conn, "slide_duration", "15")),
            "slideshow_paused": get_setting(conn, "slideshow_paused", "0") == "1",
            "music_enabled": get_setting(conn, "music_enabled", "1") == "1",
            "music_url": configured_music_url(),
            "display_command": get_setting(conn, "display_command"),
            "command_version": int(get_setting(conn, "command_version", "0")),
            "current_slide_id": get_setting(conn, "current_slide_id"),
            "control_version": int(get_setting(conn, "control_version", "0")),
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
                event_title=app.config["EVENT_TITLE"],
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
                message = data.get("special_message")
                if message is not None and not isinstance(message, str):
                    return jsonify({"error": "Special message must be text"}), 400
                set_setting(conn, "display_mode", mode)
                if message is not None:
                    set_setting(conn, "special_message", message.strip()[:240])
                set_setting(
                    conn,
                    "control_version",
                    str(int(get_setting(conn, "control_version", "0")) + 1),
                )
            elif action == "slideshow":
                duration = data.get("duration")
                paused = data.get("paused")
                music_enabled = data.get("music_enabled")
                command = data.get("command")
                if not any(key in data for key in ("duration", "paused", "music_enabled", "command")):
                    return jsonify({"error": "No slideshow setting was provided."}), 400
                if "duration" in data:
                    if (
                        isinstance(duration, bool)
                        or not isinstance(duration, int)
                        or not 5 <= duration <= 120
                    ):
                        return jsonify({
                            "error": "Slide duration must be between 5 and 120 seconds."
                        }), 400
                if "paused" in data:
                    if not isinstance(paused, bool):
                        return jsonify({"error": "Pause state must be true or false."}), 400
                if "music_enabled" in data:
                    if not isinstance(music_enabled, bool):
                        return jsonify({"error": "Music state must be true or false."}), 400
                    if music_enabled and not configured_music_url():
                        return jsonify({
                            "error": "Configure a valid licensed music file before enabling music."
                        }), 400
                if "command" in data and command not in ("next", "previous", "reload"):
                    return jsonify({"error": "Unsupported slideshow command."}), 400
                if "duration" in data:
                    set_setting(conn, "slide_duration", duration)
                if "paused" in data:
                    set_setting(conn, "slideshow_paused", "1" if paused else "0")
                if "music_enabled" in data:
                    set_setting(
                        conn, "music_enabled", "1" if music_enabled else "0"
                    )
                if command is not None:
                    set_setting(conn, "display_command", command)
                    set_setting(
                        conn,
                        "command_version",
                        str(int(get_setting(conn, "command_version", "0")) + 1),
                    )
                set_setting(
                    conn,
                    "control_version",
                    str(int(get_setting(conn, "control_version", "0")) + 1),
                )
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
        return render_template(
            "vote.html", mode=mode, event_title=app.config["EVENT_TITLE"]
        )

    @app.get("/display")
    def display():
        return render_template(
            "display.html", event_title=app.config["EVENT_TITLE"]
        )

    @app.get("/invite")
    def invite():
        base_url = (
            app.config["PUBLIC_BASE_URL"] or request.url_root.rstrip("/")
        )
        invite_url = f"{base_url}{url_for('invite')}?v={INVITE_VERSION}"
        short_invite_url = (
            f"{base_url}{url_for('invite_short')}?v={INVITE_VERSION}"
        )
        cover_url = (
            f"{base_url}{url_for('invite_cover')}?v={INVITE_VERSION}"
        )
        directions_url = (
            "https://www.google.com/maps/dir/?api=1&destination="
            + quote(app.config["EVENT_DIRECTIONS_QUERY"], safe="")
        )
        day = event_date.day
        ordinal = "th" if 11 <= day % 100 <= 13 else {
            1: "st", 2: "nd", 3: "rd"
        }.get(day % 10, "th")
        display_event_date = format_display_date(event_date)
        share_text = (
            "You're invited to celebrate Monica & Abhilash's Baby Shower "
            f"on {day}{ordinal} {event_date.strftime('%B')} at "
            f"{app.config['EVENT_VENUE']}.\n\n"
            f"Join us and bless our growing family!\n\n{short_invite_url}"
        )
        return render_template(
            "invite.html",
            event_title=app.config["EVENT_TITLE"],
            invite_url=invite_url,
            cover_url=cover_url,
            event_date_iso=event_date.isoformat(),
            display_event_date=display_event_date,
            event_time=app.config["EVENT_TIME"],
            event_venue=app.config["EVENT_VENUE"],
            share_title="Monica & Abhilash | Baby Shower Celebration",
            share_description=(
                "Join us to celebrate the arrival of our little one. Your love, "
                "blessings and presence will make this occasion special."
            ),
            directions_url=directions_url,
            whatsapp_url="https://wa.me/?text=" + quote(share_text, safe=""),
            directions_qr_url=url_for("invite_directions_qr"),
        )

    @app.get("/i")
    def invite_short():
        return redirect(url_for("invite", v=INVITE_VERSION), code=302)

    @app.get("/invite/directions-qr.png")
    def invite_directions_qr():
        directions_url = (
            "https://www.google.com/maps/dir/?api=1&destination="
            + quote(app.config["EVENT_DIRECTIONS_QUERY"], safe="")
        )
        image = qrcode.make(directions_url)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", max_age=3600)

    @app.get("/invite/cover.png")
    def invite_cover():
        preview = Image.new("RGB", (1200, 630), "#641b2d")
        draw = ImageDraw.Draw(preview)
        draw.rounded_rectangle(
            (12, 12, 1188, 618), radius=26, fill="#6d2034",
            outline="#d3b46e", width=4,
        )
        draw.rounded_rectangle(
            (448, 34, 1167, 596), radius=22, fill="#fff8e9",
            outline="#d3b46e", width=3,
        )

        photo_path = Path(app.static_folder) / "images" / "invite-couple.png"
        with Image.open(photo_path) as photo:
            photo = photo.convert("RGBA")
            photo.thumbnail((290, 480), Image.Resampling.LANCZOS)
            preview.paste(photo, (28, 72), photo)

        title_font_paths = (
            "C:/Windows/Fonts/georgiab.ttf",
            "C:/Windows/Fonts/georgia.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "DejaVuSerif.ttf",
        )
        italic_font_paths = (
            "C:/Windows/Fonts/georgiai.ttf",
            "C:/Windows/Fonts/georgia.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "DejaVuSerif.ttf",
        )
        def find_font(paths, size):
            font_path = next((path for path in paths if Path(path).is_file()), None)
            return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

        title_font = find_font(title_font_paths, 44)
        heading_font = find_font(title_font_paths, 38)
        message_font = find_font(title_font_paths, 24)
        detail_font = find_font(title_font_paths, 25)
        small_font = find_font(title_font_paths, 21)
        closing_font = find_font(italic_font_paths, 21)
        maroon = "#702b3b"
        leaf = "#64764d"
        text_x = 490
        text_width = 640

        def draw_wrapped(text, y, font, fill, spacing=7):
            lines = []
            line = ""
            for word in text.split():
                candidate = f"{line} {word}".strip()
                if line and draw.textlength(candidate, font=font) > text_width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            if line:
                lines.append(line)
            draw.multiline_text(
                (text_x, y), "\n".join(lines), font=font, fill=fill, spacing=spacing
            )
            line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
            return y + len(lines) * (line_height + spacing)

        draw.text((text_x, 54), "Monica & Abhilash", font=title_font, fill=maroon)
        draw.line((text_x, 112, 1128, 112), fill="#ad8542", width=2)
        draw.text((text_x, 128), "Baby Shower Celebration", font=heading_font, fill=maroon)
        y = draw_wrapped(
            "Cordially invite you to join us in love and laughter, and seek your blessings as our family joyfully grows to four.",
            184, message_font, leaf, spacing=5,
        )
        draw.line((text_x, y + 7, 1128, y + 7), fill="#dfd1b4", width=2)
        y = draw_wrapped(
            format_display_date(event_date), y + 20, small_font, maroon, spacing=4
        )
        y = draw_wrapped(app.config["EVENT_TIME"], y + 2, small_font, maroon, spacing=4)
        y = draw_wrapped(app.config["EVENT_VENUE"], y + 4, detail_font, maroon)
        y = draw_wrapped(
            "Opp. Sapthagiri College, Chikkasandra.", y + 1, small_font, leaf, spacing=4
        )
        qr_url = (
            "https://www.google.com/maps/dir/?api=1&destination="
            + quote(app.config["EVENT_DIRECTIONS_QUERY"], safe="")
        )
        qr_image = qrcode.make(qr_url).convert("RGB")
        qr_image.thumbnail((100, 100), Image.Resampling.NEAREST)
        preview.paste(qr_image, (28, 505))
        draw.text((text_x, 500), "Your love and blessings mean the world to us.",
                  font=closing_font, fill=maroon)
        draw.text((text_x, 528), "Looking forward to welcoming you —",
                  font=closing_font, fill=maroon)
        draw.text(
            (text_x, 556), "Shaarrvi Agamya",
            font=find_font(title_font_paths, 34), fill=maroon,
        )

        output = BytesIO()
        preview.save(output, format="PNG", optimize=True)
        output.seek(0)
        return send_file(
            output,
            mimetype="image/png",
            download_name="monicas-baby-shower-preview.png",
            max_age=3600,
        )

    @app.get("/invite/calendar.ics")
    def invite_calendar():
        end_date = event_date + timedelta(days=1)

        def escape_ical(value):
            text = str(value).replace("\r\n", "\n").replace("\r", "\n")
            return text.replace("\\", "\\\\").replace(";", "\\;").replace(
                ",", "\\,"
            ).replace("\n", "\\n")

        description = (
            f"Join us for a day filled with blessings, love and family. "
            f"{app.config['EVENT_DIRECTIONS_QUERY']}"
        )
        calendar_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Baby Shower//Invitation//EN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:monicas-baby-shower-{event_date.isoformat()}@babyshower.local",
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;VALUE=DATE:{event_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
            f"SUMMARY:{escape_ical(app.config['EVENT_TITLE'])}",
            f"LOCATION:{escape_ical(app.config['EVENT_VENUE'])}",
            f"DESCRIPTION:{escape_ical(description)}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]

        def fold_ical_line(line):
            remaining = line.encode("utf-8")
            folded = []
            limit = 75
            while len(remaining) > limit:
                cut = limit
                while cut > 0 and remaining[cut] & 0xC0 == 0x80:
                    cut -= 1
                folded.append(remaining[:cut].decode("utf-8"))
                remaining = remaining[cut:]
                limit = 74
            folded.append(remaining.decode("utf-8"))
            return "\r\n ".join(folded)

        calendar = "\r\n".join(
            [fold_ical_line(line) for line in calendar_lines] + [""]
        )
        return app.response_class(
            calendar,
            mimetype="text/calendar",
            headers={"Content-Disposition": 'attachment; filename="monicas-baby-shower.ics"'},
        )

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
                    event_title=app.config["EVENT_TITLE"],
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
            event_title=app.config["EVENT_TITLE"],
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
            set_setting(
                conn,
                "vote_sequence",
                str(int(get_setting(conn, "vote_sequence", "0")) + 1),
            )
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
        return jsonify({"photos": [slide["image"] for slide in slides_payload()]})

    @app.get("/api/slides")
    def api_slides():
        return jsonify({"slides": slides_payload()})

    @app.post("/api/display-state")
    def api_display_state():
        data = json_object()
        slide_id = data.get("slide_id")
        known_ids = {slide["id"] for slide in slides_payload()}
        if not isinstance(slide_id, str) or slide_id not in known_ids:
            return jsonify({"error": "Unknown slideshow slide."}), 400
        with connect_db() as conn:
            set_setting(conn, "current_slide_id", slide_id)
        return jsonify({"current_slide_id": slide_id})

    @app.get("/api/admin/slides")
    @admin_required
    def api_admin_slides():
        return jsonify({"slides": slides_payload()})

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
