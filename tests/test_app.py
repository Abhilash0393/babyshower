import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "ADMIN_PIN": "5831",
        "DATABASE_PATH": str(tmp_path / "votes.sqlite3"),
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
    assert client.get("/qr.png").mimetype == "image/png"
    assert isinstance(client.get("/api/photos").json["photos"], list)
