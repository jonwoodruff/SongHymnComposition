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
- Text and melody changes autosave about one second after a pause. A small status shows unsaved/saving/saved state; Save now remains available. A three-second poll displays saved edits and comments in other browsers. This is not character-level simultaneous editing: one person writes each section at a time, while different sections can be edited independently. A quiet 30-second reservation is renewed every ten seconds while an editor is open and released when a clean editor closes. A disconnected editor times out. Stale section revisions cannot overwrite newer text; conflicts show both versions for comparison. Navigation warns about unsaved text. Review approvals remain tied to the version originally viewed; refresh is required after edits.
- Comments appear in a collapsible sidebar on desktop and below the composition on small screens. Selecting text offers a floating Comment on selection action; right-clicking a selection offers the same action. It quotes the phrase, opens the composer, and focuses the comment box without clearing an existing comment draft. Escape dismisses the action. Shift-right-click keeps the browser menu. Unique exact quotations are highlighted on the discussed revision; clicking them opens the corresponding comment. Repeated or overlapping quotations are kept in the sidebar rather than guessing an attachment. Clicking notation populates a tune character reference. Comments retain the discussed revision and do not follow later edits. Revision snapshots are retained in the database and visible to administrators.

## Contributor agreement and content licensing

New applications require separate fellowship and licensing checkboxes. The fellowship text is explicitly provisional and lives in `songs/policy.py`. Agreement version and timestamp are recorded, with these fields read-only in the administration interface. Existing members are asked to accept before making new contributions; old content is not automatically relicensed. Authors can explicitly confirm the sharing licence for their existing sections using the section’s sharing control. New saved composition revisions and public comments record CC BY 4.0. Publication records CC BY-ND 4.0 for the approved edition, but cannot remove CC BY rights already granted. All sections need recorded licensing metadata before publication. Private applications and website software are outside this content policy. See `/licensing/` for the public explanation and links to Creative Commons. If the agreement text changes materially, change its version so contributors must accept the new text.

## Uploaded recordings

The tune section has an **Add or replace a tune recording** control. A recording appears alongside the synthesized preview with play/pause, volume, seeking, and a download link. It can also be used as the tune when notation has not been entered. Uploading, replacing, or removing a tune recording follows the existing author/reviewer editing rules and advances the tune and song revisions, clearing author sign-off and requiring fresh tune or publication approvals. Earlier recordings remain stored with their revision snapshots. Editing notation retains the attached recording.

Approved members can attach one recording to a comment, with or without text. These recordings appear in the sidebar and can be heard by public visitors. New live comments preserve existing player elements, so they do not interrupt playback. Starting another recording or the synthesized preview pauses the previous player.

Supported files: **MP3, M4A, WAV, OGG (Vorbis/Opus), and FLAC**, up to **25 MB per file**. Mutagen checks audio metadata and format; the original file is retained rather than transcoded. Playback depends on the browser's support for the file's codec; a download link is always available. File controls only upload on explicit submission, not on text autosave. A failed upload keeps the selected file and accompanying text for correction.

Recordings are public composition/comment contributions under the existing agreement; uploaders must have permission to share them, including any performances by others. Licence badges remain on Lyrics and Tune, not comments.

Files are stored in `media/` (or the `MEDIA_ROOT` environment setting), excluded from Git along with the database. Audio is served through `/recordings/<uuid>/` with a validated audio content type, generated filenames, and byte-range support. Back up the media directory **and** database together. On a hosted installation, configure persistent media storage and an upstream request-size limit to match the 25 MB application limit. Files are retained for revision history; there is not yet a storage-quota or archival-purge interface.

## Melody prototype

The initial editor supports adding natural notes and rests with eighth, quarter, half, and whole-note durations, plus bar lines and undo, with C-major notation rendered by locally vendored **abcjs 6.7.1**. Preview uses the browser's Web Audio API with a synthesized tone, without fetching soundfonts. Clicking a displayed note populates the comment reference.

This is a melody sketchpad, not yet a full sheet-music editor. ABC source can be edited directly, but the simple audio preview only supports natural pitches, octave markers, rests, and durations. Other keys, accidentals, ties, repeats, meter validation, changing/deleting individual notes graphically, lyric alignment, MusicXML import/export, and print/PDF export remain to be implemented. Advanced ABC may render correctly without playing correctly. The source editor and note buttons make this limitation explicit.

A researched integration path for a full visual editor is in [docs/music-editor.md](docs/music-editor.md). The Smoosic integration has not been implemented.

abcjs project: https://github.com/paulrosen/abcjs. Its MIT license is included alongside the vendored file. Typography optionally loads Google Fonts; system fonts are used when offline.

## Verify

```sh
python manage.py check
python manage.py test
node --check songs/static/songs/melody.js
node --check songs/static/songs/editing.js
```

Optional two-browser Chrome smoke test, using a temporary database that is deleted afterwards:

```sh
npm install --prefix /tmp/songhymn-browser-check --cache /tmp/songhymn-npm-cache playwright
NODE_PATH=/tmp/songhymn-browser-check/node_modules .venv/bin/python scripts/browser_smoke.py
```

This uses Chrome on macOS by default; set `CHROME_PATH` to your Chrome executable elsewhere. It checks autosave, live viewing, editing presence, independent sections, handoff, live comments, quotation markers, melody autosave, mobile overflow, and browser JavaScript errors.

Tests exercise approvals, independence from the author, role restrictions, lock expiry, stale revisions, frozen edits, return-to-development voting, private application details, pending accounts, registration, CSRF enforcement, and public page rendering. The autosave and comments interface is also checked in two isolated headless Chrome sessions. Audio quality and the musical correctness of scores still require listening and manual testing.

## Before public hosting

This is a local foundation, not a deployed service. Hosting configuration, HTTPS, email verification and password-reset delivery, login/application throttling, database backups, and production asset serving remain to be configured. Set `DEBUG=0`, a private `SECRET_KEY`, and explicit `ALLOWED_HOSTS` for deployment. Use PostgreSQL before supporting concurrent writers in production: workflow transactions use row locking, which SQLite does not implement. Configure secure session/CSRF cookies with HTTPS at deployment.

Other follow-up work includes a richer score editor, revision comparisons and annotation navigation, resolving critical review issues, membership notification emails, search, published song print layouts, the public “we sang this” count, and richer contributor attribution. The content licensing policy does not assign a software licence to the project code.
