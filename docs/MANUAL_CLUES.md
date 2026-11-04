# Author screenshot clues

Portle now uses your manual screenshots by default. It displays each authored clue
in order and does not generate portal arrangements, count visible portals, rotate
images or infer their map answer. Choose the answer when creating a set.

## Capture in Portal Atlas

1. Open http://127.0.0.1:8741 and choose the map.
2. Set the camera, surface colors and cutaway as desired.
3. Use **Hide all**, then the portal-list checkboxes to reveal your first subset.
   **Only selected** keeps just the selected portal. **Show all** restores them.
4. The **Portals** layer toggle hides all overlays temporarily. **Choose portals
   for clues** in the map controls provides the same subset selector, including
   on mobile. Hidden portal IDs are remembered per map in your browser.
5. Uncheck **Labels** and **Lines** if the IDs or route/angle lines should not be
   part of the clue. Geometry visibility is independent.
6. Click **Screenshot**. Repeat for six views, from hardest to clearest. You decide
   what changes between clues; there is no required portal-count progression.

Atlas hides portal overlays/outlines and their labels, not the map's physical
architecture. Visibility does not change the route graph. Atlas's PNG utility
captures the map viewport without the map-title header or side panels; check the
image itself for any visible text that would reveal the answer.

## Upload and publish

Open **http://127.0.0.1:8742/manage** while the Portle preview is running.

1. Choose the map under **Map answer**.
2. Upload a screenshot into each of the six numbered slots. Clue 1 appears first;
   clue 6 is the final chance. Uploads save immediately to a draft.
3. Check the six previews, then click **Publish six clues**. Incomplete sets cannot
   be published or selected for gameplay.
4. Return to Portle and start/resume the daily, or choose Practice. One published
   map is enough to play; publish more sets to build the rotation pool.

Re-upload a slot to replace it in the draft. **Clear clue** removes only that draft
slot. Publish again when the revised six-image set is ready. **Remove from future
puzzles** reversibly removes a map from selection; it does not invalidate existing
rounds. Republishing a complete draft enables that map again.

The current day's first manual puzzle is shared by all players on the installation
and stays frozen. A newly published map or revised set affects future puzzles and
new practice rounds, not the already-started daily. Existing rounds retain their
original six image hashes and still work after editing/unpublishing.

## Player behavior

- Six guesses. Each miss or skip unlocks the next screenshot.
- Earlier/later arrows review only already-revealed images without spending a guess.
- A win or six misses ends the round, reveals the map name and unlocks all six images.
- Invalid/repeated names remain free. Practice does not affect daily records.
- Browser and Discord use exactly the same normalized screenshot bytes, with a
  generic attachment filename. Manual clues have no artificial top/isometric switch.

Daily resets still use `PORTLE_TIMEZONE` (UTC by default). Manual daily rounds and
stats use their own namespace. Legacy generated rounds remain in the database and
are not counted in manual-mode stats.

## Image handling and privacy

PNG, JPEG and WebP still images are supported. Upload and normalized PNG output
must each fit within 8 MiB. Images are limited to 24 megapixels and 8192 pixels on
either side. Animated images and unsupported formats are rejected.

The server decodes the screenshot, applies its EXIF orientation, and saves a PNG
with no embedded metadata. It does not scale, crop, annotate or synthesize image
content. File names are not retained. Images are stored by a content hash; visible
map names or other spoilers inside the pixels are the author's responsibility.

The clue editor is an owner tool on the loopback-only local server. Editor writes
require a same-origin request and a per-process editor token. Anyone with access
to this local authoring installation can open the editor; this is not a public
multi-user admin/authentication system. Discord players receive only private round
images, without the editor or library URLs. Do not expose port 8742 publicly.

## Storage and backup

The default library is ignored `data/clues/`: `index.json` holds drafts and
published sets; `images/<hash>.png` contains immutable files. `PORTLE_CLUES` can
override the directory. Keep the entire library together with the game database
when backing up or moving the bot. Do not delete old image files: saved rounds may
still reference them. Tampered or missing files are detected when read.

Library writes are locked across processes and publish index changes atomically.
The browser editor and bot can share the same library on this computer. The bot
sees newly published sets on the next new puzzle without a restart. Browser
progress and Discord progress remain separate databases.

`PORTLE_CLUE_SOURCE=manual` is the default and needs only the bundled names roster.
No game archives, geometry catalog or Portal Atlas process is required to play
uploaded images. The old generator remains available only by explicitly setting
`PORTLE_CLUE_SOURCE=generated` and importing its geometry catalog. Manual mode
never falls back to generated clues when its library is empty.
