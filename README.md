# ClipForge Ads — Receipt Reel template (Remotion)

Reusable template for ClipForge promo reels in the receipt format:
**hook → on-screen bill math → cheaper alternative → comment-keyword CTA**.
Modeled on the @tech.happens ClipIt Studio reel (Dfz6w2PO6oy), with honest
numbers — OpusClip Pro is **$29/mo**, not $19.

- Format: 9:16 vertical, 1080×1920, 30 fps, ~40s (exact length comes from
  the voiceover — see below)
- Free only: Remotion is free for teams of 3 or fewer, system fonts only,
  no paid assets, no paid voice. Renders on indra with local tooling.
- Voiceover: AI voice, never Abel's voice. Piper TTS (free, local, offline),
  voice `en_US-lessac-medium`. Model file lives in `voices/` (gitignored,
  ~63 MB — download it, don't commit it):
  `https://huggingface.co/rhasspy/piper-voices` →
  `en/en_US/lessac/medium/en_US-lessac-medium.onnx` (+ `.onnx.json`).

## Render the current ad

```bash
npm run voiceover   # regenerate narration WAVs + timings (after any script edit)
npm run render      # -> out/receipt-reel-v1.mp4
```

Or directly:

```bash
npx remotion render ReceiptReel out/receipt-reel-v1.mp4 --props=./src/script.json --license-key=free-license
```

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
Beat length = max(minSeconds, voiceover seconds + 0.5s tail), so narration
and visuals stay in sync. Total runtime = sum of beats.

To render a variant without touching the file, pass props instead:

```bash
npx remotion render ReceiptReel out/variant.mp4 --props=./my-variant.json --license-key=free-license
```

(The props file needs the same shape as `src/script.json`, including
`timings` — generate it with `npm run voiceover` first, or omit `timings`
and beats fall back to `minSeconds` with no audio.)

## Voiceover

- Engine: Piper (`pip install --user piper-tts`), model
  `en_US-lessac-medium`, `lengthScale` 1.0 (in `script.json` under `voice`).
  Swap the voice by changing `voice.model` / `voice.modelPath` and
  re-running `npm run voiceover`.
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
- No architecture diagrams of how the pipeline works.

The Remotion project itself stays **private**: local git repo, no remote,
no push, no public repo. The `voices/` model and `public/voiceover/` WAVs
are gitignored. If a future variant wants an outcome shot (dashboard,
posted clip), use a screenshot or screen recording of the product's
**output** — never a code editor, file tree, or log.

## Captions

Burned-in captions run the whole video (bottom pill, current beat's text).
Ads need them — most viewers watch muted. This is the explicit exception
to the clipsdaily clips rule of no burned-in captions; that rule covers
clips, not ads.

## Layout beats (v1)

| Beat | Time | Content |
| --- | --- | --- |
| Hook | 0–~4s | "Stop paying $49/mo for clips that die in 2 days" |
| Receipt | ~4–~21s | Bill lines appear one by one, then "Total: $49/mo" |
| Alternative | ~21–~34s | ClipForge pitch lines (live, no credits, auto-post, price) |
| CTA | ~34s–end | "Comment CLIPFORGE — I'll DM you the link", held |

Prices in v1 (verified Nov 16, 2026): OpusClip Pro $29/mo (300 credits),
Claude Pro $20/mo, 300 credits = 5 hours of video. Re-check vendor pricing
pages before rendering a new variant.

## Files

- `src/script.json` — the ad. Edit this for variants.
- `src/ReceiptReel.tsx` — the composition (layout, beats, captions).
- `src/Composition.tsx` — registers `ReceiptReel` (1080×1920, 30 fps).
- `scripts/generate-voiceover.mjs` — Piper narration + timing measurement.
- `public/voiceover/` — generated narration WAVs (gitignored).
- `voices/` — Piper voice model (gitignored, download only).
- `out/` — renders (gitignored).
