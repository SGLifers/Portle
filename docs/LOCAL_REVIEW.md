# Local reproduction and code review

Reviewed 2026-11-22 against upstream `SGLifers/Portle` commit
`6763f1ac686671ce4a662efd553fb685730a917c` on branch
`codex/local-repro-review`. Publication to `origin/main` was authorized on
2026-11-23. The package includes the Windows compatibility fixes and subsequent
Arena/Simulation/Royale dropdown changes documented in HANDOFF.md.

## Findings

1. **[P2] Unix-only lock import prevents all Windows CLI startup. Fixed locally.**
   Upstream `portle/clues.py:3` imports `fcntl` unconditionally. A fresh Windows
   environment running `python -m portle doctor` raises
   `ModuleNotFoundError: No module named 'fcntl'`; the editor and bot take the
   same import path. The local change uses `msvcrt` byte-range locking on Windows
   and retains `flock` on Unix. Index edits remain atomic and serialized across
   processes. Windows lock acquisition can fail after roughly ten seconds of
   contention; the edit then fails without writing an unlocked index.

2. **[P2] Timezone data is absent from the Windows dependency installation. Fixed locally.**
   `portle/store.py:18` constructs `ZoneInfo(timezone_name)`, but the original
   requirements omit `tzdata`. With the lock import repaired, the fresh Windows
   interpreter raises `ZoneInfoNotFoundError` even for `UTC`. This prevents the
   offline doctor and bot starting. Added Windows-only `tzdata==2026.6` to
   `requirements.txt`. UTC and America/Los_Angeles are exercised by the suite.

3. **[P2] Result destination checks use the parent-channel send permission in threads. Open.**
   `portle/bot.py:104-109` checks `send_messages` for both bot and member, even
   when an automatic completion uses `interaction.channel`, which can be a
   Discord thread. Threads use `send_messages_in_threads`; the installed SDK's
   `Thread.permissions_for` preserves that distinction. A local probe with
   `view_channel=True`, `send_messages=False`, and
   `send_messages_in_threads=True` is incorrectly rejected. Reversing the two
   send flags is accepted and proceeds toward a Discord rejection instead.
   Thus valid thread completions can fail to post, and the preflight does not
   enforce the member's thread send permission. Select the applicable permission
   by channel type for both actors and add thread-specific delivery tests.
   This behavior was left unchanged so the review finding is independently
   actionable. The probe used synthetic permission objects; no Discord send
   was attempted.

## Local reproduction

Python 3.14.7; isolated `.venv`; direct requirements installed in the checkout.
See the Windows setup commands in the root README.

The editor is available at **http://127.0.0.1:8742/manage** and was verified in
the browser with the 30-map roster, six empty screenshot slots and disabled
publish controls. The library intentionally starts empty. Browser gameplay was
removed upstream; gameplay is through Discord. No screenshots were fabricated
or published, and no bot token was configured or searched for.

The detached editor's PID is recorded in `.local/editor.pid`; stdout and stderr
are in `.local/editor.log` and `.local/editor-error.log`. Check process identity
before stopping that PID. Use `start_editor.ps1` to start the editor again after
it stops; it has no hot reload. The offline doctor creates a fresh local player
database; the editor itself does not open it.

## Validation and limits

- Full suite: 157 tests run, OK with 3 private-asset tests skipped (154 passed).
  Log: `.local/tests-windows.log`.
- Added real spawn-process locking checks: four workers preserve all 40 index
  updates; an exception aborts an edit and releases its lock for another process.
- Offline doctor: 30 maps, manual clues, 0 published sets, UTC, no token and no
  network connection attempted.
- `pip check` and `git diff --check` pass.

Review covered the editor, clue storage, catalog, rules, SQLite game state,
Discord interactions/results and scheduled announcements, plus their tests.
The existing suite exercises privacy guards, ownership, stale/replayed actions,
rollover, resets, persistent snapshots and delivery reservations. It produced
some non-failing HTTPError cleanup ResourceWarnings on Python 3.14.
Live Discord privacy/delivery, production migration, private game assets and
the Unix locking branch were not exercised here. Existing offline mocks are
not evidence that a reported live Discord incident is resolved.
