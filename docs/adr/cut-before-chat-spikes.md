# Cut before chat spikes

## Status

Accepted — 2026-11-15

## Context

The hard part of clipping is choosing the moment, not cutting or captioning it. Chat spikes mark moments, but a spike's peak usually comes after the moment happened: chat reacts to what it just saw. Cutting exactly at the spike would start the clip after the good part. The style references Abel sent the same day also showed that very short clips win: 5-second and 10-second moments doing 4.6M and 1.6M plays.

## Decision

Cut window is -20s/+10s around a chat spike (30s total) and rank clips by spike intensity. TikTok variants are 60-90s (the minimum to get paid under Creator Rewards), a single extended moment preferred, otherwise the top 3 spikes stitched. A short variant of 5-15s for a single moment is under consideration for TikTok and Reels, keeping 30s for Shorts.

## Consequences

- The reveal lands about 5 seconds into a 30s cut, instead of at the end.
- Chat spikes can mislabel the moment: the jynxzi 2075s cut first inferred the hook "JYNXZI REACTS TO THE WORLDS TEASER" from chat, but the frame check showed the real moment was a chess win by checkmate ("You Won! By Checkmate"). The spike-frame check before posting catches this.
- The highest spikes are not always the best moments: the two biggest spikes in the Speed Expedia VOD (3:03:50 and 3:04:10) were just the stream ending, with zero Expedia content, and were avoided.
- Open improvement: the runner's clips currently ship hook-less when no hook is supplied (`hook=None` default); the queue path derives the hook, the live path does not yet.
