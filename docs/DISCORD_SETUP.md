# Connect Portle to your Discord server

The local game and bot implementation are ready. A live connection needs a Discord
application that you own and a bot token configured on your computer. Keep the
token in a local editor; never paste it into chat, source code, a screenshot or Git.

Before playing, publish at least one six-screenshot set in the local clue editor.
Run `.venv/bin/python -m portle editor --port 8742` and open
http://127.0.0.1:8742/manage. The editor and bot share `data/clues/` by default.
The editor has no gameplay or player database. See [manual clues](MANUAL_CLUES.md).

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
the application's **Interactions Endpoint URL** empty. The local editor URL is
for authoring screenshots. No public web server, tunnel, router port forwarding
or separate web hosting is required for the bot.

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

## Multiple servers

Use one running bot and the same Discord application across all servers:

1. In the local `.env`, set `DISCORD_GUILD_ID=`. A nonempty value intentionally
   registers commands only in that one development server. Exported environment
   variables override `.env`; clear any exported guild restriction as well.
2. In the Developer Portal, enable **Guild Install** and **Public Bot** if other
   administrators will install the app. Under Guild Install's default settings,
   request both `bot` and `applications.commands`, plus View Channels, Send
   Messages, Embed Links and Attach Files (permission value52224). A commands-only
   install does not add the bot member needed for automatic result posts.
3. Share a server-install link using this application's ID, with no fixed server:

   ```text
   https://discord.com/oauth2/authorize?client_id=APPLICATION_ID&scope=bot+applications.commands&permissions=52224&integration_type=0
   ```

4. Each administrator opens the link, selects their own server and authorizes the
   installation. Keep the bot online. Global commands work in installed servers;
   the game command group is explicitly unavailable in DMs/user-only installs.
5. Use `.venv/bin/python -m portle doctor` to verify `commandScope` is
   `global: all installed servers`. Restart with `./run.sh` after config/code
   changes; startup syncs globally in this mode. Command updates may need a client
   refresh before appearing.

Each server configures command permissions in Server Settings → Integrations →
Portle. Bot channel permissions still govern public result delivery. Portle's
public/private component buttons do not yet enforce a separate channel allowlist.

All servers share the daily puzzle, configured reset timezone and per-player
progress/statistics. A player can resume the same daily in another server.
Leaderboards include only players who joined gameplay in the current server.
Server administrators can enable scheduled daily results and Monday weekly plus
all-time standings with `/portle announcements channel:#games`; omit options for
private status or use `enabled:false` to disable. The closed daily recap reveals
yesterday's frozen map; individual completion posts and weekly boards do not.
See [schedules, ties and delivery recovery](ANNOUNCEMENTS.md).
Admin reset is limited to operator-allowlisted servers and affects the selected member's shared daily across servers. Keep the
bot token, SQLite files and local authoring editor private; inviting another
server requires none of those files or credentials.

During migration, an old guild-specific `/portle` copy can shadow global updates
in the development server. Preserve any explicit command permission overrides
when migrating/removing that copy; application-level restrictions remain managed
under Integrations. Other app commands must not be bulk-deleted as cleanup.

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
   **Play Portle**, with no arena name, guesses or clue image. Practice results
   stay private.
6. Have another member click **Play Portle**. It must open that member's own
   private daily board without changing the public post or anyone else's round.
7. Restart the bot. The public Play button should still work; clicking a result
   on a later day starts that day's daily. Reopening a completed daily does not
   create another automatic result post. Check continuity with `/portle play`.

Clues, guesses and normal game feedback remain private. A finished daily
automatically posts the player's spoiler-free score in its configured results
channel, or its finishing channel if no results channel has been configured.
Each automatic post includes Play Portle. Player attribution does not send a
mention notification. Completed private daily boards include **Share results**;
`/portle share` is a shortcut for posting in the current server's results channel.
Guessing with `/portle guess` always targets the
daily round; use the board's dropdowns for practice guesses. The **Arena**,
**Simulation** and **Royale** menus list unguessed names alphabetically, including
maps without published clues. Guessed maps disappear from their category,
including after resuming the daily. New practice starts with the full list.
There are no map page controls. Empty categories stay visible but disabled,
and all three menus disable when the round finishes. Custom catalogs currently
classify Simulation IDs by the `MAP_Simulation_` prefix and the six bundled
Royale IDs explicitly; other IDs default to Arena. Each category supports at most
25 remaining names; an oversized custom category produces an explicit error
directing daily players to `/portle guess`, rather than silently hiding answers.

Practice requires the invoking player's **Administrator** server permission.
Members without it receive a private explanation directing them to `/portle play`.
The bot rechecks this permission on existing practice board controls, including
clue review. Daily play remains available to ordinary members. This
restriction does not require granting the bot Administrator. Discord may still
show the practice subcommand to members; the bot enforces permission before
creating a round.

Administrators in operator-allowlisted servers can also run `/portle reset player:@member` to clear that member's
current daily score and guesses. It uses the configured local daily date, preserves
earlier days and practice, and reuses today's frozen puzzle. Stats/leaderboards
update immediately. The member reopens with Play Portle or `/portle play`; old
board controls are invalidated. Reset confirmation stays private and does not
ping the member. Previously posted results remain visible. Because daily progress
is shared across this bot's servers, the reset applies to that member's current
daily everywhere. The private database keeps an audit and previous state. This
command requires the invoking member's Administrator permission, not elevated bot access.

To enable resets, the bot operator sets `PORTLE_RESET_GUILD_IDS` in the hosted
`.env` or panel environment to a comma-separated list of trusted server IDs, then
restarts the bot. With Discord Developer Mode enabled, right-click each trusted
server icon and choose **Copy Server ID**. Use server IDs, not channel/user IDs.
Keep real IDs in private settings, never source control. Leave the setting blank
to disable resets everywhere. Invalid entries stop bot/doctor startup with a
configuration error. The offline doctor reports the count without printing IDs.
Panel environment variables override `.env`; update or clear an existing panel
value when changing the allowlist. Removing a server and restarting revokes its
reset access. No reinstall or database migration is required.

This operator-managed allowlist is independent of `DISCORD_GUILD_ID`; leave that
blank for normal multi-server command registration. Other servers can continue
playing, practicing and configuring announcements. Discord may still display
the reset subcommand there, but the bot denies it privately before changing any
scores. Server administrators cannot grant themselves reset access through
Discord command permission overrides.

Automatic result delivery is reserved in SQLite before sending to prevent duplicate
posts from concurrent/replayed interactions or restarts. A failed or uncertain send
is not retried automatically. The private board and scores remain saved; check
whether the result appeared and ask a server administrator to review bot access
if it is missing. Explicit Share results retries are permitted only for definite
Discord403/404/429 rejection; uncertain or pending sends remain held.
Check **View Channels** and **Send Messages** in the destination channel if posting
fails; threads also require **Send Messages in Threads**. No extra privileged
intents are required. Old completed rounds are not automatically announced on
startup, and Play buttons require the bot to be online.

If private interactions work but automatic posts fail with **Forbidden**, confirm
the bot account itself appears in the server's member list. An installed app or
registered command does not establish bot membership. Install the same application
using **Add to server / Guild Install** with both `bot` and
`applications.commands` scopes. Failed automatic posts stay reserved to prevent
duplicate automatic sends; explicit Share results can retry definite rejection
after access is fixed. New completed daily games use the restored access. Diagnostics
include HTTP status and Discord code:50001 points to missing access/membership,
while50013 points to action permissions. Raw HTTP bodies and credentials are
omitted from both private feedback and logs.

## Sharing results between servers

After updating/restarting the bot, a server Administrator opts in with:

```text
/portle results channel:#games
```

This is separate from scheduled recaps. It selects the text channel for both
automatic completions and manual shares in this server. The bot must be installed
in the server and have View Channel and Send Messages there. Each player sharing
must also be able to view and send in that channel; the bot does not bypass their
destination permissions. Existing servers keep automatic posts in the finishing
channel until they configure a results channel. Manual sharing defaults off.

1. Finish today's daily in any server running this same bot.
2. In another server, use `/portle play` or its public Play Portle button.
3. On your completed private board, press **Share results**.
4. Portle posts your saved score and squares in that server's results channel,
   with a fresh working Play Portle button and no answer/clues/ping. Feedback is
   private. `/portle share` does the same without reopening the board.

Only the player's completed current daily can be shared (including losses),
not practice/unfinished/previous days or another player's result. Sharing also
registers the player for that server's leaderboard, using their shared records.
Opening a completed board alone never posts. Private controls still expire after
15 minutes; reopen with `/portle play` or use `/portle share` after a restart.

`/portle results` privately reports settings. `enabled:false` disables both types
of individual result posts in that server; `enabled:true` resumes the saved channel.
Scheduled recaps remain independent. Changing channel/reenabling does not repost
results already confirmed in that server. Server settings persist in SQLite.

Duplicate protection now keys by player, puzzle (including clue-source namespace)
and server, shared by automatic and manual sends. A reset does not grant another
post that day in the same server. Delivery outcomes are recorded; definite
403/404/429 rejection can be manually retried after fixing access. Pending or
uncertain sends (network interruption, crash after send) are held to avoid
duplicates. Check the channel and ask the bot operator to inspect delivery
records if necessary; do not clear reservations blindly.

Upgrade limitation: older global result-post records contain no server/channel
identity. They are preserved and prevent repeated legacy automatic sends, but
cannot reliably establish which server already received a post. An explicit
first share of a pre-upgrade daily can therefore repeat an older post; check the
channel first. Newly recorded deliveries have per-server duplicate protection.
No scores, clues or credentials need replacing; the new tables are additive.

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

- **Reported visibility of another player's full board:** treat this as a privacy
  incident. Public score/squares messages are expected; screenshots, answer and
  guess history belong to the individual board. Update/restart the hosted bot and
  check its log for `private board verification enabled`. New boards identify
  their player. Board delivery now checks the actual response is ephemeral and
  its interaction recipient matches the player before sending private content.
  Failed/missing verification withholds the board; use `/portle play` to reopen.
  `Private board blocked` logs give a safe reason without tokens, IDs or answers.
  Retest using two separate accounts with different guess histories: B clicks
  Play Portle under A's public score and must see only B's board. Record the
  initiating control, client/platform and timestamp. Passing offline tests or
  requesting ephemeral flags alone does not establish live incident resolution.
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
- **No manual clues published:** start the local clue editor and publish a
  complete six-image set. The bot does not generate fallback clues in manual mode.
- **Missing clue image:** restore the entire clue library from backup, including
  older image files referenced by existing rounds. Keep it with the game database.

Implementation is tested with offline Discord interaction mocks and local editor
HTTP tests; live Discord image delivery, permission behavior and dropdown responses must
be confirmed after your application is connected.

References: [Discord app setup](https://docs.discord.com/developers/quick-start/getting-started),
[bot authorization](https://docs.discord.com/developers/topics/oauth2#bot-authorization-flow),
[discord.py interaction API](https://discordpy.readthedocs.io/en/stable/interactions/api.html).
