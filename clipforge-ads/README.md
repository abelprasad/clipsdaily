# ClipForge Ads — Receipt Reel template (Remotion)

Reusable template for ClipForge promo reels. v1–v5 are the receipt format:
**hook → on-screen bill math → cheaper alternative → comment-keyword CTA**.
v6 is the animated-explainer format (Huzaifa reel structure):
**hook number + rising bar → four-part build → live-vs-VOD mechanism → result screen → comment-keyword CTA**.
Modeled on the @tech.happens ClipIt Studio reel (Dfz6w2PO6oy), with honest
numbers — OpusClip Pro is **$29/mo**, not $19.

- Format: 9:16 vertical, 1080×1920, 30 fps, ~35s (exact length comes from
  the voiceover — see below)
- Free only: Remotion is free for teams of 3 or fewer, system fonts only,
  no paid assets, no paid voice. Renders on indra with local tooling.
- **v3 animation (Nov 16, 2026):** full reel style — an endless-runner background drawn in code (parallax skylines, scrolling ground, runner silhouette, coins, speed lines, all behind a scrim so copy stays legible) plus kinetic text: hook words pop in one at a time with the $49 counting up 0 → 49, receipt rows slide in, the total slams in, the CTA pulses. No ripped footage, no copyrighted assets.
- **v6 explainer (Nov 16, 2026):** full rebuild in the animated-explainer format — hook is a rising cost bar ($29 OpusClip + $20 Claude stacking to $49/mo), build is four named parts (watcher → cutter → ranker → poster, outcome-level names only, no code/paths/internals on screen), mechanism is two timelines (ClipForge posts while live, Opus/Vizard only after the VOD), result is $0 credits burned + 3 real metrics + price. 5 beats, 38.1s, Kokoro af_heart 1.1x, fastest beat 179 wpm (every beat ≤200).
- **v5 pace (Nov 16, 2026):** same ad, faster — Kokoro speed 1.1, Kokoro leading/trailing silence trimmed (0.05s pads, sample-accurate; ffmpeg silenceremove was rejected: its stop side leaves no pad and clips final words), beat tail 0.4s, minSeconds floors lowered; 34.2s total, inter-beat gaps ~0.5s. No script, visual, or CTA change.
- Voiceover: AI voice, never Abel's voice. Kokoro TTS (Kokoro-82M, MIT,
  free, local, offline), voice `af_heart` at speed 1.1,
  loudness-normalized to -17 dB mean. Runs in `.venv-kokoro/`
  (installed once, see Voiceover section).

## Render the current ad

```bash
npm run voiceover   # regenerate narration WAVs + timings (after any script edit)
npm run render      # -> out/receipt-reel-v6.mp4
npm run retention-check   # heuristic pre-post check, -> docs/retention-v6.txt
```

Or directly:

```bash
npx remotion render ReceiptReel out/receipt-reel-v6.mp4 --props=./src/script.json --license-key=free-license
```

## Retention check (pre-post)

Before an ad is posted, run the retention check against the render. It
flags the seconds where a viewer is most likely to bail. Heuristic only:
it measures what ffmpeg can measure and says so. **It does not score the
ad and there is no "out of 100" number** — a calibrated retention score
needs real watch data, and this tool does not invent one.

```bash
npm run retention-check
# or: python3 scripts/retention-check.py [--mp4 ...] [--script ...] [--out ...]
```

What it checks (exit 0 = PASS, 1 = REVIEW, 2 = tool error):

- **Pace** — words per minute of each beat's voice line over its beat
  timing. FLAG over 200 wpm, WARN over 180.
- **Silence** — dead-air gaps of 0.5s or more in the rendered audio, and
  an end tail over 1.0s. (v5 trimmed inter-beat gaps to ~0.5s, so anything
  above that is a regression.)
- **Beat hold** — a beat outlasting its voiceover WAV by over 1.0s.
- **Visual stasis** — picture near-frozen for over 4.0s (mean per-pixel
  delta under 0.5 at 2 fps). Calibrated on v6: slowest animated moment
  measured 1.29, a frozen frame measures 0.0.
- **Hook payoff (estimate)** — when the first money/number word is spoken
  in the hook, assuming words are evenly spaced. An estimate, not a
  measurement; FLAG past 3.0s. If it flags, watch the first 3 seconds by
  eye — the on-screen payoff may land sooner than the spoken one.

What it cannot catch: on-screen layout (empty bands, overlaps, text
collisions), whether a claim is true, whether the hook is interesting, or
anything about the audience. Watch the render once by eye.

Verified Nov 17, 2026: v6 passes everything except one flag — a real
0.55s silence at 21.07s in the mechanism beat (a TTS sentence pause in
`mechanism.wav`, confirmed in the source WAV). The check also caught the
known v5 problem beat r4 at 243 wpm (documented as ~285 wpm by audio
length), and a synthetic 5s frozen end flagged 4.5s of stasis plus a
5.45s end tail. Latest report: `docs/retention-v6.txt`.

## Make a variant — edit ONE file

All script text, prices, and the CTA live in **`src/script.json`**.
A new ad variant = edit that file, then:

```bash
npm run voiceover   # re-generates public/voiceover/*.wav + writes `timings`
npm run render
```

Fields per beat: `text` (on-screen + burned-in caption), `voice` (spoken
line — write numbers out as words, e.g. "forty-nine dollars", never
"$49"), `minSeconds` (shortest the beat can be), `subtext` (CTA only).
`timings` is written by the voiceover script — do not hand-edit it.
Beat length = max(minSeconds, voiceover seconds + 0.4s tail), so narration
and visuals stay in sync. Total runtime = sum of beats.

To render a variant without touching the file, pass props instead:

```bash
npx remotion render ReceiptReel out/variant.mp4 --props=./my-variant.json --license-key=free-license
```

(The props file needs the same shape as `src/script.json`, including
`timings` — generate it with `npm run voiceover` first, or omit `timings`
and beats fall back to `minSeconds` with no audio.)

## Voiceover

- Engine: Kokoro (`.venv-kokoro/`, `kokoro` + `misaki[en]` + spaCy
  `en_core_web_sm`, `espeak-ng` for phonemization), voice `af_heart`,
  `speed` 1.1, `targetMeanDb` -17 (in `script.json` under `voice`).
  Swap the voice by changing `voice.model` and re-running
  `npm run voiceover`. Samples of other voices live in
  `out/voice-samples/`.
- WAVs land in `public/voiceover/<beat-id>.wav` and are mixed in by the
  composition — no manual audio step.
- To add a voiceover file by hand instead: drop a WAV at
  `public/voiceover/<beat-id>.wav` and set that beat's seconds in
  `script.json` under `timings`.
- No ElevenLabs, no paid voice service, no Abel recordings. Ever.

## IP protection — what ads may and may not show

Standing rule (Abel, Nov 16, 2026): nobody steals this. Ads show the
**outcome only** — the dashboard, posted clips, the bill math, the result.
They never show internals:

- No source code on screen, ever.
- No file paths, no terminal output, no config contents.
- No queue internals, no cutter logic, no ranking/spike logic.
- Architecture diagrams are allowed ONLY at outcome level: named stages (Watcher, Cutter, Ranker, Poster) with no code, paths, config, thresholds, weights, or ranking logic. Anything showing how the cutter or ranker works stays out.

Amended Nov 17, 2026 (Abel approved): outcome-level architecture is allowed; the no-internals rule still stands for everything else.
The ads live in the clipsdaily repo under `clipforge-ads/` (public repo,
ClipForge Proprietary License — see `clipforge-ads/LICENSE`). The `voices/`
model and `public/voiceover/` WAVs are gitignored. If a future variant wants an outcome shot (dashboard,
posted clip), use a screenshot or screen recording of the product's
**output** — never a code editor, file tree, or log.

## Captions

Burned-in captions run the whole video (bottom pill, current beat's text).
Ads need them — most viewers watch muted. This is the explicit exception
to the clipsdaily clips rule of no burned-in captions; that rule covers
clips, not ads.

## Layout beats (v2)

| Beat | Time | Content |
| --- | --- | --- |
| Hook | 0–~4s | "Stop paying $49/mo for clips that die in 2 days" |
| Receipt | ~4–~21s | Bill lines appear one by one, then "Total: $49/mo" |
| Alternative | ~21–~34s | ClipForge pitch lines (live, no credits, auto-post, price) |
| CTA | ~34s–end | "Comment CLIPFORGE — I'll DM you the link", held |

## Layout beats (v6)

| Beat | Time | Content |
| --- | --- | --- |
| Hook | 0–~9s | Rising cost bar: OpusClip $29 + Claude $20 stack to $49/mo |
| Build | ~9–~18s | "One setup, four parts": watcher → cutter → ranker → poster |
| Mechanism | ~18–~25s | Two timelines: ClipForge posts while live, Opus/Vizard after the VOD |
| Result | ~25–~35s | $0 credits burned + posts-while-live / 24/7 automatic / $199 or $19–29/mo |
| CTA | ~35s–end | "Comment CLIPFORGE — I'll DM you the link", held |

Prices in v2 (verified Nov 16, 2026): OpusClip Pro $29/mo (300 credits),
Claude Pro $20/mo, 300 credits = 5 hours of video. Re-check vendor pricing
pages before rendering a new variant.

## Files

- `src/script.json` — the ad. Edit this for variants.
- `src/ReceiptReel.tsx` — the composition (layout, beats, captions).
- `src/Composition.tsx` — registers `ReceiptReel` (1080×1920, 30 fps).
- `scripts/generate-voiceover.mjs` — Kokoro narration + timing measurement.
- `scripts/generate-kokoro-voiceover.py` — per-beat Kokoro synthesis +
  loudness normalization (called by the .mjs).
- `scripts/retention-check.py` — pre-post retention check (see above).
  Stdlib only + ffmpeg/ffprobe, no new dependencies.
- `docs/retention-v6.txt` — latest retention-check report for v6.
- `public/voiceover/` — generated narration WAVs (gitignored).
- `voices/` — alternate Piper voice models (gitignored, download only;
  v2 uses Kokoro, kept for voice comparisons).
- `out/` — renders (gitignored).

## License

ClipForge Proprietary License (see `LICENSE`). Licensed, not sold.
No redistribution, resale, or sublicensing.
