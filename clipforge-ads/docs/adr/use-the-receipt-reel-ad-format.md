# Use the receipt-reel ad format

## Status

Accepted. 2026-11-16.

## Context

ClipForge needed promo reels. The format that worked for other AI-tool
creators was the "receipt reel": hook (fake price vs real price) →
on-screen bill math → cheaper alternative → comment-keyword CTA. The
@tech.happens ClipIt Studio reel (Dfz6w2PO6oy) proved it: real credit
math (1 credit/min, 300 credits ≈ 5h, gone in 2 days at 2.5h/day),
Claude Pro $20, comment "ClipIt Studio" → DM link, 1,312 comments vs
739 likes. The reel got one number wrong (Opus Pro $19; the real price
is $29), which made the honest math stronger, not weaker.

## Decision

ClipForge ads v1–v5 use the receipt format: hook ("Stop paying $49/mo
for clips that die in 2 days") → receipt (OpusClip Pro $29/mo, Claude
Pro $20/mo, 300 credits = 5 hours, 2.5h/day → gone in 2 days, Total
$49/mo) → alternative (clips live, no credits, auto-posts IG/YT/TikTok,
$199 kit or $19–29/mo) → CTA ("Comment CLIPFORGE — I'll DM you the
link"). Every number on screen is real and re-checked against vendor
pricing pages before a new variant renders. v6 switches to the animated
explainer format (Huzaifa reel structure: hook number + rising bar →
four named parts → live-vs-VOD mechanism → result screen → CTA) for
the same reason: the structure carries the pitch, and every claim in it
is checkable. Burned-in captions run the whole video (explicit exception
to the clips rule — ads need them, most viewers watch muted).

## Consequences

- The format is proven by other creators and every number is honest,
  which is the defense against the skepticism that killed the
  Polymarket-bot reel's comments (its $223K was unverifiable).
- The format constrains variants: a new ad is a new `script.json`
  (same beats, different words/numbers), not a new composition.
- No ad version has been posted yet (v1–v6 rendered, none live as of
  Nov 17, 2026). I eyeball every ad before it goes out.
