# Scheduled Portle recaps

Update and restart the bot, then have a server administrator run:

```text
/portle announcements channel:#games
```

Choose a normal server text channel where Portle has **View Channel**, **Send
Messages** and **Embed Links**. Configuration responses are private. No privileged
Discord intents, extra service, cron job or new dependency is needed.

Each server chooses its own channel; daily progress remains shared across servers.
Standings include only players who have joined Portle gameplay in that server,
using the same participant scope as `/portle leaderboard`. That includes their
shared daily records, wherever they completed those rounds.

## Schedule and messages

Times use the bot's existing `PORTLE_TIMEZONE`, including daylight-saving changes.
The scheduler checks once per minute while connected, so delivery can be up to
about a minute after the scheduled time.

| Post | Time | Coverage |
| --- | --- | --- |
| Daily results | Every day at 00:05 | Previous local day's puzzle |
| Weekly + all-time | Monday at 00:10 | Previous Monday–Sunday; all-time through that Sunday |

The daily embed names the previous puzzle's **frozen map answer**, then lists the
standings and “9 of 12 players solved it.” Only a closed day's map can be
revealed. It never selects or reveals today's answer. Weekly and all-time embeds
show solves and average clues, with no map names, guesses, images or answer data.
The two weekly boards normally share one message. Every message has a persistent
**Play Portle** button that opens the clicking player's private current daily.
User mentions display without notification pings.

The approved messages omit both promotional lines: “A fresh puzzle is ready. Can
you top today's board?” and “New week, fresh leaderboard. Every daily counts!”

## Scores and ties

- **Daily:** successful solves ranked by fewest clues used.
- **Weekly/all-time:** most successful daily solves, then fewest total clues used
  across successful solves. Practice and legacy results from another clue-source
  mode are excluded. Failed guesses/skips that advance the clue count still count
  toward a successful solve's score.
- Identical scores share a competition rank: **1, 1, 3**. Ordering names within a
  tied group does not change their rank.
- Show the top ten positions, including everyone tied at the cutoff. Large ties
  are split into continuation embeds/messages, preserving every eligible player
  and keeping messages within Discord's limits.
- Average clues are rounded for display, not used as a rounded tie breaker. If
  different exact scores round to the same displayed average, the rows also show
  their total clues so the rank difference is visible.

Participation totals count players who made at least one attempt or completed a
daily in that period. Opening a board without playing does not count. Attempted
but unfinished closed rounds count as unsolved; only winners appear in standings.
A day with no participants is skipped. A quiet week's post can still show the
all-time board if the server has historical daily participation. With no daily
history at all, the weekly post is skipped too.

`/portle leaderboard` now uses these same solve/clue tie rules and includes live
current-day solves. Scheduled weekly/all-time boards stop at the closed Sunday.
Ordinary personal streak and win-rate statistics remain available through stats.

## Enable, disable and check status

```text
/portle announcements channel:#games
/portle announcements
/portle announcements enabled:false
/portle announcements enabled:true
```

Selecting a channel enables posts unless `enabled:false` is supplied. Re-enabling
or changing channels starts with the next scheduled post; it does not immediately
publish old results. Running the command without options reports the channel,
timezone, schedule, last delivery issue and any unconfirmed delivery pages.
Settings are per server, and only server administrators can change/view them.

## Restart and delivery behavior

The existing SQLite file gains configuration, frozen message snapshots and
per-page delivery records. No existing scores or puzzle snapshots are rewritten.
Keep the same hosted database across updates; configuration and posting history
live there too. Recaps read saved scores and map metadata, not screenshot files.

After an outage, the scheduler catches up only the latest due daily and weekly
period that falls after announcements were enabled. It does not flood the channel
with a multi-day backlog. Posted snapshots remain fixed across restarts.

Each page is reserved atomically before sending, with a stable Discord nonce.
Confirmed pages are never resent by the scheduler. Definite Discord rejections
(403, 404 or an explicit 429) retry after five minutes while that period remains
current. Fix channel access, then leave the bot running. Channel lookup failures
leave the page unsent and safe to try again.

A lost connection after sending, an ambiguous HTTP failure, or a crash between
send and confirmation can leave an **unconfirmed** reservation. These are held
instead of automatically reposted, because the message may already be visible.
Later pages in that batch are held too, preserving their order. Check the channel
and the private status command before arranging a manual replacement. Delivery
errors never change players' scores or block another server's announcements.

Discord's nonce deduplication covers recent requests only; durable reservations
provide the restart protection. See the [Discord Create Message documentation](https://github.com/discord/discord-api-docs/blob/main/developers/resources/message.mdx#create-message)
for `nonce`/`enforce_nonce` behavior.
