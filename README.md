# Portle

Guess a Splitgate arena from **manually authored screenshot clues**. You capture
six views in Portal Atlas, choose their map answer and reveal order, then Portle
shows the images in a daily or practice guessing game.

## Start

```bash
./setup.sh
.venv/bin/python -m portle preview --port 8742
```

Open **http://127.0.0.1:8742/manage** to choose a map, upload six screenshots and
publish the set. Open **http://127.0.0.1:8742** to play. The library starts empty;
only complete published sets are eligible. No game installation is required for
this manual workflow. Python 3.12+ is recommended; dependencies stay in `.venv`.

See [manual clue guide](docs/MANUAL_CLUES.md) for the full capture/edit/publish
workflow, image limits and backup instructions.

## Capture clues in Portal Atlas

Use the Atlas portal-list checkboxes, **Hide all**, **Show all** or **Only selected**
to choose a visible subset. The **Portals** toggle hides all portal overlays;
**Choose portals for clues** also works on mobile. Uncheck **Labels** and **Lines**
for clean captures. Adjust the camera/cutaway/colors and use **Screenshot** for
each clue. Portle simply displays the images you supply, with no generated portal
selection, image rotation or enforced portal-count progression.

## Game rules

- One daily map shared by players, with private independent progress.
- Six guesses and six screenshots. Each wrong answer or skip unlocks the next clue.
- Review previously revealed images freely. Invalid/repeated map names are free.
- A correct guess or six misses ends the round and unlocks all screenshots.
- Unlimited practice, daily stats/streaks and guild participant leaderboards.
- Explicit, spoiler-free sharing; guesses and clue boards stay private in Discord.

The bundled answer roster contains 23 maps. Only published maps enter the puzzle
rotation, but the full roster remains available for guessing. One ready set is
sufficient to start. Daily resets at midnight `PORTLE_TIMEZONE` (default `UTC`).

## Discord

Follow [Discord setup](docs/DISCORD_SETUP.md) to create/install your application
and configure a token in a local `.env`, then run:

```bash
./run.sh
```

The bot implementation is tested offline. A live Discord connection still requires
your configured application and bot token; never paste the token into chat.

| Command | Behavior |
| --- | --- |
| `/portle play` | Open or resume the private daily |
| `/portle practice` | Start new private practice |
| `/portle guess map_name` | Guess the daily, with autocomplete |
| `/portle maps` | List accepted answers |
| `/portle stats` | Daily results and guess distribution |
| `/portle leaderboard` | Overall daily records of this guild's participants |
| `/portle share` | Post a finished daily score without its answer |
| `/portle help` | Explain the rules |

The board's alphabetical map dropdown works in daily and practice. Selecting a
map in Discord immediately submits that guess; in the browser, select a map then
press **Make a guess**. All accepted names appear, including maps without published
clues. Discord shows Previous/Next maps controls if a custom roster exceeds 25
names; browsing these pages is free. The optional `/portle guess map_name` command
still supports autocomplete. Earlier/Later clue buttons revisit unlocked
screenshots. Share result also supports practice. Controls expire after
15 minutes or a bot restart; `/portle play` restores the daily, while practice
requires starting a new round. No ordinary chat-message reading is needed.

## Data and configuration

`PORTLE_CLUE_SOURCE=manual` is the default. `PORTLE_CLUES` overrides the default
`data/clues/` directory, and `PORTLE_DATABASE` overrides `data/portle.sqlite3`.
The preview always uses `.local/preview.sqlite3`. `PORTLE_CATALOG` optionally
provides a custom names-list JSON instead of `portle/map_names.json`.

Drafts and published sets are separate. A started daily snapshots its six immutable
image hashes, so later edits, republishing, unpublishing and restarts cannot change
that puzzle. Back up the entire clue library and SQLite database together. Images,
progress, Discord identifiers, credentials and local settings are ignored by Git.
The editor is an owner tool for this loopback-only installation; it must not be
exposed as an unauthenticated public authoring service.

The original asset-coordinate generator remains an explicit development/legacy
option: set `PORTLE_CLUE_SOURCE=generated`, then run
`.venv/bin/python -m portle import-assets`. `./setup.sh --source /path/to/scenes`
can still import that legacy catalog. Manual mode never silently uses it.
Legacy generated results are retained and kept separate from manual daily stats.

## Verify

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m portle doctor
```

Doctor reports mode, answer count, published-set count and offline Discord command
schema without connecting or printing the token. Tests cover staged publishing,
image validation/privacy, immutable snapshots, future-clue/owner guards, concurrent
writes/actions, restart/rollover, stats, HTTP and mocked Discord interactions.
Legacy real-asset checks run only when those private inputs are present.

See [handoff notes](docs/HANDOFF.md) for validation evidence and process ownership.
