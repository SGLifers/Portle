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

Commit milestones and keep handoff documentation current. At most four CPUs.
Do not publish the game or proprietary assets as part of local development.
