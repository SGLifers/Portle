# Portle handoff — 2026-11-03

## Outcome and user intent

The user requested a separate Wordle-style Discord game: identify a Splitgate arena
from portal placements, with more portals revealed after each wrong guess. The
implementation is complete locally, with a playable browser preview and an offline
validated Discord bot. **Discord is not connected**: no bot token was supplied,
requested in chat or searched for. Activation requires the user's application,
server installation and a token entered locally. See DISCORD_SETUP.md.

An optional preference question offered daily per-player, shared channel, or both.
No answer arrived during development. The implemented default is a shared daily
map with private per-player progress, plus unlimited practice. Do not silently
change this to a shared competitive channel round.

## Repository and boundaries

- Repo: `/home/lambchopper67/Documents/ChatGPT/Splitgate/Portle`
- Branch: `codex/portle`; independent Git repository, no remote configured.
- Initial milestones: `14734a6` core rules, `bfb98d6` Discord and local playtest.
  Use `git log` for the final verification/documentation commit.
- Atlas: `/home/lambchopper67/Documents/ChatGPT/Splitgate/PortalAtlas`, read-only.
  Its configurable cutaway work is already separate and committed (`3ba60e6`).
- Do not modify/start/stop SplitgateHost, extraction workers, the game installation
  or the Atlas server. Do not launch the game. At most four CPUs for this work.
- Keep extracted assets, coordinates, SQLite progress, IDs, credentials, generated
  images and `.venv` out of Git. No publication or hosting registration was done.

## Running local services

Portle browser preview is left running at **http://127.0.0.1:8742**, loopback only.
At handoff its PID is **1195964**. `.local/preview.pid` records the current PID;
`.local/preview.log` is its log. It runs this checkout's `.venv/bin/python -m portle
preview --port 8742` as a detached subprocess. Verify `/proc/<pid>/cwd` and command
line before stopping a process, as PIDs can be reused. Restart only Portle if code
changes; it does not have hot reload. Preview progress persists separately in
`.local/preview.sqlite3`.

The existing Atlas continues at http://127.0.0.1:8741; it was not restarted. Its Git
checkout was clean at verification. The preview browser tab is a deliverable and
is left on practice clue 5, showing 16 portals. Opening/reloading the page starts
or resumes the daily. The preview cookie's daily is still playing at clue 2 after
one QA skip. A completed practice loss is also saved but does not affect stats.

Screenshot: `.local/portle-preview.png` (full desktop page, practice, no answer).
Screenshot and all preview state are intentionally untracked.

## Setup and operation

```bash
cd /home/lambchopper67/Documents/ChatGPT/Splitgate/Portle
./setup.sh
.venv/bin/python -m portle doctor
.venv/bin/python -m portle preview --port 8742
```

The existing isolated `.venv` uses Python 3.12.14 and contains the pinned direct
dependencies `discord.py==2.7.1`, `Pillow==13.0.0`, `python-dotenv==1.2.4`.
`setup.sh` accepts `--source` for an alternate Atlas scene directory. First setup
can use `PORTLE_PYTHON=/path/to/python3`. It never changes the source exports.

For Discord, edit a private local `.env` based on `.env.example`, then `./run.sh`.
Use one bot process per database. Guild-only slash commands need `bot` and
`applications.commands` scopes. Channel permissions: View Channels, Send Messages,
Embed Links, Attach Files. No privileged intents, Administrator permission,
message-content reading or public HTTP endpoint are needed. Keep the Discord
Interactions Endpoint URL empty; this bot uses Gateway interactions.

Default daily timezone: `UTC`; configure `PORTLE_TIMEZONE` before production play.
Optional `DISCORD_GUILD_ID` syncs commands to one development server; otherwise
commands sync globally. `PORTLE_CATALOG` and `PORTLE_DATABASE` override production
paths. Shell environment variables take precedence over `.env`.

Production files default to `data/catalog.json` and `data/portle.sqlite3`. SQLite
stores the installation seed, daily snapshots, player IDs, guesses, event IDs and
guild participation. Retain it to preserve schedules/stats. Use SQLite backup or
stop/checkpoint before copying; never casually copy a live WAL database.

## Data and rules

Real source: `../PortalAtlas/data/scenes/MAP_*.json`. Imported **23 maps with 3,366
enabled portal placements**. Of the 25 arena/training exports, Training (50 walls)
and HangmanR3 (16 shared zone walls) are excluded. Shared Ozone/Graffiti libraries
and creative/biome/simulation assets are also excluded. Coordinates, normals,
right/up vectors, shapes and aperture dimensions come directly from the exports.
Catalog data is private and ignored; rebuilding needs those exports. Test-only
synthetic fixtures are isolated from the actual playable catalog.

Rules: six guesses, clues reveal 1/2/4/8/16/all portals. A miss or skip advances one
turn; invalid/repeated map names do not. Correct guesses finish immediately;
six misses/skips lose. Finished rounds reveal the answer and full layout. Top and
isometric views are free, using the same portal subset. A consistent frame covers
the full portal layout. First clues are intentionally sparse. No textures,
meshes, map labels or screenshots are used as clue inputs.

Each installation shuffles its map pool using a private stored seed and cycles
through all maps before repeating; daily portal order also uses a seed. Selection
spreads later clues across real placements using farthest-point distance. Daily
snapshots freeze map/order/catalog revision, surviving restarts and imports.
Different installations have independent schedules. Midnight rollover closes
unfinished previous daily rounds. Practice is separate and does not affect stats.

Stats count completed daily games. Daily progress is global per Discord player
across servers; leaderboards show overall daily stats for people who started a
game in that guild. Only explicit Share actions post public, spoiler-free scores.

## Implementation map

- `portle/catalog.py`: import/filter/validate real scene data; normalized map names
  and aliases (including Foregone/FD and Ozone). Catalog format version 1.
- `portle/game.py`: pure rules, nested reveal counts, safe public DTOs, share text.
  No hidden answer, map ID, raw coordinates or source names in active client DTOs.
- `portle/store.py`: transactional SQLite, ownership, frozen snapshots, persistent
  daily/practice rounds, stats, leaderboard. Version checks and interaction event
  IDs protect against concurrent/stale/replayed submissions. Database mode 0600.
- `portle/render.py`: Pillow 1100×760 PNGs of real apertures in top/iso view. Generic
  attachment name, no answer in active image text or PNG metadata. Newly revealed
  portals are amber; earlier portals mint. All layouts use actual coordinates.
- `portle/bot.py`: `/portle` group with play/practice/guess/stats/leaderboard/share/
  maps/help. Private ephemeral board with Guess modal, Skip, Projection and Share
  buttons. Acknowledge interactions before rendering PNGs on a worker thread.
  Importing this module never connects. Allowed mentions disabled.
- `portle/preview.py`: loopback-only HTTP server, allowlisted static files, Host/
  Origin validation, random HttpOnly/SameSite cookie, private ownership and
  no-store responses. Private catalog/database files cannot be served.
- `web/`: responsive dark mint UI, real clue PNGs, map datalist, progress/history,
  result copy and local daily stats. No active solution in page/API payloads.
- `portle/__main__.py`: import-assets, doctor (offline), bot, preview, render-sample.

## Validation completed

`./setup.sh` reran successfully: 23 maps / 3,366 portals. `doctor` generated the
eight-command schema with SDK 2.7.1, UTC, `tokenConfigured: false`, and
`networkConnectionAttempted: false`. Running `./run.sh` without a token exited 2
with the intended local configuration message and made no Discord connection.

**37 tests passed** with `.venv/bin/python -m unittest discover -s tests -v`
(6.35 seconds in the final full run):

- 19 game/store tests: turn limits, correct/final wins, aliases, invalid/duplicate
  guesses, shared puzzle/private progress, four-worker concurrency, replay/stale
  protection, restart, rollover/timezone, frozen catalog changes, practice, streaks
  and map cycle coverage. An early win's public turn label is verified as 1/6.
- 9 preview HTTP tests: anonymous DTOs/images, cookie ownership, invalid guesses,
  progressive/stale image handling, loss/answer/share behavior, Host/Origin guards,
  malformed actions and private-file denial.
- 6 mocked Discord interaction tests: command schema/minimal intents, private
  deferred board, anonymous attachment, owner check, skip edits, free projection,
  finished controls and explicit public sharing.
- 3 real-asset tests: all imported portal values match source exports, actual
  aperture corners are finite, and all **46** full-layout PNGs (23×2 projections)
  render with no metadata spoilers and below 2 MB.

`node --check web/app.js` passed using the bundled Node executable at
`/home/lambchopper67/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.

Browser QA through the in-app browser: loaded real PNGs; invalid answer used no
guess; skip increased clue; projection was free; typed answer survived projection
switch; six skips showed answer/full layout and disabled play; result copied
without answer; practice left daily stats unchanged; daily resumed after reload
and preview restart. Checked 390×844 mobile layout: no horizontal overflow.
Desktop full-page screenshot saved; no browser console errors/warnings observed.

## Remaining activation checks and limits

The code is ready for a user-configured bot. Live Discord connection, actual
ephemeral image delivery, permissions, slash-command propagation and modal board
updates have **not** been tested against a real application. Follow
DISCORD_SETUP.md's server checklist after configuring the token locally. Do not
claim a live bot is running based on offline mocks or the browser preview.

Buttons expire after 15 minutes and after bot restarts. `/portle play` reopens the
persistent daily. Practice state is stored, but old practice boards have no resume
command; start another `/portle practice`. No automated daily channel posts,
notifications, production hosting/service installation or shared-channel game
mode were requested or enabled. Changing catalog/timezone can alter future daily
puzzles; retain the private production DB and seed.

## Latest request — manual screenshot clues (complete, 2026-11-03)

The user explicitly changed the clue source: they will capture screenshots in
Portal Atlas and Portle should expose those images. They also authorized Atlas
portal hiding controls. This supersedes the older generated-clue-only and
Atlas-read-only assumptions above. AGENTS.md has been updated accordingly.

Manual mode is now the CLI default (`PORTLE_CLUE_SOURCE=manual`). It uses the
tracked names-only roster `portle/map_names.json`, requiring no Atlas geometry or
game installation. The legacy generated renderer remains available only through
explicit `PORTLE_CLUE_SOURCE=generated`; there is no silent fallback. Legacy
rounds remain in SQLite and manual rounds/stats use a separate puzzle namespace.

`ClueLibrary` stores private drafts and immutable published sets under ignored
`data/clues/`. Six screenshot slots per map. Uploads are validated, preserve pixel
dimensions/orientation, normalize to PNG and strip metadata. No cropping, resizing,
annotation, inference or generated clues. Draft changes do not alter published
images, and publishing freezes six content hashes into future puzzle snapshots.
Earlier snapshots keep old files even after republish/unpublish. One published
map is enough to play; the full names roster remains valid for guesses.

Added loopback-only `/manage` authoring UI and allowlisted editor API with same-
origin/Host guards plus a per-process editor mutation token. This editor is for
the local installation owner; it is not a publicly authenticated admin service.
Player image URLs still enforce round ownership/version and unlocked clue index;
public round DTOs omit answer, image hashes, source paths and original filenames.
Discord and browser both display the same normalized screenshot bytes and support
reviewing already revealed clues without spending a guess. Manual boards have no
top/isometric projection controls; images are shown as authored.

Current real preview restarted as PID1418589 at localhost8742, same private preview
DB but new manual puzzle namespace. The real manual library is empty: no user
clues were invented or published. It should show the empty/setup screen linking
to the editor. Bot remains disconnected; no credentials requested/searched for.
Atlas remains at localhost8741, with visibility controls committed separately.

Final validation: **54 tests passed in7.935s**, including legacy37 checks, manual
library/store/HTTP and Discord screenshot cases, parallel upload preservation and
manual/legacy stat separation. Log `.local/tests-manual-final.log`. JS syntax
checks passed for web/app.js and web/manage.js. Doctor reports23 answer names,
0 geometry portals, manual mode,0 real published sets and no network connection.

Browser end-to-end QA used a separate server at localhost8743 with its own library
and database under `.local/manual-qa-3749bce4/`. Uploaded six actual Atlas captures
through file choosers, published the temporary Academy set, started a daily,
confirmed native1635×2499 image delivery, skipped to clue2, reviewed clue1 without
advancing, then guessed Academy and won2/6. The end screen unlocked screenshot6
and produced a spoiler-free share. No projection button appeared in manual mode.
These images were testing fixtures in a separate owner-only library, never added
to the user's real drafts or rotation. Temporary server PID1418983 was verified
and stopped, and its agent-created tab5 closed. QA files remain ignored locally.

Real editor remains http://127.0.0.1:8742/manage, showing an empty Academy draft
(0/6), ready for user captures. Screenshot `.local/manual-clue-editor-preview.png`.
The map-specific Open Portal Atlas link correctly targets the chosen answer map.
Editor mobile check at390×844: no horizontal overflow, both empty/populated slots
fit. No console warnings/errors. Viewport override reset. Existing Portle tab4
marked deliverable; Atlas tab3 remains available. Real library still has0 published
sets. Preview PID1418589 remains running. No live Discord token/connection exists.

Portle's README, MANUAL_CLUES.md and DISCORD_SETUP.md now document the manual
workflow. setup.sh defaults to installing dependencies and offline doctor, without
reading Atlas assets. Explicit legacy setup/import options are retained. Default
manual mode reads only the bundled names roster, uploaded screenshots and SQLite.
Backend milestone b599fb2; use git log for the final editor/documentation commit.
No required implementation remains. The next user action is to capture/upload
their first six-image set and publish it. Library/root files must be backed up
with the database because historical rounds retain immutable image hashes.

## Activation follow-up — Discord Missing Access, 2026-11-03

Current state supersedes the earlier empty-library/unconfigured-token notes:
the user published2 manual clue sets and configured a local bot token, guild ID
and America/Los_Angeles timezone. Offline doctor passed. Their ./run.sh then
authenticated but failed guild command sync with HTTP403 / Discord50001.

Read-only diagnosis used the explicitly configured local credential in memory:
GET /oauth2/applications/@me returned200, application name Portle; GET of the
configured guild returned404 /10004 Unknown Guild. This establishes accepted
credentials and inaccessible configured guild, but does not distinguish wrong
server ID from absent bot membership. No token was printed or stored elsewhere;
no credentials were searched for, no settings changed and no commands registered.
An installation URL for the authenticated application was given to the user,
with bot + applications.commands and permissions52224 (View Channels, Send
Messages, Embed Links, Attach Files). Final link permits selecting the correct
server rather than locking to a potentially wrong configured ID. Real Discord
identifiers remain outside Git.

PortleClient.setup_hook now converts Forbidden/NotFound command-sync failures to
DiscordSetupError with HTTP/Discord codes, server-ID vs channel/application-ID
guidance, environment precedence, Guild Install / Add to server vs user-only
installation, and an install link for the authenticated application. It does not
silently fall back to global sync or swallow unrelated HTTP failures. CLI catches
this error and exits2 with a concise message instead of a traceback; raw HTTP
error content is omitted. DISCORD_SETUP.md covers the same recovery steps and
clarifies that offline doctor does not check live authorization.

Verification: .venv/bin/python -m unittest discover -s tests -v passed57 tests in
7.968s. Three added startup tests cover403/50001 and404/10004, scopes/minimal
permissions in the generated URL, no global fallback, no raw-error leakage,
successful guild sync, unrelated HTTP failure propagation and clean CLI exit2.
The initial new test used the wrong SDK application-ID field; corrected fixture
to client._connection.application_id before the successful full run.
git diff --check passed. No preview/server restarts, live game-host interaction,
credential edits or asset changes. The user must install this application into
the intended server and verify DISCORD_GUILD_ID, then rerun ./run.sh and test
/portle practice. Live Discord gameplay is still unverified.

Sources checked: Discord application-command authorization documentation and
opcodes/status-code reference. Code50001 denotes Missing Access, distinct from
50013 Missing Permissions; granting channel Administrator does not establish
membership in a different server.

## Content correction — remove incorrect Abyss clues, 2026-11-03

User confirmed Discord startup now works and requested removal of the incorrect
Abyss entry. Removed MAP_Abyss's published set and six-slot draft from the active
manual clue index under the library's cross-process lock and atomic replacement.
Backed up that single entry first under ignored .local/backups/removed-abyss-*.json
with mode0600. Immutable image files remain for existing saved-round references.
Verified Abyss is absent from both packs and published(), and all other entries
are exactly unchanged. One published set remains, sufficient for play. This is a
local content edit, so no code tests or bot restart are necessary; new puzzles
read the library afresh. The answer-name roster and Atlas maps are unchanged.

Read-only aggregate check before removal: production Discord DB contained0 Abyss
puzzle snapshots; the browser preview DB contained2 historical snapshots. No
progress/snapshots/stats were altered. Existing browser rounds retain their frozen
images. Real token, server IDs and clue content remain outside Git. User's live
bot is managed by the user; no bot process or preview process was stopped.
