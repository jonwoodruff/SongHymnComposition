# Song & Hymn

A first local implementation of a public, collaborative song and hymn writing website. Built with Python 3.12+ and Django 6.0; SQLite is used for local development. Pages are generated on the server, with JavaScript for melody editing and playback.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ and http://127.0.0.1:8000/admin/.

Request membership at `/join/` using a separate account to try contributing. Sign into the administration interface with your superuser and open **Memberships** to read the application and set its role. Save the change. Applicants cannot grant themselves access. Their testimony, email, and experience are not shown on public pages. Administrator accounts do not automatically have composition privileges; approve a membership for an account to give it a writing role.

No sample users, passwords, or compositions are created automatically. The database and virtual environment are excluded from Git. The repository does not need GitHub credentials to run.

## Implemented workflow

- Visitors can browse songs, drafts, lyrics, melodies, and discussions.
- Membership applications ask about composing, commenting, reviewing, testimony, and experience. An administrator grants commenter, contributor, or experienced reviewer access.
- Contributors and experienced reviewers can start songs. Approved members can comment and suggest changes.
- Concept, lyrics, and tune develop in parallel. Only the author or an experienced reviewer can edit a draft.
- Each section needs two distinct experienced approvals. The author must also sign off before freezing. An experienced author can count toward a section's two approvals.
- Frozen compositions can be edited only by experienced reviewers. Every content change invalidates publication approvals by advancing the song revision.
- Publication needs five distinct experienced reviewers **excluding the song's author**. Published compositions are read-only; a post-publication revision process is not yet implemented.
- During frozen review, the author can request rework; two distinct experienced reviewers must approve returning it to development. Returning clears approvals and author sign-off.
- A change to one draft section requires fresh approvals for that section, retains the other sections' approvals, and clears author sign-off.
- Approval counts ignore inactive or demoted reviewers. All approval and permission checks run on the server. Administrator workflow records are read-only so the administration UI cannot skip the gates.
- Opening an editor automatically acquires a 15-minute lock without leaving the page. Another person can comment while it is locked. Renewal is manual. Saving also works without a separate lock step when no other editor holds an active lock. Stale submissions and conflicting locks are rejected with the submitted text kept in the open editor; stale section revisions must be compared with the latest version before retrying.
- Text selection can populate a comment's quoted phrase. Clicking notation can populate a tune character reference. Comments retain the discussed section revision; they do not follow later edits. Revision snapshots are retained in the database and are visible to administrators.

## Melody prototype

The initial editor supports adding natural notes and rests with eighth, quarter, half, and whole-note durations, plus bar lines and undo, with C-major notation rendered by locally vendored **abcjs 6.7.1**. Preview uses the browser's Web Audio API with a synthesized tone, without fetching soundfonts. Clicking a displayed note populates the comment reference.

This is a melody sketchpad, not yet a full sheet-music editor. ABC source can be edited directly, but the simple audio preview only supports natural pitches, octave markers, rests, and durations. Other keys, accidentals, ties, repeats, meter validation, changing/deleting individual notes graphically, lyric alignment, MusicXML import/export, and print/PDF export remain to be implemented. Advanced ABC may render correctly without playing correctly. The source editor and note buttons make this limitation explicit.

abcjs project: https://github.com/paulrosen/abcjs. Its MIT license is included alongside the vendored file. Typography optionally loads Google Fonts; system fonts are used when offline.

## Verify

```sh
python manage.py check
python manage.py test
node --check songs/static/songs/melody.js
```

Tests exercise approvals, independence from the author, role restrictions, lock expiry, stale revisions, frozen edits, return-to-development voting, private application details, pending accounts, registration, CSRF enforcement, and public page rendering. Browser layout, notation interaction, and audio still require manual browser testing.

## Before public hosting

This is a local foundation, not a deployed service. Hosting configuration, HTTPS, email verification and password-reset delivery, login/application throttling, database backups, and production asset serving remain to be configured. Set `DEBUG=0`, a private `SECRET_KEY`, and explicit `ALLOWED_HOSTS` for deployment. Use PostgreSQL before supporting concurrent writers in production: workflow transactions use row locking, which SQLite does not implement. Configure secure session/CSRF cookies with HTTPS at deployment.

Other follow-up work includes a richer score editor, revision comparisons and annotation navigation, resolving critical review issues, membership notification emails, search, published song print layouts, the public “we sang this” count, and an agreed policy for credit and publication licensing. No license for the project's own code or compositions has been assumed.
