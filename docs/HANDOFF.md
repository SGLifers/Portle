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

## Map dropdowns — 2026-11-04

User requested dropdown submission instead of a text field. Replaced Discord's
Guess map button/text modal with a native single-choice map select on daily and
practice boards. Selecting immediately submits; the placeholder, active embed
and help say so. Uses the existing store action/version/interaction-ID checks
and edits the same private board. Finished boards disable the dropdown. Optional
`/portle guess map_name` with autocomplete remains compatible; slash schemas and
required permissions are unchanged.

Options are the entire alphabetical names roster, currently23, without filtering
to published packs or marking the answer. Abyss remains a valid guess despite
its incorrect clue set having been unpublished. Custom rosters over25 names use
Previous/Next maps buttons; browsing pages is free and preserves projection and
the selected clue. Pages reject stale/finished boards and enforce ownership.

The browser preview now uses a required native select rather than input/datalist.
Its placeholder has an empty value; Make a guess stays disabled until a map is
selected. Selection does not submit until the player presses Make a guess. All
submission controls disable during requests; a successful turn resets selection.
Repeated-guess errors retain selection, and reviewing screenshots retains it.
Dark styling, keyboard focus and responsive width apply to the new select.

Validation: `.venv/bin/python -m unittest discover -s tests -v` passed62 tests in
8.155s. Five new Discord tests cover neutral alphabetical options, daily/practice
wins, wrong guesses, duplicate interaction delivery, foreign ownership, stale and
repeated guesses, and51-name pagination with free navigation and reachable later
page options. Existing manual-clue test confirms all roster names remain options
even with just one published set. SDK serialization contains no TextInput.
Node `--check web/app.js` and `git diff --check` passed. Consulted discord.py's
official interaction API for the select implementation.

Browser QA on the real local manual library: dropdown shows23 names, placeholder
disables submit, wrong guess unlocks clue2, repeated guess costs no turn, free
clue review preserves selection, correct guess completes practice and hides the
form; practice did not affect daily stats. No browser errors/warnings. Left a
fresh practice board in the new preview tab; screenshot is ignored
`.local/dropdown-preview.png`. No clue edits or production Discord DB changes.

Started preview on127.0.0.1:8742, PID213145, exec session70417, using the normal
separate `.local/preview.sqlite3`; verify PID identity before any future signal.
Portal Atlas server and user-managed Discord bot were untouched. To activate
Discord dropdowns, the user must stop their existing bot with Ctrl+C, run
`./run.sh` again, then open a fresh `/portle play` or `/portle practice` board.
Daily progress persists; old message components expire after restart. Live
Discord dropdown delivery remains to be confirmed by the user after restart.

## Make guessed maps unavailable — 2026-11-04

User has not yet tested/restarted the dropdown version and requested preventing
selection of already-guessed maps. Discord now removes guessed maps from the
board dropdown using saved attempt map IDs, so guesses entered through aliases
or the optional slash command are covered. Skips remove no choices. Filtering
is specific to the round/player, survives daily resume/restart and resets for
fresh practice. Pagination counts only remaining maps and clamps the page if
filtering removes the last page. An exhausted roster renders a disabled valid
No maps remaining select with one inert option (Discord requires options).

Browser render now disables each guessed option and appends (already guessed),
with muted styling. Options rebuild from their canonical values on each render
so labels do not accumulate and new rounds reenable choices. This uses only the
already-public attempt history; no answer/map ID fields were added to payloads.
The backend's duplicate, stale and owner validation still protects direct calls.
Optional typed `/portle guess` retains its existing autocomplete and rejects
duplicates without costing a turn, as before. No schema/permission changes.

Verification: full Python suite passed65 tests in8.257s; Node syntax and Git
whitespace checks passed. Three new tests cover persisted daily/practice history,
aliases, skips, another player, fresh practice, a fully exhausted roster and a
26-to25-option pagination transition. Existing replay/miss test now checks that
the wrong choice disappears. Browser QA confirmed disabled (already guessed)
options after a miss, unchanged availability during free screenshot review,
selection preservation and all choices reenabled for fresh practice. No browser
warnings/errors. Screenshot: ignored `.local/guessed-maps-preview.png`; native
popup overlays are not captured, so disabled-state proof is the live AX/DOM check.

QA used only `.local/preview.sqlite3`. The old preview daily had a frozen Abyss
snapshot from before clue removal and was completed during testing; this is
expected snapshot persistence, not a newly published Abyss set. New practice
used the current library and retained Abyss solely as an incorrect guess option.
No production Discord progress or clue content changed. Existing preview server
PID213145/session70417 remains running; user-managed bot and Atlas untouched.
User activation: one Ctrl+C / `./run.sh` restart loads both dropdown commits,
then `/portle play` opens a fresh board with persisted daily guesses filtered.

## Administrator-only Discord practice — 2026-11-04

User requested restricting practice to admins. `/portle practice` now has an
application-command runtime check requiring a server context and the invoking
player's current Discord Administrator permission. A role named Admin without
that permission or moderator permissions such as Manage Server are insufficient.
Denied commands respond ephemerally with an explanation and `/portle play`
guidance before creating any round. Command description and help identify the
restriction. The bot itself still needs only its existing minimal permissions.

RoundView records the round mode and applies the same permission check to every
practice component interaction after checking ownership. This covers guesses,
skips, clue review, map pagination and sharing, including boards opened before a
player loses Administrator. Daily controls and ordinary commands remain open to
members. The local loopback browser preview/editor has no Discord identity and
retains practice as the owner's playtest tool; no web authentication was added.

Use an enforced runtime check, not default_permissions on the practice subcommand:
the installed SDK source and official discord.py interaction API confirm that
Discord ignores default permission hints on subcommands. The root `/portle` group
has no Administrator default restriction, so daily access remains available.
Members may still see the practice command in Discord's picker but cannot run it.

Validation: full Python suite passed68 tests in8.265s; git diff --check passed.
Three new tests cover member/moderator rejection, ephemeral errors before/after
defer, no round creation for denial, administrator success/private practice,
ordinary-member daily success, DM rejection, permissions revoked on existing
practice controls, foreign admin ownership rejection and unchanged round state.
README and Discord setup guide updated. No live Discord messages, permission
edits, bot restart, database changes or browser/Atlas changes were performed.
User activation: Ctrl+C the existing bot, run `./run.sh` again, then test
`/portle practice` with admin and ordinary member accounts. This restart also
loads earlier dropdown changes if they have not yet been activated.

## Automatic daily results and public Play button — 2026-11-04

User authorized automatically posting finished results in Discord, with a button
for others to play without slash commands. Daily wins/losses now post in the
channel of the finishing interaction, after a dropdown guess, skip or slash guess.
Result contains player attribution, date, score and colored squares only; no map
names/IDs, guess names, images or coordinates. AllowedMentions.none prevents pings.
Guesses, clue boards and all other ordinary feedback stay ephemeral. Admin-only
practice does not auto-post; its existing explicitly requested sharing remains.

PlayPortleView has timeout=None and stable custom ID portle:play-daily:v1.
Successful PortleClient.setup_hook registers it for persistent dispatch, so all
public Play buttons work after restart. Clicking defers a new ephemeral thinking
response and starts/resumes the clicking user's current daily, without editing
the public message or the finisher's round. It works for ordinary members, uses
today's daily even on old posts, records guild participation, and does not create
new practice or bypass admin checks. Missing-library/DM/errors are handled
privately. Existing Share result and /portle share also include this button and
player attribution; explicit re-sharing remains available.

SQLite gains result_posts(round_id PRIMARY KEY,status,message_id) via automatic
CREATE TABLE IF NOT EXISTS on startup. claim_result_post checks ownership and
finished-daily status inside BEGIN IMMEDIATE, then reserves a pending row before
sending. This prevents duplicate automatic sends from replays, concurrency,
multiple store instances and restarts. Successful posts record sent/message ID;
failed/uncertain sends remain reserved as failed (or pending after interruption).
The bot gives private saved-score/manual retry guidance on HTTP/network errors.
This deliberately favors avoiding duplicates over automatic retry of uncertain
sends: check the channel before explicitly sharing again. A crash between saving
the final turn and claiming/sending can require /portle share after restart.
There is no announcement backlog or automatic post when reopening old finished
boards. Private clue/render failure still permits posting the final score.

Validation: `.venv/bin/python -m unittest discover -s tests -q` passed80 tests in
8.468s. Eight new Discord tests plus four store tests cover persistent registration,
member ownership/private opening, resume/day rollover, DM/missing-clue/error
handling, win/loss auto-posts, replay suppression, explicit share buttons,
spoiler-free/no-ping messages, HTTP/network failure privacy, private render failure,
atomic claims under4 workers, restart persistence and schema upgrade preserving
old progress. Existing dropdown tests now assert daily auto-post vs practice
silence. Git whitespace checks passed. Official discord.py persistent-view example
and interaction API consulted. README, setup guide, preview help and AGENTS updated.

No live Discord messages, credential reads, bot restart, public deployment or
production DB mutations were performed. All behavior tested using temporary
databases and offline Discord mocks; live posting/button delivery remains to be
confirmed after user activation. Existing user-managed bot and Atlas untouched.
Activation: Ctrl+C the current bot, run `./run.sh`, then finish a daily or use
`/portle share` on an already completed daily to create a public Play button.
Another member should click it and see Only you can see this. Verify the button
again after restarting the bot. It requires the bot online and normal channel
send access; threads additionally need Send Messages in Threads. This does not
require privileged intents or giving the bot Administrator.

## Diagnose automatic post Forbidden — 2026-11-04

User reported generic saved-result/post-not-confirmed message, then identified
bot-test and terminal warning Automatic result post failed: Forbidden. Running
bot is user-managed PID326743; stdout/stderr point to a separate /dev/pts/0,
not a captured log or this chat's app terminal. No reads of terminal input or
process credentials, signals, bot restarts or live messages were performed.

Read-only Discord diagnosis used the explicitly configured local .env credential
in memory, never printed. No inherited token/guild environment overrides exist
in this tool environment. GET /users/@me returned200. GET configured guild's
channels returned403 /50001 Missing Access. GET /users/@me/guilds returned200
with0 servers, establishing that the configured bot account has no guild
memberships. This explains rejection of bot-authenticated channel sends even
though interactions work. No channel permission overrides were accessible, so do
not claim to have inspected bot-test's overrides. GET /oauth2/applications/@me
returned200 and application name Portle. Generated a user-facing installation
URL for that exact app with bot + applications.commands and permissions52224;
Discord identifiers and URL remain outside Git.

User action: Guild Install / Add to server for the same Portle application,
select the server containing bot-test, then run /portle share there for the saved
result. Existing failed reservation is deliberately retained. No score/progress
reset is needed. The running bot can receive guild membership updates; restart
only to load the improved diagnostics below or if Discord does not update access.

Code now includes safe result_post_error diagnostics with HTTP status/Discord
code and targeted guidance for50001 missing access,50013 missing permissions,
50083 archived thread,10003 unavailable channel and network/missing-context
failures. Terminal warnings include numeric codes, never raw response/error
contents. Added regression coverage for safe actionable feedback. The prior
generic warning concealed these details; this diagnostics patch does not change
the public send route, membership, server permissions or retry policy. Official
Discord status-code and thread-permission sources consulted. Updated setup guide.
Verification: full Python suite passed81 tests in8.380s; git diff --check passed.
User must complete the server installation; the agent has not changed external
permissions or verified a successful public post after installation.

## Admin daily reset command — 2026-11-04

User requested an admin command to reset someone's daily score. Added
`/portle reset player:@member`, with a required discord.Member picker (user option)
and a runtime Administrator/server-context check. The shared check/message was
renamed from practice-specific to server_admin_check/ADMIN_ONLY_MESSAGE; practice
restrictions remain unchanged. Reset confirmation is deferred/ephemeral, omits
answers/clues, uses AllowedMentions.none and does not DM or ping the target.
Help, command description, README and setup guide describe the scope. Nine slash
subcommands now exist; no new privileged intents or bot permissions are needed.

GameStore.reset_daily resets only the current configured-local date and current
manual/generated clue mode. It replaces the active round ID/state with a fresh
clue1 round using the same frozen puzzle snapshot, without regenerating clues.
Stats, distribution and leaderboard derive from active rounds, so today's old
result is immediately excluded; earlier days, other players, practice, legacy
mode scores, puzzle snapshots and guild participants remain intact. No progress
is a no-op rather than creating/resetting a new round. Daily state is per user
across this bot's servers; reset applies everywhere, stated in command/help/docs.

New private daily_resets table records interaction ID, actor, target, guild,
local day, previous state, fresh round ID and timestamp. Archive and replacement
commit together in BEGIN IMMEDIATE. Interaction IDs make both actual resets and
no-ops idempotent across retries/restart, including retries after new guesses.
Different-target reuse of a reset event is rejected. Old boards cannot get/act on
their removed round ID; old action-event IDs and result-post reservations are
retained as tombstones to prevent replay against fresh progress. Finishing the
new attempt can auto-post a new result. Existing public posts are deliberately
left visible; no channel messages are deleted. The player reopens with Play
Portle or /portle play. There is no new public reset API on the browser preview.

Verification: full Python suite passed92 tests in8.638s; git diff --check passed.
Eleven added tests cover member/moderator/DM denial, admin target selection and
ephemeral/no-ping feedback, old-board rejection, fresh/unplayed no-ops, wins and
losses, prior-history/player/practice preservation, saved audit, stale event
replay, concurrent reset delivery under4 workers, restart idempotency, timezone
boundaries, post eligibility for a new attempt, manual frozen clues after
republish/unpublish and legacy-score isolation. Schema checks confirm the required
user picker and unchanged nonprivileged intents. Consulted official discord.py
member-option documentation and inspected the installed SDK-generated schema.

No real player score was reset, no production database/schema was touched and no
Discord messages, permission edits, bot restart or credential reads were performed.
User-managed bot and Atlas remain untouched. Activate by Ctrl+C / `./run.sh` so
startup resyncs the command group and creates the audit table in the chosen DB.
Then use `/portle reset player:@member`; the member reopens their daily board.

## Remove manual Discord sharing and clue footer — 2026-11-04

User requested removing the Share result button, /portle share command and
"Manually supplied screenshot · /portle maps for valid answers" footer. Removed
the board button/callback, slash subcommand and embed footer (manual/generated).
Eight subcommands remain, including admin reset. Automatic daily result posts
with persistent Play Portle stay unchanged; practice results now stay private
with no manual public-sharing path. The browser's Copy spoiler-free result
utility and score serialization remain, since they are used for local copying,
private finished-board score text and automatic result messages.

Removed references to the old sharing controls from help, active documentation,
error feedback and the store comment. Error messages now direct players to check
the channel and ask an admin to review access. Earlier manual retry instructions
in historical handoff sections are obsolete. Failed/uncertain posts retain the
existing no-automatic-retry policy; reopening a completed round does not repost.
No replacement manual repost command or button was added.

Validation: full Python suite passed92 tests in8.445s; git diff --check passed.
Updated existing checks assert no share command/button on active/finished boards,
no footer on manual/generated embeds, no dead share instructions in error text,
and continued automatic daily result posts/persistent Play buttons. README,
Discord setup guide and AGENTS reflect the new behavior. No live Discord
messages, command-sync calls, credentials, DB changes or bot/Atlas restarts.
Activate with Ctrl+C / `./run.sh` to resync commands, then open a fresh board
using Play Portle or /portle play. Old ephemeral boards are not retroactively
edited and their controls expire after restart.

## Open capture workspace and editor — 2026-11-04

User requested relaunching Atlas and the editor to prepare more screenshots.
The existing Portle preview process PID213145/session70417 was still listening
on127.0.0.1:8742; /manage returned200, so reused it. Opened a fresh valid editor
browser2/tab8 at http://127.0.0.1:8742/manage and selected Terra13 to match the
user's Atlas map. The six empty upload slots are ready; nothing was uploaded,
cleared, published or unpublished. Screenshot: ignored .local/relaunch-editor.png.

Atlas was stopped; launched PortalAtlas/./run.sh, owned PID372689/session49751,
127.0.0.1:8741. Its .local/server.pid now reflects that identity. Reloaded valid
Atlas tab5 at /#map=MAP_Terra13; renderer and Screenshot control are ready.
Both browser tabs marked deliverable and both servers left running. Old error
tabs and Discord authorization page left alone; user-managed bot untouched.
No application code changed or tests required; HTTP/UI checks verified readiness.

## Multi-server installation — 2026-11-04

User requested making Portle installable on multiple servers. Existing transport
already supports global registration when DISCORD_GUILD_ID is blank; current
local configuration still selected one development server. Set that one local
.env key to blank with dotenv.set_key, preserving other settings/credentials.
No exported guild/token override exists in the tool environment. Optional scope
question received no reply during work; retained and stated current shared
per-player progress across servers, rather than changing the database model.

Code now explicitly declares Guild Install only and guild interaction context
only on the root group. Added reusable server_install_url(application_id) with
bot + applications.commands, permissions52224 and integration_type=0, without
pinning a guild. Startup diagnostics use it, and logs identify global vs single
development scope. Offline doctor now uses the actual configured guild choice
and reports commandScope/serverInstallOnly without exposing IDs or networking.
No new slash commands; eight remain. README/setup/env example describe multi-
server operation, shared progress, server participant leaderboards, admin reset
scope, owner-only local editor and existing component channel-allowlist limitation.

Live application checks/authorized configuration used the known local credential
only in memory. Public Bot was already true, code-grant requirement false, Guild
and User Install configured, but default install_params requested only commands.
Updated /applications/@me install_params and Guild Install oauth2_install_params
to bot + applications.commands /52224. Preserved User Install configuration and
all other app settings. Read-back GET returned200 and verified these fields.
Backup of only installation settings is ignored
.local/install-settings-before-multiserver.json, mode0600; no credentials copied.

Registered the current /portle root globally using POST to the specific named
application command (not bulk overwrite), preserving other global commands.
Read-back verified eight subcommands, integration_types[0], contexts[0]. Previous
global Portle definition is backed up in ignored
.local/global-portle-before-multiserver.json, mode0600. No clue assets or screenshot
content were included in registration. This running bot already has a global
in-memory root definition/fallback, so new guild interactions can dispatch;
restart remains recommended to load current source and persist global startup.

Bot now reports1 server membership. Checked its legacy guild root: permission
lookup was unavailable using bot auth, so no command was deleted or permission
changed. A follow-up metadata-only check verified the legacy guild's eight
subcommands already exactly match the global definition; no update was needed.
Thus existing command-level overrides remain intact. An old guild copy remains
and can shadow future global definition changes in that development server;
future migration must preserve its overrides rather than blindly deleting it.
Other guild/global commands were untouched. Numeric IDs/installation URLs remain
outside Git. No server roles, channel permissions, scores, bot process, Atlas,
clue content or channel messages were changed/sent by this task.

Validation: full Python suite passed96 tests in8.619s; git diff --check passed.
Four new tests cover one global sync (no per-guild copy), canonical unrestricted
server-install URLs/minimal permissions, offline doctor scopes/ID privacy, and
independent players across two guilds with shared puzzle and participant-filtered
leaderboards. Schema tests verify server-only installs/contexts. Official Discord
application/command and installed SDK documentation checked. Actual installation
into a second server remains for an administrator with Manage Server to authorize.
Use the existing application install link; keep one bot process/token/library.
Restart via Ctrl+C / ./run.sh to load current source/config; doctor should report
global: all installed servers. Every joining server gets the global /portle group.

## GitHub publication and secret audit — 2026-11-06

User explicitly authorized pushing this repository to
https://github.com/SGLifers/Portle.git after checking for sensitive information.
The destination had no branch refs before publication. The initial history had
16 commits, 124 unique file blobs and 33 paths: source, tests, documentation,
configuration examples and an empty data placeholder. No screenshots, extracted
geometry, SQLite files, local credentials or other binary assets were committed.

Gitleaks v8.30.1 scanned all commits with full redaction and found no leaks.
An independent scan read every historical blob and commit metadata, compared the
configured local bot credential in memory without printing it, and checked for
Discord tokens/IDs, webhook credentials, private keys, GitHub tokens and URLs
containing credentials. No sensitive values were found. Nine broad assignment
matches were reviewed: example placeholders or environment-variable lookups.
All commit author/committer identities use Codex's local placeholder identity.
Verified Git ignores .env variants, .local, .venv, databases and clue assets.
Detailed audit outputs/tools stay under ignored .local/security-audit/.

Publish only the committed branch history; never add ignored local files.
The intended remote branch is main, keeping local codex/portle as the working
branch. Git HTTPS authentication is unavailable in this shell; existing SSH
authentication successfully accessed the same destination, so origin uses the
requested HTTPS fetch URL and an SSH push URL. No history rewrite is needed.
This documentation-only milestone does not change runtime behavior. No bot
restart, Discord messages, score changes or local clue-library edits were made.
After pushing, verify the remote main SHA matches local HEAD before reporting
publication complete. The earlier no-remote notes describe historical state.

## Remove browser gameplay; retain local clue editor — 2026-11-06

User requested removing browser gameplay after confirming the Discord game does
not need it. Removed web/index.html, web/app.js, the gameplay stylesheet and
portle/preview.py. New portle/editor.py serves only the authoring page at both /
and /manage, editor JS/CSS, and /api/manage endpoints. Old gameplay info, stats,
round image, start/action endpoints and assets return404. Removed browser player
cookies and gameplay HTTP handlers; Discord gameplay/store behavior is unchanged.

Start the tool with `.venv/bin/python -m portle editor --port 8742`; the preview
command is removed. The editor takes only the names catalog and ClueLibrary,
without opening GameStore, creating player progress, connecting to Discord or
requiring valid bot-only timezone/guild settings. It requires manual clue mode.
Preserved Host/Origin checks, mutation capability, upload validation/limits,
static route allowlist and response privacy/security headers. The editor keeps
its existing layout using a standalone manage.css; removed Back to game and Play
Portle links. README, setup/manual-clue docs and AGENTS describe Discord-only play.

Replaced browser gameplay HTTP tests with editor coverage for complete upload,
image review, publish, clear and unpublish, old-route removal, malformed payloads,
foreign hosts/origins and private-file guards. CLI tests confirm the old command
is rejected, generated mode cannot launch the editor and no player database is
opened. Tests mock local dotenv loading. Full suite:94 tests passed in6.012s;
manage.js syntax and git diff whitespace checks passed. Browser verification
loaded the actual editor at the root URL, showing six slots/map choices and no
play links, with no console errors/warnings. Screenshot is ignored
.local/editor-only.png. No user clue uploads, publications or progress changes
were made during browser QA; mutation tests use synthetic temporary libraries.

No preview process was running. Started the new editor at127.0.0.1:8742,
owned PID237621 / exec session9513, and left it running. Fresh browser2/tab10
shows the editor and is marked deliverable. Old error tabs were left untouched.
The bot and Atlas processes were not changed. Historical .local/preview.sqlite3
and all user libraries/databases remain intact; they are not part of this commit.
Earlier preview startup/process instructions above are obsolete.

## BisectHosting preparation and startup readiness — 2026-11-06

User purchased Bisect Discord bot hosting and requested setup. Added root bot.py
for the panel's BotStartFile field: with no arguments it invokes the existing bot
CLI; explicit arguments such as doctor still work. Docs/BISECT_HOSTING.md covers
Python3.12, requirements/pip packages, root layout, Git/file installation, private
.env configuration, global commands, timezone preservation, database/library
migration, initial verification and later clue-only updates. README links it.
User supplied Bisect's exact readiness requirement. PortleClient.on_ready now
prints `successfully finished startup` to stdout with flush=True, after Discord
readiness rather than merely importing or registering commands. Reconnect-ready
events can emit the same safe marker again. No credentials or identifiers in it.

Known local config was read only for migration paths/mode/timezone, without
printing the token. It uses manual mode, default data/clues and production SQLite,
America/Los_Angeles and the bundled names list. User replied stopped after being
asked to Ctrl+C the bot. Verified local process PID18040 is actually suspended
(stateT), not exited. No signals were sent. It cannot write while suspended, so
prepared the snapshot, but tell the user to fg then Ctrl+C in its original terminal
to fully close it before activating the hosted copy. Do not resume it as a normal
local bot after migration, because the hosted database will become authoritative.

Ignored .local/bisect-migration-current.txt points to the current private export
folder. portle-private-data.zip contains only data/portle.sqlite3 and the entire
clue library's index/images (24 PNGs,4 published sets), with no .env/token. Used
SQLite backup and a shared clue-library file lock; source database and clue files
were not edited. Converted the copied database to DELETE journal mode before
archiving, so it is standalone and needs no copied WAL/SHM. An initial archive
validation caught temporary SQLite sidecar entries; repacked and revalidated the
final archive against the strict data-file allowlist. Zip integrity/SQLite quick
check passed; every historical clue reference is present. Restoring the ZIP to a
temporary directory passed offline doctor with credentials explicitly empty.
Files/archives are private mode0600 under a mode0700 export directory. Do not
publish these data archives or put real IDs/images in Git. Source ZIP is generated
with git archive from the final committed HEAD, separately from private data.

Validation:95 tests passed in6.020s, including a new offline lifecycle check that
setup_hook alone emits no readiness marker and on_ready prints/flushed the exact
required phrase. Launcher doctor and absent-token startup checks passed using
isolated temporary databases/libraries, without connecting to Discord. Final
whitespace/secret scan checks required before push. No Bisect login, account
settings, remote upload, hosted process, Discord commands/messages or production
score changes were performed. Hosting remains for the user to configure using
the prepared ZIPs and guide. Existing local editor and Atlas were untouched.

## Fresh hosted scores and clues-only transfer — 2026-11-06

User will install source directly from GitHub and does not require old scores to
transfer. The application still uses SQLite; no MySQL/PostgreSQL integration was
requested or implemented. Updated Bisect guide to make clues-only/fresh database
the primary route and retain full migration as an optional path. A new hosted
database creates a new seed and can change daily selection. Preserve hosted
scores after launch, and do not overwrite them with the old local snapshot.

Created ignored portle-clues-only.zip in the existing private export folder
referenced by .local/bisect-migration-current.txt. It contains24 PNGs and the
clue index only, with no database or token. Verified zip integrity, strict clue
path allowlist and all draft/published image references. Existing full snapshot
and local databases were preserved. No hosting files were uploaded or deleted.

Git status revealed an untracked editor swap filename for .env. Did not inspect
its content. Added standard Vim swap/backup ignore patterns to keep such local
files out of future commits. Confirm ignore checks and whitespace/secret scan
before push; no application behavior changed or additional runtime tests needed.

## Rename Erosion to Dought — 2026-11-09

User requested Dought as the display/answer name for Erosion while discussing
Atlas screenshot automation. Updated bundled map_names.json, preserving
MAP_Erosion and adding Erosion as an accepted alias. Existing clue library keys,
images and stored rounds remain intact. Future legacy asset imports also use
Dought plus the old alias. Historical frozen puzzle names remain as saved; both
old Erosion and new Dought can solve those old snapshots because the IDs match.
New roster/editor/dropdown labels and new puzzle snapshots use Dought. Existing
private generated catalogs/custom answer lists are not rewritten automatically.
Catalog metadata revision changes, so future puzzle ordering may change; already
created daily snapshots are preserved. No production database changes were made.

Added a regression covering a frozen Erosion manual daily resumed under the new
roster: Dought and Erosion both solve it, all clue bytes remain usable and the
snapshot is unchanged. Full suite passed96 tests in6.022s; whitespace checks
passed. Atlas name/PNG filename changes are committed in its independent repo.
Source-only Portle update is pushed to main after redacted secret scanning; the
host receives it on restart with Bisect Auto Update enabled. No bot starts,
Discord messages, command syncs, tokens, score resets or hosting actions here.
Screenshot batch capture was assessed as feasible, not implemented or published.

## Portal-only host data package — 2026-11-09

User explicitly requested regenerating Atlas captures with geometry off, portals
on, labels/lines/all angles/cutaway off and preparing an uploadable bot data
folder. Atlas now supports geometry/cutaway batch options, default off, and
completed a fresh25-map/150-PNG batch with those exact flags,1280x800, progressive
groups and random camera per clue. Seed portle-portals-only-2026-11-09.

Prepared isolated private output, without editing the live local authoring
library, hosted bot, credentials or score databases:
/home/lambchopper67/Downloads/Portle-host-data-2026-11-09/data/clues/index.json
/home/lambchopper67/Downloads/Portle-host-data-2026-11-09/data/clues/images/*.png
Upload ZIP: /home/lambchopper67/Downloads/Portle-host-data-2026-11-09.zip
34.42MiB; SHA256 f5277aa3c3c3b3effb735d90321bd56c5bd68b70a536cefa4b48d0d8272bc54a.
UPLOAD.txt and VALIDATION.json are beside the data folder, outside the upload ZIP.
All generated files are private/local and outside Git. No application code
update is required on the host. This is a clue-library update only.

Packaging used the existing ClueLibrary.upload/publish methods in the isolated
output folder:23 supported map sets/138 new PNGs, including newly captured Abyss
and Dought. The earlier incorrect Abyss images are not reused. Training and
HangmanR3 remain outside Portle's23-answer roster and were excluded. Copied all24
existing local PNGs first under shared library lock; retained them in the export
for frozen rounds. Total162 image files and one index in ZIP. Original library
file hashes are unchanged. Published pack IDs are new in the exported index;
existing daily snapshots remain frozen when the host receives the update.

Reproducible one-off packaging script is ignored .local/package-portal-batch.py;
run from Portle with PYTHONPATH=. .venv/bin/python .local/package-portal-batch.py.
It refuses to overwrite the output destination. Raw input is the normal browser
download at /home/lambchopper67/Downloads/
portal-atlas-clues-portle-portals-only-2026-11-09.zip (not the earlier geometry ZIP).
Validation: ZIP CRC passes; decoded all150 raw PNGs at1280x800/no metadata/unique
hashes; all25 group sets balanced, exclusive, exact coverage and progressive.
All raw map layer flags match and cutoffHeight null. All138 new images normalized
through ClueLibrary with opaque hash filenames. Every published/draft reference
loads and matches. Actual GameStore.start/image/act exercised all six clue stages
for each of23 maps using temporary practice DBs only. Export ZIP allowlist admits
only data/clues/index.json and data/clues/images/<64hex>.png; no SQLite, .env,
coordinates, capture manifests or lock files. All25 Atlas scene hashes unchanged.

Upload procedure: stop hosted bot, back up its data/clues, merge supplied image
files FIRST (keep ALL older remote images, including ones not available locally),
then replace data/clues/index.json and restart. Do not delete/replace the whole
remote data folder or overwrite data/portle.sqlite3. Existing selected daily keeps
old clues; new practices/future dailies use the new pool. No remote access/upload,
Discord interactions or GitHub push performed. Local original editor library stays
at its prior4 published sets; this output is a separate upload snapshot.

## Progressive four-portal-first host package — 2026-11-17

User requested progressively larger portal additions instead of even six groups,
minimum4 portals first, and screenshot files for the host. Updated Atlas batch
planning in its independent repo; default growing sizes reproduce the user's
50-wall example4/5/7/9/11/14, cumulative4/9/16/25/36/50. Seed
portle-progressive-2026-11-17,1280x800, random angle per clue; only portals on,
geometry/labels/lines/all angles/cutaway off. First all25-map run completed but
browser download failed to reach disk. Added normal Atlas Save ZIP locally,
repeated deterministic run, saved150 images successfully and copied raw ZIP to
/home/lambchopper67/Downloads/portal-atlas-clues-portle-progressive-2026-11-17.zip.

Final private outputs (all outside Git):
/home/lambchopper67/Downloads/Portle-host-data-2026-11-17/data/clues/
/home/lambchopper67/Downloads/Portle-host-data-2026-11-17.zip (58.17MiB)
/home/lambchopper67/Downloads/Portle-host-data-2026-11-17/screenshots/<Map>/clue-01.png..06.png
/home/lambchopper67/Downloads/Portle-progressive-screenshots-2026-11-17.zip
UPLOAD.txt and VALIDATION.json beside data include instructions/per-map counts.
Host ZIP SHA256 a3ac1852aaeefb69ebab2ea673bc690afa2b043ee209fd1e14718fca45e6ad5d.
Raw ZIP SHA256 dcf150998985d50b05566e39a6e7bbf7735785cb8acfcbb215307c9689000d72.

One-off ignored script .local/package-progressive-batch-2026-11-17.py was run from
Portle with PYTHONPATH=. .venv/bin/python .local/package-progressive-batch-2026-11-17.py.
Refuses overwrite; all captured images processed through existing ClueLibrary.
Published all23 roster maps with138 new clues into isolated output. Excluded
Training/HangmanR3. Retained all162 immutable images from previous delivered Nov9
library (includes24 local older originals), giving300 PNGs plus index.json only
in host ZIP. Named review ZIP contains only138 new PNGs in23 display-name folders.
Neither local authoring library (still4 published sets) nor prior export changed.

Validation passed: raw CRC/150 decoded PNGs/no metadata/unique hashes/exact layers;
first4, nondecreasing additions for all23 supported maps; exact exclusive portal
coverage and cumulative prefix sets; last clue all portals. Every draft/published
image reference verified. Actual GameStore.start/image/act traversed six clues for
each23 maps against temporary practice DBs only. Host ZIP CRC/path allowlist passed;
no credentials, SQLite, IDs of players/servers, raw coordinates, manifests or lock
files in upload. Source library hashes are in ignored
.local/progressive-source-library-hashes-2026-11-17.json and match after packaging.
All25 Atlas source scene hashes unchanged. Atlas18 Node and57 Python tests passed.

Upload host-ready ZIP at server root while bot stopped after backing up clues;
merge data/clues/images FIRST, keep ALL older remote PNGs (some may be unknown
locally), replace data/clues/index.json last, then restart. Preserve hosted
data/portle.sqlite3 and .env; no bot code update required. Existing selected daily
keeps its frozen screenshots; future dailies/new practices use progressive sets.
No live local/remote bot, Discord, GitHub push, game or SplitgateHost operations.
Handoff/docs changes committed locally; Atlas code has its own independent commits.

## Current-clues-only package including takedown — 2026-11-17

User explicitly clarified to discard historical images and keep only new clues
in data/clues/index.json. Previous index already referenced only138 current clues;
the prior58.17MiB ZIP had162 extra historical PNGs. Created a23-map new-only ZIP at
/home/lambchopper67/Downloads/Portle-host-data-new-only-2026-11-17.zip (23.75MiB),
then superseded it with a combined29-map package after capturing Simulation maps.
Do not repeat the previous keep-all-old-images instructions for this user's
intentional replacement package. Original libraries/backups were not deleted.

Atlas extracted MAP_Simulation and compiled6 roots separately, then captured36
new progressive PNGs: Simulation Anomaly39 walls, Charlie36, Divide30, Faceoff50,
Hectic72, Moshpit57. Each first clue4; cumulative nested additions/final full map;
same portal-only settings/1280x800/random camera per clue. Raw capture is ignored
../PortalAtlas/.local/captures/capture-514d991796d94ee78fc6670df0baa842.zip. All6 maps
have validated geometry extraction and independent source roots. No installed game
or existing arena scene writes. Atlas60 Python tests pass; no browser errors.

Final user-facing artifacts, all private/outside Git:
/home/lambchopper67/Downloads/Portle-host-data-29-maps-new-only-2026-11-17.zip
(29.88MiB, SHA256 0018ff3f85ecc68ade932cc7c1f8ca44b4b99157973f3685b0f63c58b168e1d3)
/home/lambchopper67/Downloads/Portle-host-data-29-maps-new-only-2026-11-17/data/
/home/lambchopper67/Downloads/Portle-screenshots-29-maps-2026-11-17.zip (29.85MiB)
Named screenshots/UPLOAD.txt/VALIDATION.json are beside data in the export folder.
Upload ZIP contains176 files:174 hashed PNGs + index.json + data/map_names.json.
Index drafts/published sets cover only current29 maps/174 current images;0 orphan
or historical images. No overlap with old Nov9 image hashes. No database, token,
raw coordinates, source geometry, archive manifest or lock file in upload ZIP.

The bundled default Portle roster in Git remains23 maps. The package supplies a
29-map names-only catalog containing all existing IDs/aliases plus six stable
MAP_Simulation_<Name> IDs. Set PORTLE_CATALOG=data/map_names.json on the host
(.env or panel environment; panel takes precedence), and upload this file with
data/clues. Existing code supports it; no bot code update/GitHub push required.
Same override can be used for local clue editor authoring later. No .env changed.

Packaging command, from Portle:
PYTHONPATH=. .venv/bin/python .local/package-takedown-new-only-2026-11-17.py
Ignored one-off script refuses overwrite. Starts isolated library from previous
current23-map index but copies only its138 referenced PNGs, then uploads/publishes
36 real Simulation captures through ClueLibrary. All source libraries preserved.
Validation:6-map raw ZIP CRC/decoded PNG/layers/count/exclusive coverage/prefix
checks;29 published/draft sets reference exactly174 valid immutable PNGs;both ZIP
CRC/path allowlists pass. Actual GameStore.start/image/act traverses six stages
for each29 maps using temporary practice scores only. RoundView against complete
custom catalog verifies2 pages25+4 options, all29 names available. No Discord login.

Upload: stop hosted bot and back up clues; replace data/clues with supplied
new-only folder, add data/map_names.json, set catalog override, restart. Preserve
hosted data/portle.sqlite3 and .env credentials. User intentionally discards old
images: existing frozen daily/practice rounds may fail to show their old clues;
new index does not reset stored puzzles or scores. New practice/future daily use
new29-map pool. No remote file deletion/upload or live bot operations performed.

## Scheduled daily / weekly / all-time recaps — 2026-11-17

User approved message formats and explicitly requested implementation. Daily
recap reveals only previous closed day's frozen map name, ranked solves, solve
rate and persistent Play Portle button. Removed promotional lines stay absent.
Monday post combines previous Mon–Sun standings with all-time through that Sunday.
Both are server-participant scoped; practice/other clue-source namespaces excluded.
Times are00:05 daily / Monday00:10 in existing PORTLE_TIMEZONE, checked each minute.
No external scheduler, new dependency or privileged intent. User messages are
suppressed with AllowedMentions.none. Public individual completion posts remain
spoiler-free; AGENTS.md now records the explicit closed-day recap exception.

New portle/announcements.py implements dates, scores, competition ranks1/1/3,
cutoff ties, escaped previous-day answer and bounded continuation embeds/messages.
Daily: fewest clues on successful solves. Weekly/all-time: most wins, then fewest
total clues on wins; exact equal totals share rank, not rounded averages. If two
different exact totals round to identical displayed averages, show totals too.
Zero-attempt opens are not participation; attempted unfinished closed rounds are
unsolved in denominator. No-participant daily skipped. Quiet weeks still show
all-time when history exists. Live /portle leaderboard uses same rank rules,
including current-day solves; personal stats/streaks unchanged.

GameStore adds AnnouncementStore with additive SQLite tables: announcement_config
(server/channel/enabled/enable-time/last error), announcement_batches (namespaced
closed-period frozen message payloads), announcement_pages (atomic per-page send
reservations/status/nonce identity/IDs). Existing player/puzzle data untouched.
First enable/re-enable/channel change begins at next due time. Restart catches
latest eligible daily/weekly only, no old backlog. Snapshots remain fixed. Page
claim rechecks enabled channel and most recent closed period, even after clock
rollover during channel lookup. Two-worker SQLite claims prevent concurrent posts.

New admin-only /portle announcements channel:#games configures one normal server
text channel. Optional enabled:false disables, enabled:true resumes; no options
reports private status, schedule, safe last error, unconfirmed pages. Checks
same-server channel and bot View/Send/Embed permissions. Settings persist per guild;
default is off, no arbitrary channel guessed. Runtime Administrator check, global
Guild Install registration and existing command permission overrides preserved.

PortleClient starts one guarded tasks.loop on ready, waits for ready, skips gateway
disconnects, cancels/awaits task on close. All SQLite/aggregation is off event loop.
Persistent PlayPortleView reuses existing restart-safe button handler. Stable nonce
per page uses SDK2.7.1's enforce_nonce behavior (verified installed http.py and
official Discord Create Message docs). Definite403/404/429 rejection retries after
5min while current; pre-send channel failure remains safe to retry. Ambiguous
network/HTTP errors or crash between HTTP send and DB confirmation retain an
unconfirmed reservation and hold later pages rather than automatically resending.
Status exposes these for manual channel review. Another server's posts continue.
Never claim exactly-once network delivery; Discord nonce uniqueness is recent-only.

Validation: final full121 tests passed in6.267s after the finish-idempotency
guard/test; targeted25 announcement tests also passed. New cases: exact ties/top10 boundary ties/1000 tied
players under UTF16 embed limits, frozen names after roster rename, reset audits,
namespace/server filtering, Sunday/current-day cutoffs, DST, skipped periods,
restart/catch-up/disabled/reconfigured schedules, concurrent prepare/claim/two bot
workers, partial continuation delivery, permission recovery with same nonce,
uncertain/crashed sends, task lifecycle, admin checks/status and paginated private
standings. Stale finish callbacks do not change confirmed delivery records or
diagnostics. Docs: docs/ANNOUNCEMENTS.md, README, Discord/Bisect guides.

No production SQLite/library/.env read or migration during development; only temp
test DBs. No local/hosted bot login, command sync or live messages. Atlas/installed
game/host workers untouched. Existing origin verified github.com/SGLifers/Portle.git,
branch codex/portle. Next: final test/diff checks, redacted credential scan of
tracked/new files, commit milestone, inspect origin divergence and push the source
update under existing user GitHub authorization. Host must update/restart and an
admin select channel; no hosting configuration or channel was set automatically.

### Announcement rollout — final verification, 2026-11-17

Feature committed as afe0c05, Add scheduled daily and weekly leaderboards with
shared ranks. Full121 tests passed in6.267s; whitespace and compile checks passed.
Credential audit of36 tracked files found no Discord/GitHub/cloud credential,
private-key or literal server-setting patterns; only .env.example/data/.gitkeep
are tracked among private-config/data paths. Audited all4 outgoing commits and47
unique blobs too: no credential patterns or private runtime files. Existing
origin/main had0 ahead/3 local doc commits before this feature; no upstream changes
or merge conflicts. git push origin HEAD:main succeeded, advancing main from
1ef6bb4 to afe0c05; local origin/main matched. Only source/docs/tests published.

User activation: update/restart hosted bot (Bisect Git Auto Update if enabled),
wait for readiness/command sync, then a server Administrator runs
/portle announcements channel:#games in each target server. Omit options to see
timezone/delivery status, enabled:false to disable. New config posts starting at
the next due00:05 daily / Monday00:10 weekly, using current PORTLE_TIMEZONE; no
automatic channel choice or immediate historical post. SQLite migrations happen
on hosted startup and retain player data. Keep the existing database/clues/.env.
No remote host restart, live command execution, token access or messages occurred
here. All tests use isolated temporary stores and mocked Discord sends. Atlas and
the user-authored new-only29-map clue package are unchanged by this feature.
No required implementation work remains; handoff is ready for host verification.

## Reset server allowlist — 2026-11-18

User requested that only operator-allowlisted servers can use /portle reset.
Added PORTLE_RESET_GUILD_IDS: private comma-separated positive Discord server
IDs. Empty/unset denies resets in every server; malformed/empty list entries,
wildcards, non-ASCII IDs and out-of-range IDs stop bot/doctor startup before the
player database is opened. Editor ignores bot-only configuration as before.
The CLI passes an immutable allowlist into the command group. Reset checks both
the actual interaction guild and the invoking user's Administrator permission
before deferring or calling reset_daily; callback rechecks Administrator even if
command-level Discord permissions/checks are bypassed. Denial is private without
disclosing the allowlist. Guild registration scope is independent; all other
commands remain usable. Offline doctor reports only the allowlisted server count.

Updated .env.example, README, Discord/Bisect guides, command help and AGENTS.
No configured real IDs, tokens, private data or host settings were read/changed.
No live login, command sync, Discord posts or production score changes occurred.
No schema changes required; shared-score reset audit/replay semantics preserved.

Validation: full126 offline tests passed in6.613s before the final added assertion
that normal daily play remains allowed in denied servers. Added allowlist parser,
startup validation, private denial/no mutation/audit, callback admin/DM checks,
allowlisted reset, doctor ID redaction and unrestricted practice/play coverage.
Final targeted40 Discord tests passed in0.886s with that additional assertion;
git diff --check passed. Fetch confirmed origin/main matches the previous local
HEAD, with no upstream changes to integrate. Deployment uses the new source
commit/code-only ZIP; no local or hosted bot is started during this work.
Hosted activation: update code, set PORTLE_RESET_GUILD_IDS privately (Copy Server
ID, not channel/user ID), restart. Keep DISCORD_GUILD_ID blank for multi-server
commands. Panel environment overrides .env. Empty removes all reset access;
removing one ID and restarting revokes that server. Preserve .env and all data/.

## Cross-server result sharing — 2026-11-18

User approved a completed-board button named exactly **Share results** and a
shortcut, then explicitly renamed the proposed /portle post-result to /portle
share. Implemented /portle share (no arbitrary user/server/channel arguments),
Share results on finished daily boards only, and admin-only /portle results
channel:#games with enabled/status options. Reopening a completed daily in another
server does not post until clicked. Practice, unsolved/previous-day/other-owner
rounds cannot share. The same bot must be installed; both player and bot need
View Channel and Send Messages in the configured destination of the invoking
guild. Bot fetches only its configured destination and verifies actual guild.

New portle/results.py creates additive result_config and server_result_posts
tables. Manual sharing defaults off until server admin selects a text channel.
Configured results channel also receives automatic completions; enabled:false
disables both individual result types, independent of scheduled recaps. Before
any config exists, existing automatic completion behavior stays in the finishing
channel. Per player/puzzle/server atomic claims unify auto/manual sends, survive
restarts, resets and channel changes. Claims recheck ownership/completion/day and
config inside transaction, register server participation, and use stable nonce.
Rows retain destination/message/status/unique attempt token; stale callbacks
cannot alter later attempts. Explicit manual retry only after definite403/404/429
rejection; pending/uncertain sends are held permanently for operator review.
No automatic resends or blind clearing. Posting cannot guarantee exactly-once
delivery across the network. Stable nonce supplements durable reservation.

Legacy result_posts are preserved/read-only for new transport: suppress legacy
automatic replay, but lack destination identity. First explicit share of an
already-posted pre-upgrade daily may duplicate that older post; check channel.
Documented limitation rather than guessing server mappings. New posts track each
server and do not duplicate confirmed results. Reset does not grant another post
in a server that already has a new-format record for that player/day.

Public messages reuse spoiler-free result_message + persistent PlayPortleView;
no screenshot, answer, guesses, raw coordinates or pings. Shared results count
the player in the destination server leaderboard without replaying the puzzle or
adding another win. Private Share results confirmation does not replace the
board. Private buttons still expire15min; /portle play rebuilds them and /portle
share works after restart. Help now uses an embed to fit Discord content limits.
README, Discord/Bisect setup and AGENTS updated with opt-in, disable, permissions,
retry/migration behavior. No live token, settings, library or scores touched.

Validation: full148 tests passed in6.724s, including22 new result tests: actual
manual screenshot daily loss, spoiler/ownership/mode/day guards, no unplayed
round creation, admin config, both permissions, guild isolation, rollover/config
change during lookup, concurrent DB claims/sends, restarts, reset/channel changes,
safe retry/stale completion, pending/uncertain/crash holds, legacy migration and
shared leaderboard participation. git diff --check passed. All Discord sends
mocked and DBs temporary; no local/hosted bot startup, real command sync or posts.

Deployment: publish the new source commit and code-only ZIP, preserving hosted
.env and all data/. Restart, then each participating server admin runs
/portle results channel:#games (separate from /portle announcements). Scores,
clues, expanded roster and reset allowlist stay intact. No new dependencies.

## Drought correction and expanded default roster — 2026-11-19

User corrected Dought to Drought, requested Outskirts, and explicitly requested
the expanded roster as the default. Bundled portle/map_names.json now has30 maps:
the original23, six Simulation entries from the previous29-map host package, and
Outskirts. The six Simulation IDs/names/aliases match that package exactly.
Drought retains MAP_Erosion, accepts Dought/Erosion as compatibility aliases, and
is also the name used by future legacy geometry imports. Outskirts uses
MAP_Outskirts and is available for guesses/editor authoring. No Outskirts scene
export or clue screenshots exist in the current Atlas library; six manually
supplied screenshots must be published before it enters the puzzle rotation.
No substitute images or generated clue fallback were introduced.

Existing puzzle snapshots retain their frozen names/images. Regression checks
cover Dought/Erosion snapshots solved with Drought and both aliases, unchanged
clues, new practice displaying Drought, all six Simulation names in the default,
and Outskirts requiring a published set. Full149 offline tests passed in6.674s;
git diff --check passed. Initial sandboxed suite stalled in async checks and was
interrupted; the approved unsandboxed rerun passed, including local HTTP tests.
No live Discord connection, token/config edit, production database/library write,
Atlas modification, hosted bot operation or asset publication occurred.

The existing PORTLE_CATALOG override still deliberately takes precedence. Hosts
using the prior package's data/map_names.json should remove PORTLE_CATALOG from
both .env and panel environment after updating source, then restart to use the
new bundled default. Preserve all existing data/ and credentials. An optional
updated30-map custom file was prepared under ignored
.local/deploy/portle-maps-2026-11-19/data/map_names.json before the user's default
clarification; it is unnecessary when using the new default. Source-only update
ZIP is .local/deploy/Portle-source-2026-11-19.zip. Changes committed locally;
no GitHub push or host deployment was requested/performed in this turn.

### Dynamic capture counts — 2026-11-19

User superseded the four-wall first-clue rule. The independent Atlas batch
planner now scales every group to map size: reserve one portal per group, then
apportion remaining portals with increasing weights1–6 and largest-remainder
rounding. A30-wall map starts2,50 starts3,447 starts22. Six cumulative screenshots
still end with the whole map. See Atlas handoff for implementation/18 passing
Node tests and29 real map count checks. Updated docs/MANUAL_CLUES.md here only;
Portle still displays the six uploaded images without computing portal counts.
Existing PNG packs retain their old four-first captures until recaptured and
republished. No clue library, player database, settings or hosted bot was changed.

### First-clue minimum clarification — 2026-11-19

User clarified dynamic scaling needs a minimum of four portals first. Atlas now
reserves four per group and allocates the remaining N-24 with increasing1–6
weights.30 walls starts4,50 starts5,447 starts24. This supersedes the prior
one-per-group policy above. Updated MANUAL_CLUES.md; Atlas18 Node tests and all29
available real map count checks pass. Six clues, final full coverage and existing
PNG packs remain as before; using new counts requires recapture/republish. No
library, scores, credentials, bot/host operations or public uploads were made.

## Screenshot regeneration requested — pending browser, 2026-11-19

Latest user request is to regenerate screenshots with the final minimum-four,
dynamic scaling policy.29 maps have Atlas source scenes, so expect174 new PNGs;
Outskirts remains unavailable pending a real source scene. Atlas server was down
and has been started onhttp://127.0.0.1:8741 (exec session93982), API readiness
verified. Current computer-use session has no browsers; creating an iab tab fails
"Browser is not available: iab". User has been asked to connect a browser.
See Atlas handoff for exact tooling diagnosis/settings and pending batch steps.
No new screenshots or data package was created. Keep existing libraries, scores,
.env and previous delivered ZIPs intact. The future new-only export must use
Drought display labels, preserve current29 map IDs and include default30 names;
Outskirts gets no substitute clues. No hosted upload/restart/Discord operation.

## Reported cross-player board visibility — investigated, unconfirmed, 2026-11-19

User supplied two mobile screenshots of a report claiming another player's full
results were temporarily visible. They show the claim and one ordinary public
score summary with Play Portle, but no exposed private board, map answer,
screenshot clue or guess list. Reporter says they dismissed the view themselves;
there is no observed author-dismissal event affecting another player's view.
Treat as an unconfirmed privacy report, not proof of a leak or proof of safety.
Hosted version/live two-account behavior has not been verified.

Reviewed result_message/post_daily_result, show_round, public PlayPortleView and
GameStore.start/_owned. Public result text includes score/squares only. The
persistent public button stores no author's round state; it starts/resumes the
clicking member's own round and defers a separate private response. Board actions
retain per-user ownership. No confirmed application defect or behavior change.

Added test_another_players_score_opens_clickers_board_with_real_sdk_private_response
to tests/test_discord.py. Author finishes with two guesses; fresh and partially
played other members click that author's public score. Actual discord.py2.7.1
InteractionResponse.defer serializer emits callback type5 and flags64, creating
a private reply instead of editing the public source message. Tests check each
member's own guess history, no author's private history or answer in active
embed, unchanged author's saved state and unchanged public message/no channel send.
Only fake HTTP callback return parsing is skipped; network transport is mocked.

.venv/bin/python -m unittest discover -s tests -p 'test_discord.py' -v passed41
tests in1.048s; git diff --check passed. No token lookup, live Discord message,
production data access, host update or behavior change. Next verification needs
two distinct Discord accounts/screens: complete player A, click A's public Play
button as B, and capture whether B actually sees A's unique guesses/score on the
private board. Shared daily clues alone do not distinguish player ownership.
Screenshot regeneration remains pending: rechecked current CUA inventory after
environment change; still no apps/browsers connected. No new captures generated.

## Regenerated dynamic screenshots and upload packages — complete, 2026-11-19

User explicitly authorized local headless capture. Atlas completed29 maps/174
fresh PNGs using its existing UI/Three.js renderer and final minimum-four dynamic
planner. Seed portle-dynamic-min4-2026-11-19,1280x800, random angle per clue,
cumulative growing groups, portals only; geometry/labels/lines/allAngles/cutaway
off.30-wall Simulation Divide starts4,50-wall Faceoff starts5,447-wall Drought
starts24. No Outskirts source scene exists; its30-name roster entry remains
available for guessing/authoring but has no published set and cannot be selected.

Private deliverables (outside Git):
/home/lambchopper67/Downloads/Portle-host-data-dynamic-min4-2026-11-19.zip
(25.17MiB, SHA2566a35e918abbaa95eaad8297db49a14dc6abbfbcb8c38632edb7f4af42fbefc0f)
/home/lambchopper67/Downloads/Portle-screenshots-dynamic-min4-2026-11-19.zip
(25.14MiB;174 named PNGs in29 canonical map folders, including Drought)
/home/lambchopper67/Downloads/Portle-host-data-dynamic-min4-2026-11-19/
contains data/clues, data/map_names.json, screenshots, UPLOAD.txt, VALIDATION.json.
The host ZIP has176 files: index.json,174 hashed PNGs and30-name map_names.json.
Only current/new images are included:0 historical/orphan images and no overlap
with Nov17's prior29-map package hashes. Existing local libraries/exports preserved.

Reproducible ignored package command, from Portle:
PYTHONPATH=. taskset -c 0-3 .venv/bin/python .local/package-dynamic-batch-2026-11-19.py ../PortalAtlas/.local/captures/capture-6463f6f68f0c4de3811de7ed7c87400e.zip
Log .local/package-dynamic-2026-11-19.log. Script refuses existing destinations.
Raw ZIP SHA25632227fca84a350cf8130fff48e85e0907add0ea8f6937b162abeb0a06cf7f532;
capture provenance/command/completion proof are in Atlas handoff.

Validation passed: raw/output ZIP CRC,174 unique decoded1280x800 PNGs/no embedded
metadata/visible portal pixels, exact memberships and cumulative prefix coverage,
groups/camera plans reproduced by current JS planner, first minimum4/scaled
counts, six distinct camera poses per map, all29 source scene hashes unchanged.
Every image normalized/published through ClueLibrary in the isolated output;
draft/published references verified and0orphans. Actual GameStore practice
start/image/act exercised all six stages for each29 maps using temporary DBs.
Default30-name dropdown verified25+5 pages. Largest clue198200bytes, under2MB.
Original authoring-library hashes unchanged. Visual QA inspected unmodified
Divide clue1, Drought clues1/6 and Academy clue6: portal-only captures as intended.
No database, token, source geometry, raw coordinates, capture manifest or lock
file in either upload ZIP. No credentials or production scores were read/changed.

Deployment is manual: stop/back up hosted clues, replace data/clues with supplied
new-only library, preserve hosted data/portle.sqlite3 and .env, restart. Updated
source has30 answers by default; remove PORTLE_CATALOG from .env and panel to use
the bundled default. If retaining a custom override, update it with the matching
included data/map_names.json. Older images are intentionally absent: removing
them can break existing frozen daily/practice images; index replacement does not
reset those saved rounds/scores. New practices/future daily puzzles use new sets.
No hosted upload/restart, live Discord calls, GitHub push or game-host operations.
Screenshot regeneration and packaging are complete; original bot/library intact.

## Source pushed to GitHub — 2026-11-19

User explicitly requested pushing both repositories. Fetched origin/main and
confirmed0 remote-only /6 local-only commits. Audited all16 outgoing source blobs
across those commits: no private runtime paths, asset/image archives, database,
credential-token patterns or private keys. git diff --check passed. Fresh
taskset -c 0-1 .venv/bin/python -m unittest discover -s tests -v passed150 tests
in6.450s; log .local/tests-prepush-2026-11-19.log. Atlas18 Node tests passed too.

git push origin HEAD:main succeeded, advancing SGLifers/Portle main from a6a10e3
to9ea4d78 (Drought/default30 maps, privacy regression and documentation). A final
documentation-only commit records this verified rollout and is pushed as well.
No force push, remote divergence or conflicts. Screenshot/data ZIPs remain local
and need separate upload as documented above. No hosted bot restart, live Discord
connection, production data mutation or game-host operation was performed.

## Confirmed personal-board report and privacy containment — 2026-11-19

User supplied follow-up screenshots showing they explicitly distinguished the
expected public score summary from an unexpected personal board. Reporter
confirmed the latter and that it belonged to the user. Treat this as a credible,
confirmed report of personal-board exposure; the earlier unconfirmed assessment
is superseded. The actual originating interaction/hosted version and transport
mechanism have not been reproduced or established. No original runtime payload
or observer screenshot at the time of exposure is available. Do not claim that
passing tests disproves the report or that a root-cause fix is proven.

Reviewed all board/score paths, GameStore ownership and historical public Play
handler. Existing code consistently requests ephemeral responses, but had no
runtime check of the actual original message's privacy/recipient before edits.
Added verify_private_board: compare actor and round owner, fetch actual original
response, require ephemeral=True and matching user from interaction_metadata (or
legacy interaction metadata). Missing recipient/privacy data, fetch errors or
mismatches withhold the board. Verify before entrypoint starts, guess/skip
mutations, page/clue/projection edits and all board image/embed delivery. SDK
original_response caches its result within each interaction, so repeated guards
reuse one verified response. Existing replay, private ownership, scoring and
public spoiler-free score behavior remain intact. No database migration.

Private board descriptions now identify the player with a mention; mentions are
suppressed as before. on_ready logs and prints `Portle private board verification
enabled` while preserving the hosting startup marker. Safe warning reasons: owner_mismatch,
non_private_response, recipient_unverified, recipient_mismatch and
verification_unavailable; no tokens, IDs, answers, guesses or raw HTTP errors.
AGENTS and Discord troubleshooting document the invariant and two-account retest.

Validation: final full155 tests passed in6.752s via taskset -c 0-3 .venv/bin/python -m
unittest discover -s tests -v; .local/tests-privacy-full-2026-11-19.log. Added
negative cases for public/missing flags, missing/wrong recipient, wrong state
owner, unavailable HTTP/client responses and raw-error redaction. Verify no
render/edit/upload on failure and no turn consumption/view changes across board
controls; test legacy recipient metadata, owner label and overlapping public
Play clicks with distinct completed results. Existing real-SDK defer flag test,
all manual/daily/restart/concurrency/share/announcement tests pass. Whitespace
checks pass. All network sends mocked and player stores temporary.

This is containment and diagnostic hardening; live cause/resolution remains
unverified. Update/restart the hosted bot, confirm its new startup log, reopen
boards with /portle play, then retest A/B with distinct histories and record the
entry control/client/time if any wrong-player board appears. User was asked what
the reporter clicked and whether hosting had restarted since the prior push;
answers were not available during implementation. No credentials, production
scores/library, live Discord messages, hosting configuration or bot process was
accessed/changed. Existing local/GitHub source workflow is used for the patch;
hosting update and live retest remain the operator's action.

Before release, fetched origin/main and confirmed no upstream divergence; audited
all5 changed source/docs/test files for credential patterns/private runtime paths,
and git diff --check passed. Publication uses the user's existing explicit push
authorization via git push origin HEAD:main. Source-only recovery ZIP is ignored
.local/deploy/Portle-privacy-verification-2026-11-19.zip; it contains no data or
credentials, and must preserve hosted .env/data. Do not call this a verified
root-cause resolution until the hosted two-account test confirms isolation.

## Streamlined hosted code updates — 2026-11-19

User described downloading database/clues/.env, doing a clean reinstall, restoring
those files and starting the bot on every code update. Verified current Bisect
Git installation documentation: Auto Update pulls Git changes on server start;
initial repository cloning uses a reinstall. Existing Portle .gitignore excludes
.env and all data files except data/.gitkeep, confirmed with git ls-files.
Routine in-place Git pulls therefore preserve the runtime files. No updater code
or new dependency is needed for an established Git checkout.

Added a Routine code updates section to docs/BISECT_HOSTING.md: one-time repo/main/
Auto Update/BotStartFile settings, verify .git exists, then normal stop/start and
console/readiness/score checks. Retain regular independent backups without moving
data or restoring backups for every code release. Git/authentication failures
need diagnosis; source-only ZIP overwrite is the in-place fallback. Documented
that clue updates remain separate and a custom PORTLE_CATALOG override prevents
bundled roster updates from taking effect. Do not delete data to fix Git pulls.

User confirmed host Auto Update is already enabled. Next is an ordinary stop/start
without reinstall, inspecting the Git output and whether the new startup privacy
marker appears. No failed ordinary update has yet been reported. If it fails,
request only the Git-related console lines to distinguish missing checkout,
wrong branch, authentication or local tracked-file conflicts. Other host settings,
checkout/authentication and actual startup script remain unverified, so no claim
they were configured/tested remotely. No hosted actions,
database/config/asset edits or live Discord messages. Documentation-only change;
git diff --check is the appropriate validation, no application tests repeated.
