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

Discord daily completion now automatically posts a spoiler-free score with a
persistent Play Portle button. Practice is Administrator-only and stays private.
There is no Discord share button/command or screenshot-source footer. Keep public
result messages free of answers and clues.
The admin-only /portle reset command resets one member's current daily progress,
retains a private audit/previous state and invalidates old board IDs. Preserve
earlier daily history, practice rounds and replay protection when changing this.

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
