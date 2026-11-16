# Captions, hooks, and framing — the standing rules (Nov 15, 2026)

These rules were set by Abel across Nov 15, 2026. They supersede
everything earlier (the launch-day README's "Whisper captions
burned in" and "crops to vertical" are both stale). Do not change
them without his go.

## Post captions — one line, no hashtags

Same one-liner on YouTube, TikTok, and Instagram.

Regular clips (live + VOD throwbacks):

```
Throwback — <streamer>: <moment>
```

- Example: `Throwback — ishowspeed: gonna be back streaming Skiiiiit`
- Live clips (not from a VOD) use the same line without
  "Throwback" when the moment is live; the queue builder
  (`queue_seed.py:build_texts`) always writes the throwback form
  because the queue is VOD-seeded. The live runner
  (`poster.py:_caption`) writes `clipsdaily • <streamer>`.
- No boilerplate closing line ("Best stream moments, clipped
  daily. Credit to the streamer in every post." — removed Nov 15).
- No date in the caption. No hashtags.

Campaign clips (one hashtag — the required one, nothing else):

```
<money line> <brand> <destination> #IShowSpeed
```

- Example Japan: `You're going to Japan Expedia #IShowSpeed`
- Example Hong Kong: `Expedia is giving you 10 thousand dollars Hong Kong #IShowSpeed`
- Built by `campaign_cut.py:build_campaign_texts`: the brand,
  destination, and required mentions are appended only if the
  money line doesn't already name them, so the gate's caption
  check still passes with no redundant words.
- The campaign hashtag is required by the campaign, not by the
  algorithm. It stays even though hashtags don't drive reach.

Titles are NOT captions and are unchanged:

```
THROWBACK: <streamer> — <moment> | clipsdaily #shorts
```

## Why no hashtags

2026 consensus across platform guidance: hashtags stopped being
a reach lever on every major app. They are a categorization
signal now. Instagram's head has said plainly they don't drive
reach; TikTok's For You runs on watch time, saves, and shares;
YouTube Shorts hashtags are not a ranking factor. Generic tags
(`#throwback`, `#clipsdaily`, `#twitch`, `#twitchclips`) carry
no signal — the algorithm already infers the topic from the
caption keywords, the spoken audio, and the on-screen text.
A few precise tags don't hurt, but ours were pure noise, so
they were cut. Keep at most the tags a campaign requires.

## Hook overlay — one big line, start only

- One big hook line at the START of the clip only (first ~3s),
  big bold centered text. Example: `SPEED GAVE HIM $10,000!`
- Position: **y=300** on the 1080x1920 canvas (moved down from
  y=150 on Nov 15 to clear the platform top UI). Entrance:
  250ms ease-out-expo slide+fade in, hold, 170ms ease-in fade
  out (motion-design skill, LottieFiles Energetic archetype).
  Box removed so the fade applies to the whole hook.
- The hook is generated automatically per clip from the moment
  (transcript money line / spike context) inside the cutter.
  A garbled transcript line must never become a hook
  (`cutter.py:_make_hook` only accepts lines containing a hook
  word; chat spikes can mislabel the moment, so the spike-frame
  check is the backstop).
- **No burned-in word captions, ever.** Whisper may run
  internally to find the moment; nothing burns in except the
  hook. (The launch-day word captions were removed Nov 15:
  they were enormous, covered faces, and mistranscribed
  "Hong Kong" as "home call".)
- Credit overlay: `clipsdaily • <streamer>`, small, top-left
  (y=20). It is separate from the hook.

## Framing — full frame, never crop

- Every clip is 1080x1920: the whole 16:9 source frame scaled
  to fit width (1080x608), centered, top/bottom filled with a
  blurred, darkened copy of the same video. Nothing is cut off
  the sides. This applies to the queue, the runner, VOD batches,
  and campaign cuts. Already-posted cropped clips stay as-is;
  do not re-post duplicates to fix them.
- The gate proves it (`eligibility_gate.py`, band energies on
  frames at t=5/15/25s): PASS only if top (rows 150–550) < 0.4
  AND bottom (rows 1400–1800) < 1.0 AND center (rows 800–1200)
  > 2.0. Calibrated Nov 15–16, 2026: true blur-fill scores
  top ~0.03–0.08, bottom ~0.5–0.6, center ~4.6; center-crop
  scores top ~1.6–2.3, bottom ~3.2–6.7. The first version used
  a top-vs-center ratio and FALSE-PASSED a center-crop clip;
  absolute band energies are the fix. Re-validate against both
  ground truths if `cutter.py`'s filter chain ever changes.

## Lengths

- YouTube Shorts + Instagram Reels: 30s (20s before the spike,
  10s after — chat reacts after the moment).
- TikTok: 60–90s, target 75s. Creator Rewards only pays for
  clips over 60 seconds. Single extended moment preferred; else
  stitch the top 3 spikes. `poster.py` refuses any file under
  60s for TikTok.
