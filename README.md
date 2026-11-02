# Baby Shower Prediction & Family Slideshow

A Flask + SQLite application for QR and touchscreen booth predictions, a live projector display, and event administration. Both voting modes use the same server-side database. The app does not collect names, email addresses, or phone numbers.

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
- Projector display: <http://127.0.0.1:5000/display>
- Admin controls: <http://127.0.0.1:5000/admin>
- Health check: <http://127.0.0.1:5000/health>
- QR image: <http://127.0.0.1:5000/qr.png>

Run the unit and route tests with `python -m pytest`.

## Add event media

- Copy approved family photos into `static/photos/`. Supported formats are JPG/JPEG, PNG, GIF, WebP, and AVIF. The app automatically lists local image files; no manifest edit is needed. If there are no images, the display shows a useful placeholder.
- Optionally add a music file you have permission to play at `static/music/instrumental.mp3`. On `/display`, click **Start Display / Enable Music**. Music playback failure does not interrupt the slideshow or voting meter.
- Do not commit private family photos or licensed music into a public repository.

## Display and voting behavior

- `auto` mode starts with the slideshow and switches to the vertical two-column vote meter for 10 seconds after new votes arrive. Rapid votes are reflected together from the server's full counts.
- `slideshow`, `meter`, and `special` modes are controlled in `/admin`. The slideshow changes photos every six seconds; the background audio element is not recreated during view transitions.
- The display polls every 1.8 seconds. If the connection drops, the local slideshow continues and the display reports reconnecting.
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
6. Reload the web app, verify `/health`, both vote modes, `/admin`, and `/display`. Download the QR image from `/qr.png` only after confirming the deployed HTTPS URL. The deployed database is created empty; local SQLite files are excluded from Git.
7. When ready to start collecting votes, use the admin controls to ensure voting is open. If you cast test votes during verification, reset them from `/admin` before sharing the QR code.

This free plan is intended for low-traffic, short-term use and has no production uptime guarantee. Keep a backup of the SQLite database if votes must be retained after the event. For longer-term hosting, use a paid service with persistent storage or migrate to a managed database.

## Deploy environment variables

- `SECRET_KEY`: a long, unique random secret.
- `ADMIN_PIN`: a non-default event PIN.
- `PUBLIC_BASE_URL`: the deployed HTTPS origin, e.g. `https://<username>.pythonanywhere.com`.
- `DATABASE_PATH`: a database path under the persistent home directory.
- `COOKIE_SECURE`: `1` when using HTTPS.

`PUBLIC_BASE_URL` must use HTTPS, and the app refuses to start with a configured public URL unless `SECRET_KEY`, `ADMIN_PIN`, and `COOKIE_SECURE=1` are set.

## Security notes

- Admin mutations and vote submissions require a session CSRF token. Admin PIN attempts are rate-limited per client address. The PIN and Flask secret are read from environment variables and are never sent to client-side JavaScript.
- The default PIN `2468` is only a local-development fallback. Never deploy without setting a unique `ADMIN_PIN` and `SECRET_KEY`.
- Sessions use HTTP-only, SameSite=Lax cookies. Set `COOKIE_SECURE=1` on HTTPS deployments.
- The QR voting repeat check is an event convenience, not an identity check or security guarantee.

## Project structure

- `app.py` — Flask routes, security controls, and SQLite data access.
- `templates/` — QR/booth voting, display, and admin pages.
- `static/css/app.css` — dark responsive styling and custom illustrated baby icons.
- `static/js/` — voting flow, photo display/live meter, and admin controls.
- `static/photos/` and `static/music/` — optional user-provided event media.
- `tests/` — route and behavior tests.
- `AI_BUILD_PROMPT.md` — implementation brief.
- `wireframes/` — visual references.
