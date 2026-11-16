# Use one-line post captions

## Status

Accepted — 2026-11-15

## Context

Post captions had grown long: a throwback line with a date, the moment phrase, a `clipsdaily • <streamer>` credit line, three or four hashtags (`#clipsdaily #throwback #<streamer> #twitchclips`), and a boilerplate closing line ("Best stream moments, clipped daily. Credit to the streamer in every post."). Abel asked to cut the captions down more and whether hashtags help.

## Decision

Post captions are one line, the same on YouTube, TikTok, and Instagram. Regular clips: `Throwback — <streamer>: <moment>`. Live (non-throwback) clips: `clipsdaily • <streamer>`. No hashtags except campaign-required ones, no boilerplate, no date. Campaign clips keep the money line plus the brand, the destination, and the one required hashtag, and nothing else (for example: "You're going to Japan Expedia #IShowSpeed"). Titles are unchanged.

## Consequences

- Shorter captions read better on mobile, where most views happen.
- Streamer credit is carried by the name in the line itself, plus the burned-in `clipsdaily • <streamer>` overlay on the video.
- Hashtags don't drive reach (2026 consensus: categorization only). Instagram's head has said they don't drive reach, TikTok's For You runs on watch time and saves/shares, and Shorts hashtags aren't a ranking factor. Dropping the generic tags (`#throwback`, `#clipsdaily`, `#twitch`) loses nothing.
- Campaign captions still pass the eligibility gate: the required mention, hashtag, and destination are all present in every caption field, verified by `eligibility_gate.py`.
- This supersedes the multi-line caption format and the date element of the throwback rule (see `label-old-vod-clips-as-throwbacks.md`); the `Throwback —` lead is kept.
