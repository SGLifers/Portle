# Host Portle on BisectHosting

Use a Python Discord bot server. The hosted service runs the Discord bot only;
keep Portal Atlas and the clue editor on your own computer. No public website,
reverse proxy or inbound web port is required.

## 1. Install the application code

Stop the hosting server before changing its files. In the Starbase panel's Files
tab, upload and extract the Portle source ZIP, or install the Git repository:

```text
Repository: https://github.com/SGLifers/Portle.git
Branch: main
```

The server root must contain `bot.py`, `requirements.txt`, `portle/` and `data/`.
Avoid an extra enclosing `Portle-main/` directory. Do not upload `.venv`, `.git`,
`.local`, generated geometry catalogs or Portal Atlas exports. The source ZIP
does not contain credentials, screenshots or player progress.

If the repository is private, Git installation needs read access. File upload is
an alternative that does not require a GitHub token on the host. Bisect's Git
installer requires a reinstall before its first clone: do this only on the empty
hosting server, before adding private files. Later reinstalls that delete files
can erase the live database and clue library. Keep Auto Update off during initial
setup and migration.

## 2. Configure Startup

In Settings → Startup, select a **Python 3.12** runtime if available. This is the
version used to test Portle; ask Bisect support if the available image is older.

Set **BotStartFile** to `bot.py`. This new root-level launcher runs the same bot
as `python -m portle bot`; do not choose `portle/bot.py` directly.

Install dependencies from `requirements.txt` using the panel's requirements-file
support. If the panel only offers **Additional Python Packages**, enter:

```text
discord.py==2.7.1 Pillow==13.0.0 python-dotenv==1.2.4
```

The root launcher also accepts `doctor` for an offline check if the panel supports
startup arguments. With a shell, use `python bot.py doctor`. The normal launch
command is `python bot.py`, with no arguments.

## 3. Upload clues and start fresh

To start without previous scores, upload and extract the private
`portle-clues-only.zip` at the hosting server root after the Git installation.
This supplies `data/clues/index.json` and all saved images under
`data/clues/images/`. Do not upload the older database-containing migration ZIP
for a fresh installation.

On first startup, Portle creates `data/portle.sqlite3` with empty scores and a new
installation seed. This can select a different daily map than the local bot.
After launch, preserve this hosted file across updates to retain new scores.
The current bot uses SQLite directly; it does not connect to Bisect's optional
MySQL/PostgreSQL service. Those would require a separate storage implementation.

Stop the local bot before starting the hosted copy, even with a fresh database.
Keep the local editor for authoring clues. Do not delete the local database as
part of this setup. If a database already exists on the host, uploading clues
does not clear it; the fresh-start instructions assume an empty installation.

### Optional migration of old scores

The following path is only for an installation that wants to preserve old scores.

Before the final snapshot, stop the local Discord bot with Ctrl+C and leave it
stopped after moving to Bisect. Running the same bot locally and remotely can
process interactions twice or split scores between two databases. You may keep
the local editor running, but pause uploads/publishing during the snapshot.

Transfer these private paths, preserving their layout:

```text
data/portle.sqlite3
data/clues/index.json
data/clues/images/<all saved PNGs>
```

Use a SQLite backup snapshot for `portle.sqlite3`, including any committed WAL
changes. Do not copy just a live `.sqlite3` file while ignoring its WAL. Transfer
the entire clue library, including older images retained by existing rounds;
copying only the currently published six-image sets is insufficient.

If supplied a separate private data ZIP, upload and extract it at the server root
after installing the source ZIP. It contains player data and clue answers: upload
it only to this private hosting server. Do not commit it or share a download link.
Remove uploaded archive files from the host after successful extraction.

## 4. Configure the existing Discord application

Create a private `.env` file in the hosting server root (or use matching panel
environment variables). Use the existing application token, entered directly in
the panel. No new Discord application or token reset is necessary.

```dotenv
DISCORD_BOT_TOKEN=replace_with_your_existing_bot_token
DISCORD_GUILD_ID=
PORTLE_CLUE_SOURCE=manual
PORTLE_TIMEZONE=America/Los_Angeles
```

Keep the timezone equal to the local installation's configured value so the
daily rollover does not change. Leave the guild restriction blank for all
installed servers. Default relative data locations already match the layout
above; omit local-machine PORTLE_DATABASE/PORTLE_CLUES/PORTLE_CATALOG overrides.
Panel environment variables take precedence over `.env`.

Keep Public Bot enabled for multi-server installation. Portle does not need
privileged intents or Administrator permission for the bot. Keep the existing
server/channel permissions and Discord Interactions Endpoint URL unchanged;
Bisect's generic example bot configuration is not Portle's configuration.

## 5. Start and verify

1. Start the hosted server and watch its console for dependency/startup errors.
2. Confirm it logs successful command registration and bot readiness. The panel
   must not be repeatedly restarting it or reporting out-of-memory exits.
   Portle prints `successfully finished startup` to stdout, with immediate
   flushing, only when Discord dispatches its ready event. This is the exact
   phrase Bisect's panel requires to recognize a completed startup.
3. In Discord, open `/portle stats` (initially empty on a fresh installation), then
   `/portle play` to start the daily. Confirm the clue image loads. If you chose
   the optional database migration, verify old records and daily progress instead.
4. An administrator can use `/portle practice` for a disposable image/control
   check. Practice results remain private. A future daily completion should post
   its score and persistent Play Portle button in the permitted channel.
5. Restart the hosted bot once and verify scores and an existing public Play
   button still work. Keep the local bot stopped.

Monitor memory during simultaneous games before deciding whether to upgrade the
256 MB plan. Storage usage and RAM usage are separate. Keep an independent copy
of the SQLite snapshot and complete clue library, alongside provider backups.

## Later clue updates

Continue using the local editor to capture/publish clues. Transfer new PNGs first,
then replace the remote `data/clues/index.json` only after all referenced files
have arrived. Preserve all older remote PNGs. Do not replace the hosted player
database with the old local database when updating clues: live scores now belong
to the hosted copy. Code updates must also preserve `.env` and the entire `data/`
directory. Start with manual file updates until a dedicated sync workflow exists.

## References

- [Bisect Python/pip startup guide](https://help.bisecthosting.com/hc/en-us/articles/40086898596379-How-to-Install-a-Custom-Discord-Bot-with-the-Pip-Installer)
- [Bisect Git installation guide](https://help.bisecthosting.com/hc/en-us/articles/40086761039387-How-to-Install-a-Custom-Discord-Bot-Using-Github)
