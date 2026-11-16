# Label old VOD clips as throwbacks

## Status

Accepted — 2026-11-15

## Context

Clips cut from past VODs are old footage. Viewers and the algorithm treat old footage as stale unless it is framed as a throwback. Abel's style references showed the opposite can be true: an old stream moment (AMP benching Kai for bad 2K performance) doing 695,500 plays. He decided the framing on the spot: label old-VOD clips as throwback.

## Decision

Clips cut from past VODs are labeled throwback in the title and the caption: titles read "THROWBACK: <moment>" and captions lead with "Throwback — <moment>" plus the stream date when known. Old footage is a feature, not a flaw. This applies to VOD clips only, not to the Speed campaign clips.

## Consequences

- Throwback labeling is the durable rule for all VOD clips, in titles and captions.
- The date element was later dropped by the one-line caption decision (see `use-one-line-post-captions.md`): captions are now "Throwback — <streamer>: <moment>" with no date. The `Throwback —` lead is kept.
- The VOD batch proved the framing works: the throwback clips posted Nov 15 (jynxzi checkmate and Worlds final, stableronaldo 40K viewers and Punch-Out) went live on YouTube and Instagram the same evening.
- A future ADR supersedes this one if the throwback framing ever changes.
