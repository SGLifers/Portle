# Portle

Guess a Splitgate arena from its portal placements. Six guesses; each miss
reveals more portal walls. A separate Discord game powered by the real asset
coordinates extracted by Portal Atlas.

## Play

- One shared daily arena, with private progress for each Discord player.
- Six guesses. Clues reveal **1 → 2 → 4 → 8 → 16 → all** portal placements.
- A wrong answer or skip consumes a guess. Invalid/repeated answers are free.
- Switch between isometric and top views without spending a guess.
- Unlimited practice, daily statistics, streaks and server leaderboards.
- Explicit, spoiler-free result sharing; clue boards and guesses stay private.

The current local catalog contains **23 maps and 3,366 portal placements**.
Every visible portal comes from the imported game assets, with its real position,
orientation, shape and dimensions. Clues contain no map textures or screenshots.
Both views use the same revealed portals and a consistent full-map frame.

## Run locally

Python 3.12+ is recommended. From this directory:

```bash
./setup.sh
.venv/bin/python -m portle preview --port 8742
```

Open **http://127.0.0.1:8742** for the playable browser preview. It uses the same
rules and clue renderer as Discord, and a separate database. A browser cookie
identifies your local preview player. Keep that cookie to retain daily progress.
The preview only listens on loopback and is intended for this computer.

`setup.sh` installs dependencies into `.venv` and imports the existing Atlas
scene exports. To use a different source:

```bash
./setup.sh --source /absolute/path/to/PortalAtlas/data/scenes
```

On a machine with multiple Python installations, set `PORTLE_PYTHON` when first
running setup. The importer reads source files without changing them. It excludes
training, creative libraries and the shared HangmanR3 zone. Extracted data,
generated clues, databases, virtual environments and credentials are ignored by Git.

## Run in Discord

Follow [Discord setup](docs/DISCORD_SETUP.md) to create your bot, install it in a
server, and place its token in a local `.env`. Then:

```bash
./run.sh
```

Use `/portle play` in the server. No Discord account credentials are included in
this repository. The bot has been tested offline; a live Discord session still
requires your configured application and token.

| Command | Behavior |
| --- | --- |
| `/portle play` | Open or resume today's private round |
| `/portle practice` | Start a fresh private practice round |
| `/portle guess map_name` | Guess the daily arena, with autocomplete |
| `/portle maps` | List accepted map names |
| `/portle stats` | Your daily results and guess distribution |
| `/portle leaderboard` | Daily records of players who joined in this server |
| `/portle share` | Post your finished daily score publicly without its answer |
| `/portle help` | Explain the rules |

The board's **Guess map** button works for daily and practice. **Share result**
also supports practice. Each board has a 15-minute button lifetime; reopen the
daily using `/portle play`. An expired practice board requires a new practice
round. The bot does not read ordinary chat messages.

## Persistence and configuration

Daily puzzles reset at midnight in `PORTLE_TIMEZONE` (default `UTC`). Everyone on
one bot installation receives the same map and portal order each day. Each player
has one daily round across servers. Leaderboards include participants in that
server and show their overall daily records. Practice never changes these records.

The installation's private seed shuffles the catalog into a repeating cycle that
uses every map before repeating. Portal selection starts at a seeded real portal
and adds distant placements to spread later clues across the arena. Different bot
installations have independent schedules. Each started daily puzzle is frozen in
SQLite, so a restart or later asset import cannot change that day's saved puzzle.

`PORTLE_CATALOG` and `PORTLE_DATABASE` optionally override the default paths
`data/catalog.json` and `data/portle.sqlite3`. Browser preview progress always uses
`.local/preview.sqlite3`. SQLite stores player/server IDs, guesses, daily snapshots
and the private schedule seed. Back up the production database while the bot is
stopped, or use SQLite's backup facility; retain the seed to retain the schedule.
Changing the timezone or replacing the catalog can alter future puzzles, so choose
these before launch.

## Verification and maintenance

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m portle doctor
.venv/bin/python -m portle render-sample --stage 5 --view iso
```

`doctor` validates local loading and command registration without connecting to
Discord or printing the token. `render-sample` writes `.local/sample.png`.
The test suite checks rules, persistence, private ownership, concurrent/replayed
actions, daily rollover, anonymous clue payloads, HTTP handling and mocked Discord
interactions. When local assets are present, it also verifies all imported portal
values and renders both views for every map. Real-asset tests skip when their
private inputs are absent.

See [handoff notes](docs/HANDOFF.md) for architecture, validation evidence, process
ownership and remaining live deployment checks. Portle is independent of Portal
Atlas and does not start or modify the game installation or extraction workers.
