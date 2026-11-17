# Unslop audit — ClipForge Receipt Reel v4

Method: unslop skill by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)),
CC BY 4.0. Audited the actual v3 render (`out/receipt-reel-v3.mp4`, 46.5s,
1080x1920) frame by frame — 7 timestamps (2.5, 7, 14, 22, 26, 33, 44) —
plus the code in `src/ReceiptReel.tsx` (842 lines). Verdict: **light slop**.
The reel is mostly designed; the findings below are the whole list. v4 is a
polish-mode pass: fix only what the audit found, keep the palette, type,
layout and visual, and push the direction harder where the template check
fails. Nothing about the script, voice, timings, bill math or CTA changes.

## Direction

- **Product.** ClipForge auto-clips a streamer's live stream and posts the
  clips, so they stop renting OpusClip plus Claude by the credit.
- **Character.** Blunt, nocturnal, scrappy.
- **World.** A streamer's city at 2 a.m. after the stream ends — ink sky, lit
  windows, an empty road, one runner still going.
- **Moments.** The bill itself, adding up to $49 in amber; and the clip-coins
  the runner collects, amber discs with a play mark.
- **Signature.** The clip-coin trail — every coin on the road is a clip
  ClipForge already posted.

## Findings and fixes

### Surfaces and color

- **F1 — Sky is a hue wash with no scene.** `linear-gradient(180deg,
  #0B0E11 → #0E141B → #111A22)` in `RunnerBackground`. It stays inside one
  neutral, so it is not a hue gradient in the banned sense, but it is a wash
  with nothing in it. Fix: flat ink field, one flat dusk band at the horizon
  (amber, 0.05 opacity), one flat moon disc (off-white, upper right).
- **F2 — Coins use a radial gradient** (`#FFD97A → #F5B942 → #C98A1B`) and
  read as flat glossy dots. Fix: flat amber disc, flat darker-amber ring,
  white play triangle. Spin stays scaleX, plus a bob.
- **F3 — Amber splashed everywhere.** Full-width 12px amber top bar, hook
  $49, amber window dots, amber alt header, amber checkmarks, amber total,
  amber CTA wordmark, amber coins — eight uses. Fix: amber is reserved for
  the money that matters ($49 in the hook, $49 total, the a4 price) plus the
  clip-coins, which are the moment. Top bar removed. Windows go warm white.
  Alt header goes white. Checkmarks go white.
- **F4 — A second accent fights amber.** Coral `#E04A3A` on the receipt
  prices ($29/mo, $20/mo). Fix: coral deleted from the file. Prices are
  white, tabular figures. The cost reading now comes from the total, not
  from red.
- **F5 — Scrim is a 4-stop gradient.** Kept deliberately (see below): it is
  a legibility device, not decoration, and the legibility rule is a hard
  constraint. Values unchanged.

### Type

- **F6 — Weights 700–900 everywhere.** Hook 108/900, scene label 900, alt
  header 900, CTA 132/900, receipt rows 800, alt lines 800, caption 700.
  Unslop caps at 600. Fix: every weight token capped at 600. Honest caveat:
  Arial resolves on this machine to Liberation Sans, which ships no 600
  face, so Chromium renders 600 as Bold. The token is capped; the raster
  still reads bold. A bundled Inter would be needed for a true 600.
- **F7 — Uppercase tracked labels.** `THE BILL`, 44px/900, letter-spacing
  10; `CLIPFORGE` alt header, 52px/900, letter-spacing 6. Fix: `The bill`,
  40px/600, tracking 2; alt header `ClipForge`, 52px/600, tracking 0,
  white.
- **F8 — CTA `CLIPFORGE` is all caps.** Kept deliberately: it is the comment
  keyword the viewer must type, not a label, and the CTA wording is a hard
  constraint.
- **F9 — Numbers in mixed formats.** `$29/mo` next to `300 credits = 5
  hours` next to `2.5h/day`. Different facts, not one figure twice, but the
  figures now all use `tabular-nums`.
- **F10 — Caption bar off-grid and heavy.** Padding 22/34, radius 18,
  weight 700. Fix: padding 20/32, radius 16, weight 600.

### Icons

- **F11 — `✓` text-glyph checkmarks in the alt lines.** A glyph, not an
  emoji, but not a drawn icon either. Fix: inline SVG check, white stroke,
  round caps, one size everywhere.

### Spacing

- **F12 — Off-grid values.** Page padding 70, row padding 34, caption
  padding 22, receipt pitch 150, alt pitch 210, CTA margin-top 30, coin
  34px. Fix: all snapped to the 4px grid (72, 32, 20, 148, 208, 32, 32).
- **F13 — Dead bands in the early beats.** Receipt at t7: one row, ~600px of
  empty middle. Alt at t26: one line, ~700px empty. CTA top half empty.
  Fix: the block was re-centered — receipt rows start at 400 instead of
  328 and the total moved up to 1120, so the bill block (400–1262) sits on
  the optical center instead of crowding the top; the middle is now the game
  layer's stage on purpose — runner 1.2x bigger, a fast foreground layer
  added, top coin lane moved up into the band. Alt lines start at 480
  instead of 430 so the block sits lower.
- **F14 — Radii do not nest.** Receipt panels 20, caption 18. Fix: both 16.

### Copy

- **F15 — `LIVE` all caps in a1.** Script text, kept. The voiceover speaks
  it; the script is a hard constraint.
- **F16 — Trailing periods in a2** (`No credits. No per-minute billing.`).
  Script copy, kept. They are spoken sentences, not labels.
- **F17 — Claims.** `die in 2 days` and `Opus and Vizard don't` are
  substantiated inside the ad itself by the receipt math (300 credits = 5
  hours, 2.5h/day = gone in 2 days). Kept, and no new claims were invented.
  No exclamation marks and no hype words (supercharge, seamless, unlock,
  magic) anywhere — pass.

### Visuals

- **F18 — The runner is a generic stick figure.** One sine wave driving
  straight limbs. In stills it reads as a T-pose (t26), a split (t14/t22),
  a crucifix (t26). Template check fails: swap the product name and it fits
  any running ad. Fix: a real run cycle — 4 keyframed poses
  (contact / passing / contact / passing), two-segment limbs with knees and
  elbows, forward lean, cap and clip satchel. The runner is now a courier,
  not a pictogram.
- **F19 — Top-lane coins clip behind the receipt panel.** At t7/t14 the
  coins at y=322 peek over the panel's top edge like a rendering bug. Fix:
  top lane moved to y=252, clear of the panel; coins became clip-coins
  (F2), sizes vary 28/32/36.
- **F20 — Speed lines read as scratches in stills.** Uniform 3px, fixed
  opacity, scattered over the whole frame. Fix: confined to the runner band
  (y 1240–1700), widths 2–4, lengths 80–220, opacity fades in and out over
  each streak's travel.
- **F21 — Skyline is flat-topped rectangles** with 3 identical windows per
  building. Fix: antennas on ~30% of far buildings, stepped tops on mid
  buildings, warm-white windows in varied sizes.
- **F22 — Lane dashes are perfectly uniform** (90x8). Fix: dash lengths vary
  72–112.

### Motion

- **F23 — CTA looping pulse, ±3% at 1.4s.** Unslop: no looping pulse on
  things that are not live. Fix: removed. The CTA wordmark lands once with
  an overshoot spring and holds still.
- **F24 — Bouncy springs and overshoot.** See the tension note below.
- **F25 — Parallax.** See the tension note below.
- **F26 — Entrances from different directions.** Each scene now has exactly
  one entrance pattern: hook words pop, receipt rows slide, alt lines rise,
  CTA slams. Consistent inside a scene, different between scenes because
  the scenes are different moments.

### Template check

- **F27 — v3 would fit any "stop paying for X" SaaS ad.** v4 pushes the
  direction: the bill is this product's own math, the runner is a clip
  courier with a satchel, the coins are clip-coins, the world is a
  streamer's 2 a.m. city. Signature detail is the clip-coin trail.

## The tension, resolved in plain terms

Unslop's motion rules ("one ease-out curve", "no looping motion", "no
parallax", "bouncy springs → one ease-out") are written for UI chrome:
buttons, cards, menus, things a person operates. A 46-second reel is not
chrome. The motion IS the content, and Abel explicitly asked for
animator-quality springs and overshoot. Flattening the reel to one ease-out
curve would satisfy a UI rule by deleting the product.

So the split is: **unslop governs the look, the 12 principles govern the
motion.** Color, type, copy, spacing, composition and the runner's design
follow unslop (F1–F22 above). Entrances, slams, the run cycle, squash and
stretch, anticipation and follow-through follow the 12 principles, with two
guards borrowed from unslop: no motion loops without a reason (F23 — the CTA
pulse is gone; the endless scroll loops because the world is endless, which
is the reason), and one entrance pattern per scene (F26). The only linear
moves left are constant-velocity world scrolls (stars, skylines, dashes):
a runner runs at constant speed, so the world scrolling past at constant
speed is the physics, not an easing miss.

## Deliberately kept

- Script text, Kokoro af_heart voice, all 11 beat WAVs and timings, the
  $29 + $20 = $49 math, the CTA wording (`Comment CLIPFORGE`, `I'll DM you
  the link`).
- The scrim and the legibility rule: every text block sits on a panel, the
  caption pill, or the scrim.
- The burned-in caption bar (the explicit muted-viewer exception to the
  clipsdaily no-captions rule). It duplicates the on-screen line by design.
- Arial (Liberation Sans on the render box). No better face is installed;
  see F6 for the weight caveat.
- `CLIPFORGE` in caps in the CTA (F8), `LIVE` in a1 (F15), periods in a2
  (F16), the competitive claims as scripted (F17).

## Checklist (unslop, adapted for video)

- [x] Direction written, every pass follows it
- [x] Spacing on the 4px grid, equal things equal sizes
- [x] One tinted neutral ramp (ink), three text roles, one accent
- [x] No hue gradients, gradient text, glows, colored shadows, color blobs
- [x] No emoji; checks are drawn SVG
- [x] Type capped at 600, no uppercase tracked labels except the CTA keyword
- [x] No exclamation marks, no trailing periods on labels, no unverified claims
- [x] Numbers tabular, one format per figure
- [x] Nested radii (16/16)
- [x] One bright element per scene (the money, then the CTA wordmark)
- [x] No looping pulse; one entrance pattern per scene
- [ ] True 600 weight — blocked on font availability (F6 caveat)
- [ ] Runner still reads as a silhouette in a still frame — it is a
  silhouette by design; the cycle only fully reads in motion

## v4 verification

- Render: `out/receipt-reel-v4.mp4` — 7,833,418 bytes, 46.507s, 1080x1920,
  h264 + AAC, 30fps, 1395 frames. md5
  `2d91e03fa15acce77c1e8f74d8b38226`. v1/v2/v3 untouched (v3 md5 still
  `379bb13684f65d801fd8fc8d9a776a96`).
- Frame checks (from the v4 mp4, all legible): t2.5 hook — hook + $49 amber
  + caption pass; t7 receipt row 1 — `The bill`, white $29/mo, top coins
  clear of the panel; t14 rows 1–3 — all legible; t22 total — `Total:
  $49/mo` amber, runner head clear of the text (fixed from the first
  test render, where the 1.3x runner's head touched the total); t26 alt
  a1 — `ClipForge` white, drawn check, legible; t33 alt a1–a3 — all
  legible; t44 CTA — `Comment CLIPFORGE / I'll DM you the link`, no pulse,
  runner clear.
- Audio: reused v2 beat WAVs; volumedetect -17.7 dB mean / -0.7 dB max —
  identical to v3, no clipping. Silence scan: 11 gaps of ~1.24–1.29s
  (the beat tails) plus the 1.54s end tail; no dead stretch.
- Defects found and fixed during the build: (1) runner head collided with
  the total text at 1.3x scale — fixed by scale 1.2, runner top 1360,
  rows re-centered to start at 400, total moved to 1120; (2) a failed scp
  (two files, one destination) silently left the old component in place
  for one test render — caught by comparing frame hashes, re-copied, and
  re-verified by md5 before the full render.
- Commit: `Receipt Reel v4 — animator-quality motion + unslop audit`
  (no push). `out/` is gitignored, so the mp4 itself is not in git; the
  operator copy is `~/workspace/clipforge-ad-v4.mp4`.

Unslop by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)), CC BY 4.0.
