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
| `/invite`, `/i`, `/invite/calendar.ics`, `/invite/cover.png` | Interactive invitation, short redirect for sharing, calendar file, and 1200 x 630 social-preview image |
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

The invitation at `/invite` is responsive HTML/CSS and uses locally bundled Cormorant Garamond (SIL Open Font License) with serif fallbacks. It contains the revised wording, the supplied couple illustration, a generated directions QR, and a thick maroon frame with animated white Kolam knotwork and leafy corner sprays. The **Add to Calendar**, **Get Directions**, and **Share on WhatsApp** actions remain inside the framed invitation panel. The calendar retains `EVENT_DATE` (including its configured year); the date printed in the invitation omits the year.

The WhatsApp action shares a concise message and one same-origin short link, currently `/i?v=5`. `/i` redirects to `/invite?v=5`, the full interactive HTML invitation. The actual canonical metadata and 1200 x 630 Open Graph/Twitter preview remain on `/invite` and `/invite/cover.png`; the cover is generated from the revised invitation details and couple image. A URL cannot be hidden in a WhatsApp text message while also using it to create a rich link preview; the short route avoids repeating the long `/invite` path but WhatsApp may still display that single short link beneath its preview.

Set `PUBLIC_BASE_URL` to the deployed HTTPS origin so the metadata and the shared short link use the public host. The current PythonAnywhere URL shown in the invitation screenshot is `https://abhilash0393.pythonanywhere.com`. WhatsApp cannot fetch a rich image preview from localhost or a private-network URL. When the invitation artwork or metadata changes, increment `INVITE_VERSION` in `app.py`, deploy, and share the new `/i?v=...` link. To refresh a cached WhatsApp preview, fetch the canonical `/invite?v=...` URL and `/invite/cover.png?v=...` over HTTPS, then request a fresh scrape with Meta's Sharing Debugger before re-sharing the versioned short link.

Voting is not offered on the invitation page; guests can use the separate QR and booth voting pages.

## Motherhood slideshow

The display is preloaded with eight local motherhood images and original captions in `static/photos/manifest.json`; it starts cycling them automatically. Two public-domain or Creative Commons artworks include credits in `static/photos/README.txt`. To customize it, replace or add approved landscape images under `static/photos/` (for example `static/photos/motherhood/`). Supported formats are JPG/JPEG, PNG, GIF, WebP, and AVIF. Add each image and its matching caption to the manifest:

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

   `author` is optional.    The app validates paths and skips missing or unsafe entries. If no valid slides remain, it reports that rather than showing fabricated content.
On `/display`, the slideshow shuffles slides without immediately repeating one, preloads the next image, and rotates every 15 seconds by default. Each `static/photos/manifest.json` entry can specify a `textLayout` with position, alignment, desktop and mobile maximum width/insets, minimum/preferred/maximum font sizing, color, shadow, line height, padding, gradient, image focal point, and a percentage-based subject-safe area. Layout values are validated before being returned by `/api/slides`; the browser wraps text within the selected region, reduces its size if needed to fit the frame, and checks alternative positions against the visible subject-safe area after accounting for `object-fit: cover`. The three reference compositions are configured in `motherhood-tender-guidance` (top-right), `motherhood-golden-hour` (center-right), and `motherhood-lifted-high` (center-left). In automatic mode, new votes show the live results for 10 seconds; subsequent votes extend the results display. It then continues from the queued slide. On `/admin`, use **Big Screen Experience** to change mode or duration, pause/resume, navigate, preview the current slide, inspect the available list, and request a manifest reload.

Example per-image metadata:

```json
"textLayout": {
  "position": "top-right",
  "alignment": "right",
  "maxWidthPct": 35,
  "minFontPx": 18,
  "preferredFontVw": 3.2,
  "maxFontPx": 54,
  "color": "#342414",
  "shadow": "light",
  "lineHeight": 1.15,
  "overlay": "right-light",
  "objectPosition": "center center",
  "subjectArea": { "left": 18, "top": 14, "right": 64, "bottom": 92 }
}
```

Private photographs are excluded from Git by default. For deployment, copy them directly to the host and edit the manifest there, or use a private repository.

## Background music

The display uses the workspace's India drums, tabla, and sitar instrumental by default; its filename credits Alex Morgan. Its tuning is not documented, so no 455 Hz or 777 Hz claim is made. Music is allowed or disabled in `/admin`; browser autoplay restrictions may require one tap on the discreet music control revealed by hovering at the bottom of `/display`. You can replace it with an MP3, OGG, or WAV that you supplied or are licensed to use by setting `DISPLAY_MUSIC_FILE` in the private `.env`; leave it empty to disable music. Missing or invalid audio does not interrupt slides or results.

The display fills the browser tab with the slideshow or results, with kolam decoration limited to a narrow border. Use browser full-screen mode when sharing the display tab on a projector.

The prediction meter emphasizes the live percentage split while retaining individual and total vote counts. Before any votes are cast, it shows a clearly labeled even 50/50 starting split without recording placeholder votes.

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

5. Create `~/babyshower/.env` on the host (never commit it) and set a fresh `SECRET_KEY`, a unique `ADMIN_PIN`, `PUBLIC_BASE_URL=https://abhilash0393.pythonanywhere.com`, `COOKIE_SECURE=1`, and `DATABASE_PATH=instance/baby_votes.sqlite3`. The database then lives under the persistent project directory.
   Also set `EVENT_TITLE`, `EVENT_DATE=2026-11-22`, `EVENT_TIME`, `EVENT_VENUE`, and `EVENT_DIRECTIONS_QUERY` to the confirmed event details. Leave `DISPLAY_MUSIC_FILE` empty unless you upload licensed audio.
6. Reload the web app, verify `/health`, `/invite`, both vote modes, `/admin`, and `/display`. Download the QR image from `/qr.png` only after confirming the deployed HTTPS URL. The deployed database is created empty; local SQLite files are excluded from Git.
7. When ready to start collecting votes, use the admin controls to ensure voting is open. If you cast test votes during verification, reset them from `/admin` before sharing the QR code.

This free plan is intended for low-traffic, short-term use and has no production uptime guarantee. Keep a backup of the SQLite database if votes must be retained after the event. For longer-term hosting, use a paid service with persistent storage or migrate to a managed database.

For code updates after the first deployment, push your changes to GitHub, then in a PythonAnywhere Bash console run `cd ~/babyshower && git pull origin main`. If dependencies changed, activate `babyshower-venv` and run `pip install -r requirements.txt`; then click **Reload** in the PythonAnywhere **Web** tab. GitHub pushes do not automatically update the running PythonAnywhere app. Keep `.env`, the SQLite database, and private media on the host; do not overwrite or reset them during updates.

## Deploy environment variables

- `SECRET_KEY`: a long, unique random secret.
- `ADMIN_PIN`: a non-default event PIN.
- `PUBLIC_BASE_URL`: the deployed HTTPS origin, currently `https://abhilash0393.pythonanywhere.com`.
- `DATABASE_PATH`: a database path under the persistent home directory.
- `COOKIE_SECURE`: `1` when using HTTPS.
- `EVENT_TITLE`, `EVENT_DATE`, `EVENT_TIME`, `EVENT_VENUE`, `EVENT_DIRECTIONS_QUERY`: event, preview, calendar, directions, and QR settings.
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
- `static/fonts/` — self-hosted Cormorant Garamond font files and SIL Open Font License.
- `static/js/` — voting, slideshow/live meter, and admin controls.
- `static/photos/manifest.json` — paired slideshow photo-and-thought content.
- `static/images/` — reusable kolam ornaments; the invitation Open Graph cover is generated from configured event details.
- `static/photos/` and `static/music/` — optional user-provided event media.
- `tests/` — route and behavior tests.
- `AI_BUILD_PROMPT.md` — implementation brief.
- `wireframes/` — visual references.
