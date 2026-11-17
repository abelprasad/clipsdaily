# Remove burned-in word captions

## Status

Accepted — 2026-11-15

## Context

On the morning of Nov 15, 2026, clips burned Whisper word captions into the video. I viewed the first live TikTok Japan clip on my phone and said "it's captioned weird". The defects: the captions were enormous (they filled the whole frame, ran off the edges, and covered Speed's face in six lines of black boxes); the credit overlay read literally "clipsdaily u2022 ishowspeed" (a double-escaped bullet in `cutter.py`); and Whisper mistranscribed lines ("TOOSIN' THE WINNER", "You going to whole co-op!" for Hong Kong). The first fix (smaller font, outline instead of boxes, word-timestamp chunks, a correction map) helped, but I then decided the word captions should go entirely: "we don't need captions, we just need one big caption in the start of the clip where it's sorta clickbaity and interesting".

## Decision

No Whisper word captions are burned into the video. There is ONE big hook line at the start of the clip only (first ~3 seconds, big bold text, max ~8 words, true to the moment, for example "HE JUST WON A TRIP TO JAPAN"). The hook sits lower on the frame, at y=300, to clear the platform top UI. Whisper may still run internally to find the moment; nothing burns in except the hook.

## Consequences

- Faces and gameplay stay visible for the whole clip.
- The hook carries the moment in the first seconds, which is what stops the scroll.
- The hook is generated automatically per clip from the transcript money line or spike context inside the cutter/poster flow.
- A garbled transcript line must never become the hook: a line only becomes a hook if it actually contains a hook word (this is how "I DID NOT GOT THROW GUYS" became a hook once, and the gate was added).
- The hook entrance uses motion-design easing (250ms ease-out-expo slide and fade in, 170ms ease-in fade out).
