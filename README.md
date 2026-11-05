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
- Unlimited admin practice in Discord, daily stats/streaks and guild participant leaderboards.
- Daily results post automatically with a Play Portle button; guesses and clue boards stay private.

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

Portle supports installation in multiple Discord servers with one running bot,
token and clue library. Leave `DISCORD_GUILD_ID` blank for global command
registration; a populated value is only for single-server development. The
offline doctor reports which mode is configured. Each server administrator adds
the same application using Guild Install with `bot` + `applications.commands`.
The application must have Public Bot enabled for other administrators to install
it. See [multi-server setup](docs/DISCORD_SETUP.md#multiple-servers).

The daily puzzle and each player's daily progress/stats are shared across servers.
Leaderboards list only players who have used Portle in that server. Server admins
control their server's command permissions, while practice/reset keep their
runtime Administrator checks. The screenshot editor remains local to the owner;
server administrators do not need the bot token or access to the editor.

| Command | Behavior |
| --- | --- |
| `/portle play` | Open or resume the private daily |
| `/portle practice` | Administrators only: start new private practice |
| `/portle reset player:@member` | Administrators only: reset that member's current daily score and guesses |
| `/portle guess map_name` | Guess the daily, with autocomplete |
| `/portle maps` | List accepted answers |
| `/portle stats` | Daily results and guess distribution |
| `/portle leaderboard` | Overall daily records of this guild's participants |
| `/portle help` | Explain the rules |

The board's alphabetical map dropdown works in daily and practice. Selecting a
map in Discord immediately submits that guess; in the browser, select a map then
press **Make a guess**. Already-guessed maps are removed from the Discord dropdown;
the browser disables them and labels them **already guessed**. This follows the
current round's saved history and resets for new practice rounds. All other
accepted names remain available, including maps without published clues.
Discord shows Previous/Next maps controls if more than 25 unguessed names remain;
browsing these pages is free. The optional `/portle guess map_name` command
still supports autocomplete. Earlier/Later clue buttons revisit unlocked
screenshots. Private board controls expire after
15 minutes or a bot restart; `/portle play` restores the daily, while practice
requires starting a new round. No ordinary chat-message reading is needed.

Discord practice requires the player's **Administrator** server permission; a
role name alone does not grant access. Both the command and practice board
controls check current permissions. Members can still play the daily puzzle, and
denied practice requests respond privately. The loopback browser preview remains
an owner playtest/editor without Discord accounts or roles.

Admins can use `/portle reset player:@member` to give a server member another
attempt at today's same puzzle. It removes today's result from their stats and
leaderboard, clears their guesses and starts them again at clue1. Earlier daily
history and practice rounds are preserved. The date follows `PORTLE_TIMEZONE`.
Daily progress is shared across servers, so this reset applies to that player's
current daily everywhere this bot runs. Confirmation is private, and old public
result posts remain visible. The player must reopen with Play Portle or
`/portle play`; their previous board stops working. A private SQLite audit retains
the previous state and admin identity. Repeated delivery of the same reset does
not erase a later attempt. Resetting someone with no current progress is a no-op.

Finishing a daily puzzle (win or loss) automatically posts your score and colored
squares in the channel where you finished. The post identifies the player without
pinging them and contains no answer, guesses or clue images. **Play Portle** on
the post opens or resumes the clicking player's own private daily puzzle, without
a slash command. This public button survives bot restarts and always opens
today's puzzle, even on older posts. The bot must be running for buttons to work.
Practice results stay private.

Automatic posts are reserved in SQLite to prevent duplicates from replayed or
concurrent interactions and restarts. Reopening completed boards does not post
again or backfill older results. If a send fails or its outcome is uncertain, the
bot preserves the game and gives private guidance to check the channel and the
bot's access. Interrupted sends are not automatically retried, to avoid duplicate
public messages. There is no manual Discord share button or command.

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
