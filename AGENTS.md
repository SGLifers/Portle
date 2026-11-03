# Portle

Read docs/HANDOFF.md before continuing. This is a separate Discord game using
portal-wall data imported read-only from ../PortalAtlas. Never change the atlas,
game installation, SplitgateHost, or its workers. Do not launch the game.

Keep credentials, IDs, SQLite progress and extracted game data out of Git. Never
print a Discord bot token or require it to be pasted into chat. Live Discord
connection requires a user-configured local bot token; do not search for one.

Clues must derive from real portal placements. Generated PNGs are visualizations
of asset coordinates, not screenshots used as map inputs. Keep answers, map IDs,
raw coordinates and revealing filenames out of unsolved clue payloads. Share
results without spoilers. Validate turn limits, restart persistence, concurrent
interaction handling, private game ownership and daily rollover with tests.

Commit milestones and keep handoff documentation current. At most four CPUs.
Do not publish the game or proprietary assets as part of local development.
