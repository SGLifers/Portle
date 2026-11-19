# Portle

Read docs/HANDOFF.md before continuing. This is a separate Discord game using
manually authored screenshot clues. The user explicitly authorized matching Portal
Atlas visibility controls for capturing these clues. Keep the repositories separate.
Never change the game installation, SplitgateHost, or its workers. Do not launch the game.

Keep credentials, Discord IDs, SQLite progress and extracted game data out of Git. Never
print a Discord bot token or require it to be pasted into chat. Live Discord
connection requires a user-configured local bot token; do not search for one.

The user now supplies the clue screenshots manually, captured using Portal Atlas.
Default gameplay must expose only published manual sets; do not fabricate clues or
silently substitute the legacy generated renderer. Keep answers, map IDs,
raw coordinates and revealing filenames out of unsolved clue payloads. Share
results without spoilers. Validate turn limits, restart persistence, concurrent
interaction handling, private game ownership and daily rollover with tests.

Before board edits/attachments or board actions that consume a turn, verify the
actual original Discord response is ephemeral and its interaction recipient
matches the actor/round owner. Missing privacy/recipient metadata or failed
verification must withhold the board. Keep privacy diagnostics free of answers,
guesses, interaction tokens and Discord IDs. Do not treat requested flags alone
as proof of actual destination privacy or passing mocks as live incident closure.

Discord daily completion now automatically posts a spoiler-free score with a
persistent Play Portle button. Practice is Administrator-only and stays private.
Completed daily boards now include Share results; /portle share posts the same
saved result in the invoking server's admin-configured /portle results channel.
Keep practice private and public result messages free of answers and clues.
Sharing requires bot/member View Channel + Send Messages in that same server's
destination. Reserve per user/puzzle/server across automatic/manual sends, resets
and restarts; only explicit retries of definite Discord rejection may resend.
Never automatically resend pending/uncertain deliveries. Keep legacy global
post records intact; they lack server IDs and cannot be backfilled reliably.
There is no screenshot-source footer.
Scheduled closed-day recaps are an explicit user-approved exception: they name
only the previous puzzle's frozen map after that day has ended. Weekly/all-time
recaps and individual completion posts remain free of map answers and clues.
Keep announcement settings/delivery records server-scoped and persistent. Do not
post or requeue uncertain deliveries automatically after a restart.
The admin-only /portle reset command resets one member's current daily progress,
retains a private audit/previous state and invalidates old board IDs. Preserve
earlier daily history, practice rounds and replay protection when changing this.
Reset also requires the invoking server in the operator's PORTLE_RESET_GUILD_IDS
allowlist. Empty/unset denies all resets; invalid configuration blocks startup.
Keep the allowlist independent of command registration and normal gameplay.

Multi-server use registers commands globally with DISCORD_GUILD_ID blank. Commands
support Guild Install/server channels only. One shared puzzle/library and per-user
daily progress serve all servers; leaderboards filter server participants. Preserve
server command permission overrides when touching legacy development registrations.

Commit milestones and keep handoff documentation current. At most four CPUs.
Do not publish the game or proprietary assets as part of local development.

Browser gameplay has been removed. The `editor` CLI serves only the local clue
authoring UI at / and /manage; it must not open a player database or expose
gameplay endpoints. Discord is the player interface. Preserve existing private
clue libraries, Discord progress and unused historical browser databases.
