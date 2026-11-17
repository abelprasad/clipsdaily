# Seed famous clips from top Twitch clips

## Status

Accepted. 2026-11-17.

## Context

The queue was nearly all throwbacks: the maintainer cut chat-spike
moments from old VODs, and the 28 pending entries were all throwbacks
with only 2 live clips. Abel's direction was "don't just do throwbacks,
it should be famous clips" — the clips posted should be moments people
already know, not random slices of old streams. The throwback source
ranks moments by chat intensity, which finds loud moments but says
nothing about whether anyone outside that stream remembers them.

## Decision

Add a second queue source in `queue_seed.py`: each watchlist Twitch
channel's top clips by view count, fetched via the existing Twitch GQL
path with the same client ID. Verified live: the GQL `ClipsSort` enum
has no `VIEWS` value, and `TRENDING` returns recent low-view clips —
but no sort criteria at all returns clips in views-descending order.
Round-robin across the 8 Twitch channels, top 30 per channel per fetch,
6h cache. Download via TwitchDownloaderCLI `clipdownload`, cut 30s +
TikTok variant with the current cutter framing. The clip title doubles
as the on-screen hook (no Whisper run). TikTok variant only for clips
>= 110s. Famous entries carry `source: "famous"`, `views`, `clip_slug`,
insert at the front of the pending queue (the FIFO poster picks one
next with no poster change), and the maintainer keeps >= 8 famous
pending. Throwbacks keep running behind them — famous mixes in, it does
not replace throwbacks. The Speed Expedia campaign exclusion extends to
famous clips (iShowSpeed clips from 2026-11-06 or Expedia-titled are
skipped; GQL clips carry no source-VOD id, so date + title is the
guard). Manual run: `python3 queue_seed.py --seed-famous N`.

## Consequences

- The queue's front is now recognizable moments (first batch: jynxzi
  "kiss on the lips" 2.3M views, kaicenat "Kevin Hart gets drenched"
  2.7M views, and 6 more), which is what Abel asked for.
- Supply is bounded: top 30 per channel is ~240 clips, ~5 days at full
  post rate; when exhausted the queue falls back to throwbacks until new
  clips crack the top 30. Raising `FAMOUS_PER_FETCH` extends it.
- Famous clips are the easiest content for Instagram to match to the
  original. On Nov 17, 2026 — the same day this source shipped —
  Instagram flagged `@clippedaily31` for unoriginal content. The
  famous-clips source likely accelerated the flag (see ADR 018 and
  `docs/RESTART.md`). A restart must not treat famous clips as safe
  content for Instagram; they need the same transformation as any
  repost.
- `TDCLI clipdownload` is flaky per clip (slug and full-URL forms can
  fail with a parser error before the fallback succeeds); cuts take
  40s–3min each.
