# Portle handoff — in progress, 2026-11-03

User requests a separate Wordle-style Discord game: guess the map from portal
placements, revealing more portals after each failed guess until solved.

Repo: /home/lambchopper67/Documents/ChatGPT/Splitgate/Portle
Branch: codex/portle. PortalAtlas remains independent/read-only.

Implementing: private daily puzzle per player, six guesses, progressive
1/2/4/8/16/all portal clues, SQLite persistence, private Discord slash commands
and buttons, spoiler-free shares, practice, stats and local browser preview.
An optional user question asks daily vs shared-channel vs both; default is daily
unless user steers otherwise. No Discord token was requested or searched for.

Asset input: ../PortalAtlas/data/scenes/MAP_*.json. Import only real enabled
portal walls with provenance. Exclude library features, HangmanR3 zone walls and
Training from the default quiz pool. Private data goes under ignored data/.

No required code or validation is complete yet. Dependencies install in .venv;
logs under .local/. Continue through functional implementation and verification,
then document exact Discord setup and clearly distinguish offline validation
from a live connection, which needs a user-owned bot token.
