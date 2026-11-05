# Connect Portle to your Discord server

The local game and bot implementation are ready. A live connection needs a Discord
application that you own and a bot token configured on your computer. Keep the
token in a local editor; never paste it into chat, source code, a screenshot or Git.

Before playing, publish at least one six-screenshot set in the local clue editor.
Run `.venv/bin/python -m portle preview --port 8742` and open
http://127.0.0.1:8742/manage. The preview and bot share `data/clues/` by default but
keep separate player progress databases. See [manual clues](MANUAL_CLUES.md).

## 1. Create and install the application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications)
   and create an application named Portle (or your preferred name).
2. In **Bot**, obtain its bot token. Leave **Message Content**, **Server Members**
   and **Presence** privileged intents disabled. Portle uses slash commands,
   interaction buttons and map dropdowns.
3. Configure a **Guild Install** with the `bot` and `applications.commands` scopes.
   Give the bot **View Channels**, **Send Messages**, **Embed Links** and **Attach
   Files** in the channel where you want to play. It does not need Administrator.
4. Open the generated installation URL and select your server using an account
   authorized to install applications there. The channel must allow members to use
   application commands.

Portle receives interactions over Discord's outbound Gateway connection. Leave
the application's **Interactions Endpoint URL** empty. The local preview URL is
only a playtest; it is not a Discord webhook endpoint. No public web server,
tunnel, router port forwarding or separate web hosting is required for the bot.

## 2. Configure this checkout

Run from the Portle directory:

```bash
./setup.sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` locally and replace `DISCORD_BOT_TOKEN` with your bot token. Optional
`DISCORD_GUILD_ID` limits command registration to a development server; enable
Developer Mode in Discord, then copy that server's ID. Leave it blank to register
global commands for all servers where this bot is installed. Avoid switching
between guild and global registration for the same application during launch,
since previously registered commands can remain visible until explicitly removed.

Choose `PORTLE_TIMEZONE` before the first production game. `UTC` gives everyone the
same midnight reset; an IANA value such as `America/Los_Angeles` also works.

```bash
.venv/bin/python -m portle doctor
./run.sh
```

`doctor` reports only whether a token is present and never attempts a connection.
`run.sh` connects, registers the `/portle` command group, and stays running. Global
command changes may take time to appear. The machine must remain awake and online.
Ctrl+C stops the bot safely; restarting resumes daily progress from SQLite.

## 3. Verify in a server

1. Run `/portle help` and `/portle maps`.
2. Open `/portle play`. Confirm **Only you can see this** and a portal clue image.
3. Choose a map from the board's dropdown to immediately submit a guess, or skip
   to unlock the next screenshot. Earlier/Later clue
   controls must revisit revealed images without consuming a guess.
4. As a server administrator, use `/portle practice` for a disposable round.
   Finish it using guesses or skips;
   check that the answer appears and all six screenshots can be viewed at the end.
5. Finish a daily round. Confirm one public score post with colored squares and
   **Play Portle**, with no arena name, guesses or clue image. Practice does not
   auto-post; admins can explicitly use **Share result** for practice scores.
6. Have another member click **Play Portle**. It must open that member's own
   private daily board without changing the public post or anyone else's round.
7. Restart the bot. The public Play button should still work; clicking a result
   on a later day starts that day's daily. Reopening a completed daily does not
   create another automatic result post. Check continuity with `/portle play`.

Clues, guesses and normal game feedback remain private. A finished daily
automatically posts the player's spoiler-free score in its finishing channel.
The explicit Share button and `/portle share` post another public score, also
with Play Portle. Player attribution does not send a mention notification.
Guessing with `/portle guess` always targets the
daily round; use the board's dropdown for practice guesses. The dropdown lists
unguessed names alphabetically, including maps without published clues. Guessed
maps disappear from the current round's dropdown, including after resuming the
daily. New practice starts with the full list. Free Previous/Next maps controls
appear when more than 25 unguessed names remain.

Practice requires the invoking player's **Administrator** server permission.
Members without it receive a private explanation directing them to `/portle play`.
The bot rechecks this permission on existing practice board controls, including
clue review and sharing. Daily play remains available to ordinary members. This
restriction does not require granting the bot Administrator. Discord may still
show the practice subcommand to members; the bot enforces permission before
creating a round. The local browser playtest has no Discord roles.

Administrators can also run `/portle reset player:@member` to clear that member's
current daily score and guesses. It uses the configured local daily date, preserves
earlier days and practice, and reuses today's frozen puzzle. Stats/leaderboards
update immediately. The member reopens with Play Portle or `/portle play`; old
board controls are invalidated. Reset confirmation stays private and does not
ping the member. Previously posted results remain visible. Because daily progress
is shared across this bot's servers, the reset applies to that member's current
daily everywhere. The private database keeps an audit and previous state. This
command requires the player's Administrator permission, not elevated bot access.

Automatic result delivery is reserved in SQLite before sending to prevent duplicate
posts from concurrent/replayed interactions or restarts. A failed or uncertain send
is not retried automatically. The private board and scores remain saved; check
whether the result appeared before using Share result or `/portle share` to retry.
Check **View Channels** and **Send Messages** in the finishing channel if posting
fails; threads also require **Send Messages in Threads**. No extra privileged
intents are required. Old completed rounds are not automatically announced on
startup, and Play buttons require the bot to be online.

If private interactions work but automatic posts fail with **Forbidden**, confirm
the bot account itself appears in the server's member list. An installed app or
registered command does not establish bot membership. Install the same application
using **Add to server / Guild Install** with both `bot` and
`applications.commands` scopes. Then use `/portle share` on the saved result;
failed automatic posts stay reserved to prevent duplicate sends. New diagnostics
include HTTP status and Discord code:50001 points to missing access/membership,
while50013 points to action permissions. Raw HTTP bodies and credentials are
omitted from both private feedback and logs.

## Keep it running

Running `./run.sh` in a persistent terminal is sufficient for local use. For a
permanent host, run the same command under your normal service manager with this
repository as its working directory and a restart-on-failure policy. Keep a single
bot process per SQLite database. This task does not enable a login service or
change the computer's power settings.

Preserve `data/portle.sqlite3` and `.env` when updating code. If copying a stopped
database, ensure there is no uncheckpointed WAL data; SQLite's backup API is the
preferred way to copy a database while it is running. Keep database backups
private because they contain Discord identifiers and the puzzle schedule seed.

## Troubleshooting

- **Token not configured:** replace the example value in local `.env`; environment
  variables take precedence over `.env`. Do not print the token while debugging.
- **Token rejected:** update the token locally using your Developer Portal bot.
- **Commands missing:** check that the bot is installed with both scopes, the guild
  ID matches (if set), command synchronization succeeded, and the channel permits
  application commands. Allow time for global commands to propagate.
- **403 / 50001 Missing Access while starting:** login succeeded, but command
  registration cannot access the configured server. Verify `DISCORD_GUILD_ID` is
  the **server** ID (right-click its icon → Copy Server ID), rather than a channel,
  application or user ID. Check that any shell environment override agrees with
  `.env`. In the Developer Portal, install the same application as a **Guild
  Install / Add to server**, with `bot` and `applications.commands`; **Add to my
  apps** alone is insufficient. Confirm the bot is in that server's member list.
  The startup error provides the matching application's installation link. If
  Discord reports Unknown Guild (10004), the ID may be wrong or the bot may not
  belong to that server. Correct installation/ID and rerun `./run.sh`; changing
  channel permissions or granting Administrator does not fix server membership.
  Offline `doctor` checks configuration presence, not live Discord authorization.
- **Images missing / share fails:** check the four channel permissions above and
  any channel-specific permission overrides.
- **Buttons expired after restart or 15 minutes:** `/portle play` restores the
  daily board. `/portle practice` starts new practice; older practice buttons are
  not restored.
- **No manual clues published:** start the local preview/editor and publish a
  complete six-image set. The bot does not generate fallback clues in manual mode.
- **Missing clue image:** restore the entire clue library from backup, including
  older image files referenced by existing rounds. Keep it with the game database.

Implementation was validated with offline Discord interaction mocks and the local
browser; live Discord image delivery, permission behavior and dropdown responses must
be confirmed after your application is connected.

References: [Discord app setup](https://docs.discord.com/developers/quick-start/getting-started),
[bot authorization](https://docs.discord.com/developers/topics/oauth2#bot-authorization-flow),
[discord.py interaction API](https://discordpy.readthedocs.io/en/stable/interactions/api.html).
