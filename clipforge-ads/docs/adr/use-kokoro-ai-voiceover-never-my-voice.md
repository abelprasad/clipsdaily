# Use Kokoro AI voiceover, never my voice

## Status

Accepted. 2026-11-16.

## Context

The first ad (v1) used Piper `en_US-lessac-medium`. My feedback:
"the voice needs to be more natural and human." He also set the rule
the same night: "don't use my voice, use ai voice" — AI voice only,
never my voice, standing for ClipForge ads.

## Decision

Use Kokoro TTS (Kokoro-82M, MIT, free, local, offline), voice
`af_heart` at speed 1.1, loudness-normalized to -17 dB mean, in
`.venv-kokoro/` (torch CPU, `misaki[en]`, spaCy `en_core_web_sm`,
espeak-ng 1.50). v2–v6 all use it. Voice samples of other voices were
rendered Nov 16 and I picked `af_heart` at speed 0.95 originally;
v5 moved the render speed to 1.1 for pace (dead-air trimming did more
than the speed change). No ElevenLabs, no paid voice service, no recordings of my voice. Ever. The voice is chosen in `script.json` under `voice`;
swap it by changing `voice.model` and re-running `npm run voiceover`.

## Consequences

- The ads sound human without me recording anything, and the
  voiceover costs $0 (local TTS, no API).
- Kokoro at 1.1x is ~7–10% faster than 1.0x; the v5 pace win came
  mostly from trimming inter-beat dead air (1.24–1.29s → ~0.5s), not
  from the speed change. Per-beat speed, not global speed, is the fix
  if a beat runs hot (v5's r4 beat hit ~285 wpm).
- The voiceover pipeline is deterministic: `npm run voiceover`
  regenerates WAVs + timings from `script.json`, so a variant is one
  file edit + two commands.
