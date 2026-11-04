# Baby Shower Prediction & Family Slideshow

A Flask + SQLite application for QR and touchscreen booth predictions, a live projector display, a kolam-themed invitation, and event administration. Both voting modes use the same server-side database. The app does not collect names, email addresses, or phone numbers.

## Run locally

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace `SECRET_KEY` and `ADMIN_PIN` with private values. For local use, leave `PUBLIC_BASE_URL` empty and keep `COOKIE_SECURE=0`. The app loads `.env` automatically.

```powershell
python app.py
```

Open:

- QR voting: <http://127.0.0.1:5000/vote?mode=qr>
- Touchscreen booth: <http://127.0.0.1:5000/vote?mode=booth>
- Digital invitation: <http://127.0.0.1:5000/invite>
- Projector display: <http://127.0.0.1:5000/display>
- Admin controls: <http://127.0.0.1:5000/admin>
- Calendar file: <http://127.0.0.1:5000/invite/calendar.ics>
- Health check: <http://127.0.0.1:5000/health>
- QR image: <http://127.0.0.1:5000/qr.png>

Run the unit and route tests with `python -m pytest`.

### Routes and APIs

| Route | Purpose |
|---|---|
| `/` | Redirects to QR voting |
| `/invite`, `/invite/calendar.ics`, `/invite/cover.png` | Invitation, all-day calendar file, and social-preview artwork |
| `/vote?mode=qr`, `/vote?mode=booth` | QR and touchscreen voting |
| `/display` | Live results and motherhood slideshow |
| `/admin` | Authenticated event and display controls |
| `/qr.png`, `/health` | QR image and health check |
| `GET /api/results`, `GET /api/slides`, `GET /api/photos` | Public results and validated slideshow content (`/api/photos` remains for compatibility) |
| `POST /api/vote` | CSRF-protected vote submission |
| `POST /api/display-state` | CSRF-protected current-slide reporting for the admin preview |
| `GET/POST /api/admin`, `GET /api/admin/slides` | Authenticated admin status, controls, and photo list |
| `POST /api/voting-control`, `POST /api/display-settings` | Authenticated control routes retained for compatibility |

## Event configuration

The invitation details are configurable through `.env`. The provided defaults are Monica's Baby Shower, 22 November 2026, at Hotel Highland. `EVENT_DATE` must use `YYYY-MM-DD`; the calendar download is an all-day event because no time was supplied. Do not add a time unless the family confirms one. `EVENT_DIRECTIONS_QUERY` defaults to Hotel Highland; set it to the confirmed full venue address if needed. No RSVP feature is provided.

The invitation at `/invite` includes an Add to Calendar download, Google Maps directions, WhatsApp sharing, and a configurable Open Graph cover image at `/invite/cover.png`. Voting is not offered on the invitation page; guests can use the separate QR and booth voting pages.

## Add motherhood photos and thoughts

1. Add approved landscape images under `static/photos/` (for example `static/photos/motherhood/`). Supported formats are JPG/JPEG, PNG, GIF, WebP, and AVIF.
2. Add each image and its matching caption to `static/photos/manifest.json`:

   ```json
   [
     {
       "id": "motherhood-001",
       "image": "/static/photos/motherhood/photo1.jpg",
       "caption": "A tiny hand can hold an entire heart.",
       "category": "Love"
     }
   ]
   ```

   `author` is optional. The image file is only an example path; add a real, locally stored image before using it. The app validates paths and skips missing or unsafe entries. With no valid slides it shows a placeholder instead of fake content.
3. On `/display`, the slideshow shuffles slides without immediately repeating one, preloads the next image, and rotates every 15 seconds by default. In automatic mode, new votes show the live results for 10 seconds; subsequent votes extend the results display. It then continues from the queued slide.
4. On `/admin`, use **Big Screen Experience** to change mode or duration, pause/resume, navigate, preview the current slide, inspect the available list, and request a manifest reload.

Private photographs are excluded from Git by default. For deployment, copy them directly to the host and edit the manifest there, or use a private repository.

## Optional background music

Only configure audio you supplied or are licensed to play. Copy an MP3, OGG, or WAV into `static/music/`, then set `DISPLAY_MUSIC_FILE` in the private `.env` to the filename (for example `instrumental.mp3`). Audio is disabled by default. Enable it from the admin controls, then tap **Enable Music** on the display because browsers may block autoplay. Missing or invalid audio does not interrupt slides or results. Music files are excluded from Git.

## Display and voting behavior

- `auto` mode starts with the slideshow and switches to the prediction meter for 10 seconds after new votes arrive. Further votes update the counts and extend the results window.
- `slideshow`, `meter`, and `special` modes are controlled in `/admin`. The display polls the existing results API every five seconds to limit server load.
- Display settings and slide-navigation commands are stored in the existing SQLite `settings` table; vote records and voting APIs are unchanged.
- QR voting discourages a second submission in the same browser session. This is a casual prediction game, not identity-verified one-person-one-vote security. Booth guests can submit repeatedly using the next-guest button.
- A vote is only confirmed after the server reports it saved. A closed poll rejects submissions server-side.
- After a selection is submitted, the chosen baby animates before the confirmation page appears in both QR and booth modes. The animation respects reduced-motion preferences.

## Short-term free hosting

For a small event, PythonAnywhere's free Beginner account can host this Flask app at `https://<username>.pythonanywhere.com`. Its home-directory files persist, so the existing SQLite database can be used without a database migration. Free accounts have limited resources and restricted outbound internet; the voting app does not need outbound requests during normal use.

1. Push the project to a GitHub repository. The repository can be public or private, but do not commit `.env`, SQLite database files, or private/licensed media. These files are excluded by `.gitignore`.
2. Create a PythonAnywhere Beginner account and add a **Manual Configuration** web app using Python 3.12.
3. In a PythonAnywhere Bash console, clone the repository, create/activate a virtual environment, and install the requirements:

   ```bash
   git clone https://github.com/<owner>/<repository>.git ~/babyshower
   mkvirtualenv --python=/usr/bin/python3.12 babyshower-venv
   workon babyshower-venv
   pip install -r ~/babyshower/requirements.txt
   ```

4. In the web app's **Virtualenv** field, enter `~/.virtualenvs/babyshower-venv`. Edit its WSGI file so it imports the project:

   ```python
   import sys
   path = "/home/<username>/babyshower"
   if path not in sys.path:
       sys.path.insert(0, path)
   from app import app as application
   ```

5. Create `~/babyshower/.env` on the host (never commit it) and set a fresh `SECRET_KEY`, a unique `ADMIN_PIN`, `PUBLIC_BASE_URL=https://<username>.pythonanywhere.com`, `COOKIE_SECURE=1`, and `DATABASE_PATH=instance/baby_votes.sqlite3`. The database then lives under the persistent project directory.
   Also set `EVENT_TITLE`, `EVENT_DATE=2026-11-22`, `EVENT_VENUE=Hotel Highland`, and `EVENT_DIRECTIONS_QUERY` to the confirmed event details. Leave `DISPLAY_MUSIC_FILE` empty unless you upload licensed audio.
6. Reload the web app, verify `/health`, `/invite`, both vote modes, `/admin`, and `/display`. Download the QR image from `/qr.png` only after confirming the deployed HTTPS URL. The deployed database is created empty; local SQLite files are excluded from Git.
7. When ready to start collecting votes, use the admin controls to ensure voting is open. If you cast test votes during verification, reset them from `/admin` before sharing the QR code.

This free plan is intended for low-traffic, short-term use and has no production uptime guarantee. Keep a backup of the SQLite database if votes must be retained after the event. For longer-term hosting, use a paid service with persistent storage or migrate to a managed database.

For code updates after the first deployment, push your changes to GitHub, then in a PythonAnywhere Bash console run `cd ~/babyshower && git pull origin main`. If dependencies changed, activate `babyshower-venv` and run `pip install -r requirements.txt`; then click **Reload** in the PythonAnywhere **Web** tab. GitHub pushes do not automatically update the running PythonAnywhere app. Keep `.env`, the SQLite database, and private media on the host; do not overwrite or reset them during updates.

## Deploy environment variables

- `SECRET_KEY`: a long, unique random secret.
- `ADMIN_PIN`: a non-default event PIN.
- `PUBLIC_BASE_URL`: the deployed HTTPS origin, e.g. `https://<username>.pythonanywhere.com`.
- `DATABASE_PATH`: a database path under the persistent home directory.
- `COOKIE_SECURE`: `1` when using HTTPS.
- `EVENT_TITLE`, `EVENT_DATE`, `EVENT_VENUE`, `EVENT_DIRECTIONS_QUERY`: invitation settings.
- `DISPLAY_MUSIC_FILE`: optional filename under `static/music/`; leave empty by default.

`PUBLIC_BASE_URL` must use HTTPS, and the app refuses to start with a configured public URL unless `SECRET_KEY`, `ADMIN_PIN`, and `COOKIE_SECURE=1` are set.

## Security notes

- Admin mutations and vote submissions require a session CSRF token. Admin PIN attempts are rate-limited per client address. The PIN and Flask secret are read from environment variables and are never sent to client-side JavaScript.
- The default PIN `2468` is only a local-development fallback. Never deploy without setting a unique `ADMIN_PIN` and `SECRET_KEY`.
- Sessions use HTTP-only, SameSite=Lax cookies. Set `COOKIE_SECURE=1` on HTTPS deployments.
- The QR voting repeat check is an event convenience, not an identity check or security guarantee.

## Project structure

- `app.py` — Flask routes, security controls, and SQLite data access.
- `templates/` — QR/booth voting, display, and admin pages.
- `static/css/app.css` — shared responsive kolam design system.
- `static/js/` — voting, slideshow/live meter, and admin controls.
- `static/photos/manifest.json` — paired slideshow photo-and-thought content.
- `static/images/` — reusable kolam ornaments; the invitation Open Graph cover is generated from configured event details.
- `static/photos/` and `static/music/` — optional user-provided event media.
- `tests/` — route and behavior tests.
- `AI_BUILD_PROMPT.md` — implementation brief.
- `wireframes/` — visual references.
