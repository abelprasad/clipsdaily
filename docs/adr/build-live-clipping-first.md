# Build live clipping first

## Status

Accepted — 2026-11-15

## Context

The pipeline could grow in two directions: live clipping (Twitch, Kick, YouTube Live) and YouTube VOD mode (cutting moments from past YouTube videos, including long-form content). Both were on the table on Nov 15, 2026, and the VOD mode had a real design behind it (the "Clip Brain" method: scrape the latest 100 clips from the biggest podcast short-form accounts, pull the original episodes' full transcripts with timestamps, reverse-engineer moment selection into a Claude skill). Doing both at once would have split the work and shipped neither.

## Decision

Finish live Twitch/Kick/YouTube Live clipping completely before YouTube VOD mode. My order: "first let's add this clipping completely and then we will add youtube". YouTube VOD mode is paused, not built; its design note lives in `docs/youtube-vod-notes.md`. Past-Twitch-VOD batch clipping is a separate, allowed exception: I separately authorized cutting clips from past Twitch VODs on the evening of Nov 15.

## Consequences

- Live mode shipped Nov 15, 2026: record, watch chat for spikes, cut, post, all automatic.
- YouTube VOD work is deferred, not forgotten: the design note and the Clip Brain method are saved for the VOD phase, and I explicitly said "remember this once we add" (live first).
- The VOD batch proved spike-cutting works on past Twitch VODs without opening the YouTube phase: 6 clips cut, 4 live on YouTube the same evening.
- A future ADR supersedes this one when the VOD phase starts.
