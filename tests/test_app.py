import json
import re
import struct
from urllib.parse import unquote

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "ADMIN_PIN": "5831",
        "DATABASE_PATH": str(tmp_path / "votes.sqlite3"),
        "PUBLIC_BASE_URL": "https://baby.example",
        "EVENT_TITLE": "Monica's Baby Shower",
        "EVENT_DATE": "2026-11-22",
        "EVENT_VENUE": "Highland Hotel",
        "EVENT_DIRECTIONS_QUERY": "Highland Hotel, Opp. Sapthagiri College, Chikkasandra",
        "DISPLAY_MUSIC_FILE": "",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_token(client, path="/vote?mode=qr"):
    response = client.get(path)
    assert response.status_code == 200
    with client.session_transaction() as session:
        return session["csrf_token"]


def vote(client, csrf, choice, source="qr"):
    return client.post(
        "/api/vote",
        json={"choice": choice, "source": source},
        headers={"X-CSRF-Token": csrf},
    )


def admin_login(client, pin="5831"):
    csrf = csrf_token(client, "/admin")
    return client.post(
        "/admin",
        data={"pin": pin, "csrf_token": csrf},
        follow_redirects=True,
    )


def admin_post(client, csrf, data):
    return client.post(
        "/api/admin",
        json=data,
        headers={"X-CSRF-Token": csrf},
    )


def test_invalid_vote_is_rejected(client):
    csrf = csrf_token(client)
    response = vote(client, csrf, "unexpected")

    assert response.status_code == 400
    assert response.json["error"]
    assert client.get("/api/results").json["total"] == 0


def test_vote_requires_csrf_token(client):
    csrf_token(client)

    response = client.post("/api/vote", json={"choice": "girl", "source": "qr"})

    assert response.status_code == 400
    assert client.get("/api/results").json["total"] == 0


def test_closed_voting_rejects_vote(client):
    login = admin_login(client)
    assert login.status_code == 200
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    close_response = admin_post(client, csrf, {"action": "close"})
    assert close_response.status_code == 200

    response = vote(client, csrf, "girl")

    assert response.status_code == 403
    assert response.json["error"] == "Voting is closed. Thank you for joining!"
    assert client.get("/api/results").json["total"] == 0


def test_duplicate_qr_browser_token_is_rejected(client):
    csrf = csrf_token(client)
    first = vote(client, csrf, "girl", "qr")
    duplicate = vote(client, csrf, "boy", "qr")

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json["already_voted"] is True
    assert client.get("/api/results").json["total"] == 1


def test_booth_allows_repeat_guest_flow(client):
    csrf = csrf_token(client, "/vote?mode=booth")
    first = vote(client, csrf, "girl", "booth")
    second = vote(client, csrf, "boy", "booth")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json["total"] == 2
    assert second.json["girl"] == 1
    assert second.json["boy"] == 1
    assert second.json["booth"] == 2


def test_results_include_choice_and_source_counts(client):
    qr_client = client.application.test_client()
    booth_client = client.application.test_client()
    qr_csrf = csrf_token(qr_client)
    booth_csrf = csrf_token(booth_client, "/vote?mode=booth")

    assert vote(qr_client, qr_csrf, "girl", "qr").status_code == 201
    assert vote(booth_client, booth_csrf, "boy", "booth").status_code == 201
    assert vote(booth_client, booth_csrf, "girl", "booth").status_code == 201

    result = client.get("/api/results").json
    assert result["total"] == 3
    assert result["girl"] == 2
    assert result["boy"] == 1
    assert result["qr"] == 1
    assert result["booth"] == 2
    assert result["girl_percent"] == 67
    assert result["boy_percent"] == 33
    assert result["vote_sequence"] == 3


def test_admin_requires_login_and_valid_pin(client):
    csrf = csrf_token(client, "/admin")
    assert client.get("/api/admin").status_code == 401

    invalid = client.post("/admin", data={"pin": "wrong", "csrf_token": csrf})
    assert invalid.status_code == 200
    assert b"Incorrect PIN" in invalid.data

    login = admin_login(client)
    assert login.status_code == 200
    assert client.get("/api/admin").status_code == 200


def test_admin_pin_attempts_are_rate_limited(client):
    csrf = csrf_token(client, "/admin")
    for _ in range(5):
        response = client.post("/admin", data={"pin": "wrong", "csrf_token": csrf})
        assert response.status_code == 200

    limited = client.post("/admin", data={"pin": "wrong", "csrf_token": csrf})

    assert limited.status_code == 429
    assert b"Too many incorrect attempts" in limited.data


def test_admin_reset_requires_explicit_confirmation(client):
    csrf = csrf_token(client)
    assert vote(client, csrf, "girl", "booth").status_code == 201
    assert admin_login(client).status_code == 200
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    denied = admin_post(client, csrf, {"action": "reset", "confirm": False})
    assert denied.status_code == 400
    assert client.get("/api/results").json["total"] == 1

    reset = admin_post(client, csrf, {"action": "reset", "confirm": True})
    assert reset.status_code == 200
    assert reset.json["total"] == 0


def test_required_routes_are_available(client):
    assert client.get("/health").json == {"status": "ok"}
    assert client.get("/vote?mode=qr").status_code == 200
    assert client.get("/vote?mode=booth").status_code == 200
    assert client.get("/display").status_code == 200
    assert client.get("/invite").status_code == 200
    assert client.get("/qr.png").mimetype == "image/png"
    assert isinstance(client.get("/api/photos").json["photos"], list)
    assert isinstance(client.get("/api/slides").json["slides"], list)


def test_display_uses_prediction_language_percentages_and_kolam_frame(client):
    page = client.get("/display").data

    assert b"The Room Is Leaning..." in page
    assert b"What's Your Prediction?" not in page
    assert b'id="girlPercent"' in page
    assert b'id="boyPercent"' in page
    assert b'id="girlCount"' in page
    assert b'id="boyCount"' in page
    assert b'class="kolam-frame"' in page
    assert b'id="toggleMusicButton"' in page
    assert b"Enable Music</button>" not in page


def test_slideshow_manifest_has_loadable_motherhood_slides(client):
    slides = client.get("/api/slides").json["slides"]

    assert len(slides) == 8
    for slide in slides:
        assert slide["id"]
        assert slide["caption"]
        assert client.get(slide["image"]).status_code == 200


def test_bundled_indian_instrumental_mix_is_ready_by_default(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": str(tmp_path / "votes.sqlite3"),
    })
    client = app.test_client()

    results = client.get("/api/results").json

    assert results["music_enabled"] is True
    assert results["music_url"] == (
        "/static/music/alex-morgan-india-drums-tabla-sitar-ethnic-mood-587419.mp3"
    )
    assert client.get(results["music_url"]).mimetype == "audio/mpeg"


def test_voting_modes_show_clear_choices_without_install_or_privacy_copy(client):
    for mode in ("qr", "booth"):
        response = client.get(f"/vote?mode={mode}")

        assert response.status_code == 200
        assert response.data.count(b'class="choice ') == 2
        assert b"Baby Girl" in response.data
        assert b"Baby Boy" in response.data
        assert b"No app to install" not in response.data
        assert b"identity-verified one-vote-per-person" not in response.data


def test_invitation_has_configured_event_and_no_rsvp(client):
    response = client.get("/invite")

    assert response.status_code == 200
    assert b"Monica&#39;s Baby Shower" in response.data
    assert b"RSVP" not in response.data.upper()
    assert b"og:title" in response.data
    assert b"og:description" in response.data
    assert b"og:image" in response.data
    assert b'Monica &amp; Abhilash | Baby Shower Celebration' in response.data
    assert (
        b"Join us to celebrate the arrival of our little one. Your love, "
        b"blessings and presence will make this occasion special."
    ) in response.data
    assert b'og:image:width" content="1200"' in response.data
    assert b'og:image:height" content="630"' in response.data
    assert b"og:image:secure_url" in response.data
    assert b"twitter:card" in response.data
    assert b'name="twitter:card" content="summary_large_image"' in response.data
    assert b'<link rel="canonical" href="https://baby.example/invite?v=3">' in response.data
    assert b'property="og:url" content="https://baby.example/invite?v=3"' in response.data
    assert b'property="og:image" content="https://baby.example/invite/cover.png?v=3"' in response.data
    assert b"What is your prediction?" not in response.data
    assert b"Baby Girl" not in response.data
    assert b"Baby Boy" not in response.data
    assert b"/vote?mode=qr" not in response.data
    assert b"/static/images/invitation-reference.png" in response.data
    assert b"invite-kolam-frame" in response.data
    assert response.data.index(b'class="invite-image"') < response.data.index(
        b'class="invite-actions"'
    )
    assert b'href="/invite/calendar.ics"' in response.data
    assert b"Add to Calendar" in response.data
    assert b"Get Directions" in response.data
    assert b"Share on WhatsApp" in response.data
    assert b"google.com/maps/dir/" in response.data
    cover = client.get("/invite/cover.png")
    assert cover.mimetype == "image/png"
    assert cover.data.startswith(b"\x89PNG")
    assert struct.unpack(">II", cover.data[16:24]) == (1200, 630)
    image = client.get("/static/images/invitation-reference.png")
    assert image.mimetype == "image/png"
    assert image.data.startswith(b"\x89PNG")
    assert cover.data != image.data
    directions_qr = client.get("/invite/directions-qr.png")
    assert directions_qr.mimetype == "image/png"
    assert directions_qr.data.startswith(b"\x89PNG")


def test_invitation_only_shows_the_attached_artwork(client):
    response = client.get("/invite")
    assert response.data.count(b'class="invite-image"') == 1
    assert b"invite-couple-art" not in response.data
    assert b'class="invite-actions"' in response.data
    whatsapp = re.search(rb'href="(https://wa\.me/\?text=[^"]+)"', response.data)
    assert whatsapp is not None
    share_text = unquote(whatsapp.group(1).decode())
    assert "https://baby.example/invite?v=3" in share_text
    assert "Monica's Baby Shower" in share_text


def test_calendar_download_is_all_day_and_valid(client):
    response = client.get("/invite/calendar.ics")

    assert response.status_code == 200
    assert response.mimetype == "text/calendar"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "DTSTART;VALUE=DATE:20261122" in response.text
    assert "DTEND;VALUE=DATE:20261123" in response.text
    assert "SUMMARY:Monica's Baby Shower" in response.text
    assert "LOCATION:Highland Hotel" in response.text
    assert "DTSTART:" not in response.text
    assert all(len(line.encode("utf-8")) <= 75 for line in response.text.splitlines())


def test_slideshow_manifest_pairs_content_and_ignores_invalid_paths(app, client, tmp_path):
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / "approved.jpg").write_bytes(b"image")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([
        {
            "id": "approved",
            "image": "/static/photos/approved.jpg",
            "caption": "A tiny hand can hold an entire heart.",
            "category": "Love",
            "author": "Family",
        },
        {"id": "missing", "image": "/static/photos/missing.jpg", "caption": "Missing"},
        {"id": "unsafe", "image": "/static/photos/../app.py", "caption": "Unsafe"},
        {"id": "external", "image": "https://example.com/photo.jpg"},
    ]), encoding="utf-8")
    app.config["PHOTO_DIR"] = str(photo_dir)
    app.config["PHOTO_MANIFEST_PATH"] = str(manifest_path)

    slides = client.get("/api/slides").json["slides"]

    assert slides == [{
        "id": "approved",
        "image": "/static/photos/approved.jpg",
        "caption": "A tiny hand can hold an entire heart.",
        "category": "Love",
        "author": "Family",
    }]
    assert client.get("/api/photos").json["photos"] == ["/static/photos/approved.jpg"]


def test_big_screen_admin_controls_are_authenticated_and_validated(client):
    csrf = csrf_token(client, "/admin")
    assert client.get("/api/admin/slides").status_code == 401
    assert client.get("/api/admin").status_code == 401

    assert admin_login(client).status_code == 200
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    saved = admin_post(client, csrf, {"action": "slideshow", "duration": 30})
    assert saved.status_code == 200
    assert saved.json["slide_duration"] == 30

    paused = admin_post(client, csrf, {"action": "slideshow", "paused": True})
    assert paused.status_code == 200
    assert paused.json["slideshow_paused"] is True

    command = admin_post(client, csrf, {"action": "slideshow", "command": "next"})
    assert command.status_code == 200
    assert command.json["display_command"] == "next"
    assert command.json["command_version"] == 1

    invalid = admin_post(client, csrf, {"action": "slideshow", "duration": 500})
    assert invalid.status_code == 400
    assert client.get("/api/admin").json["slide_duration"] == 30

    unconfigured_music = admin_post(
        client, csrf, {"action": "slideshow", "music_enabled": True}
    )
    assert unconfigured_music.status_code == 400


def test_display_state_only_accepts_manifest_slide_ids(app, client, tmp_path):
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / "memory.webp").write_bytes(b"image")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([
        {"id": "memory-1", "image": "/static/photos/memory.webp", "caption": "Memory"}
    ]), encoding="utf-8")
    app.config["PHOTO_DIR"] = str(photo_dir)
    app.config["PHOTO_MANIFEST_PATH"] = str(manifest_path)
    csrf = csrf_token(client, "/display")

    rejected = client.post(
        "/api/display-state",
        json={"slide_id": "unexpected"},
        headers={"X-CSRF-Token": csrf},
    )
    assert rejected.status_code == 400

    accepted = client.post(
        "/api/display-state",
        json={"slide_id": "memory-1"},
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200
    assert client.get("/api/admin").status_code == 401
    assert client.get("/api/results").json["current_slide_id"] == "memory-1"


def test_invalid_music_path_does_not_break_public_display(app, client):
    app.config["DISPLAY_MUSIC_FILE"] = "../private.mp3"

    assert client.get("/display").status_code == 200
    assert client.get("/api/results").status_code == 200
    assert client.get("/api/results").json["music_url"] == ""


def test_vote_sequence_survives_vote_reset_and_only_counts_votes(client):
    csrf = csrf_token(client, "/vote?mode=booth")
    assert vote(client, csrf, "girl", "booth").status_code == 201
    assert client.get("/api/results").json["vote_sequence"] == 1

    assert admin_login(client).status_code == 200
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    reset = admin_post(client, csrf, {"action": "reset", "confirm": True})

    assert reset.status_code == 200
    assert reset.json["vote_sequence"] == 1
    assert reset.json["total"] == 0

    booth_csrf = csrf_token(client, "/vote?mode=booth")
    assert vote(client, booth_csrf, "boy", "booth").status_code == 201
    assert client.get("/api/results").json["vote_sequence"] == 2
