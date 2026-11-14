# Master prompt for VS Code AI assistant

Act as a senior full-stack engineer. Read README.md and inspect every file in this repository before changing anything. Implement the complete app in this repo, not just a plan or a static mockup. Keep the dark premium design and the custom illustrated baby icons.

## Event purpose
Build one web application for a baby shower. Guests vote from their own phones using a QR code or from a touchscreen laptop at the polling booth. A separate TV/projector page shows family photos with instrumental background music, and briefly switches to an animated live prediction meter when votes arrive. Admin controls the event.

## Routes and pages
- `/vote?mode=qr`: phone-friendly voting. After a successful vote, show “You chose Baby Girl/Baby Boy”, “Thank you”, and Done.
- `/vote?mode=booth`: large touchscreen buttons. After voting, show the selected choice and “Cast My Vote Again” to prepare for the next guest.
- `/display`: full-screen display with slideshow, vertical vote columns, and special-message mode.
- `/admin`: PIN-protected controls, totals split by Girl/Boy and QR/Booth, open/close voting, display mode, special message, QR code, and reset test data with explicit confirmation.
- `/qr.png`: QR code to the deployed public `/vote?mode=qr` URL.
- `/api/vote`, `/api/results`, `/api/admin`, `/health`.

## Architecture
Use Flask + SQLite for local development. Server is the source of truth for all vote totals. Use parameterized SQL, validate choices on the server, store timestamp/source/browser token, and do not collect names, email, or phone numbers. QR and booth clients must update the same database. Use polling every 1–2 seconds or reliable Server-Sent Events. The big screen must refresh automatically after votes from either source.

## Live display behaviour
- Premium dark navy background with restrained violet/blue glow and high-contrast text.
- Default `auto` mode: slideshow plays by default; after one or more new votes, briefly show the meter for 8–12 seconds and then return to the slideshow.
- `slideshow` mode: photos only; `meter` mode: columns remain on screen; `special` mode: admin-controlled special message.
- Prediction meter must use two **vertical columns**, not horizontal bars. Show count, percentage, and total votes. New vote should animate count and pulse/rise the relevant column. Batch rapid vote updates into one transition while preserving all vote counts.
- Photos rotate every 5–7 seconds with crossfade/slow zoom. Load local images from `static/photos/`; don't depend on an external image service. Create an easy photo manifest or automatic safe directory listing. If no photos are found, show a useful placeholder.
- Keep instrumental music playing continuously across slideshow/meter transitions. Use only music the user has permission to play. Add a deliberate “Start display / Enable music” action because browsers may block autoplay. If audio fails, the slideshow still works.
- When the server connection drops, keep local slideshow playing and show reconnecting status. Resume live data when reconnected.
- Support 16:9 displays, laptop screens, mobile screens, keyboard focus, accessible labels, and reduced-motion preferences.

## Voting UX and integrity
- QR voting should discourage repeat submissions from the same browser/session token, but clearly state this is a casual prediction game, not identity-verified one-person-one-vote. Do not promise that each person can only vote once.
- Booth voting should allow repeated next-guest flow. If voting is closed, reject the vote on the server and show a clear friendly message.
- Show success only after the server confirms the vote was saved. Handle network errors without silently losing a vote.
- Never use hard-coded fake vote totals in production. Test votes must be reset before event start.

## Admin and security
- Read admin PIN and Flask secret from environment variables; include `.env.example`; never commit real secrets.
- Protect all admin mutations server-side, use CSRF protection or an equivalent safe approach, rate-limit PIN attempts if practical, and never expose secrets in browser JavaScript.
- Reset requires an explicit confirmation phrase. Add a warning before deleting votes.
- Make `PUBLIC_BASE_URL` and `DATABASE_PATH` configurable. Production hosting must have HTTPS and persistent database storage. Do not use an ephemeral filesystem for the live database.

## Delivery requirements
1. Improve the starter source and complete any missing behaviour.
2. Add unit tests for invalid vote, closed voting, duplicate QR browser token, booth repeat flow, counts/source split, and admin authentication.
3. Add deployment instructions for a simple HTTPS host with persistent storage, and local development instructions.
4. Run syntax checks/tests; fix errors.
5. Explain changed files and provide a concise run guide.
6. Do not stop after outlining a plan. Implement the features and verify the routes.
