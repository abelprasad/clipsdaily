#!/usr/bin/env python3
"""Pre-post retention check for ClipForge ads.

Runs against a rendered ad mp4 + src/script.json and flags the seconds where
a viewer is most likely to bail, before the ad is posted. Heuristic only:
it measures what ffmpeg can measure (pace, silence, holds, frozen frames)
and says so. It does NOT score the ad, it does NOT predict watch time, and
there is no "out of 100" number anywhere in here — any tool that claims a
calibrated retention score without real watch data is inventing one.

Checks
  1. Pace: words-per-minute of each beat's voice line. FLAG over 200 wpm
     (rushed, hard to follow), WARN over 180.
  2. Silence: gaps of 0.5s or more in the rendered audio (dead air), and a
     trailing tail over 1.0s after the last word. Thresholds come from the
     v5 fix: inter-beat gaps were trimmed to ~0.48-0.51s and the end tail to
     0.44s, so anything above that is a regression.
  3. Beat hold: per-beat voiceover WAV shorter than its beat timing by more
     than 1.0s means the beat is padded with a visual hold and no narration.
  4. Visual stasis: stretches over 4.0s where the picture barely changes
     (mean per-pixel frame delta under 1.0 at 2 fps, 64x114 gray). A beat
     that long with nothing moving is where people swipe.
  5. Hook payoff (ESTIMATE): when the first money/number word is spoken in
     the hook beat, assuming words are evenly spaced across the beat. This
     is an estimate, not a measurement — there is no speech recognition
     here. FLAG if the estimate is past 3.0s. If it flags, watch the first
     3 seconds by eye; the on-screen payoff may land earlier or later than
     the spoken one.

Usage
  python3 scripts/retention-check.py [--mp4 out/receipt-reel-v6.mp4]
                                      [--script src/script.json]
                                      [--voiceover-dir public/voiceover]
                                      [--out out/v6-retention.txt]
                                      [--debug]
  Exit 0 = PASS (no flags), 1 = REVIEW (flags found), 2 = tool/usage error.
  Warnings do not change the verdict. Run from the repo root.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

FLAG_WPM = 200
WARN_WPM = 180
SILENCE_MIN = 0.5          # seconds; anything at/above is dead air
END_TAIL_MAX = 1.0         # seconds of trailing silence allowed
HOLD_MAX = 1.0             # seconds a beat may outlast its voiceover
STASIS_MIN = 4.0           # seconds of near-frozen picture that gets flagged
STASIS_DELTA = 0.5         # mean per-pixel gray delta (0-255) under this = frozen
                          # calibrated on v6: slowest animated moment measured 1.29,
                          # a truly frozen frame measures 0.0-0.1, so 0.5 sits between
STASIS_FPS = 2
HOOK_PAYOFF_MAX = 3.0      # seconds; hook payoff later than this is flagged

NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
    "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand",
}


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc


def ffprobe_duration(path):
    proc = run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "csv=p=0", path])
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def beat_spans(script):
    """Return [(beat_id, start, end)] in seconds from script.json timings."""
    spans = []
    t = 0.0
    for beat in script["beats"]:
        dur = script.get("timings", {}).get(beat["id"], beat.get("minSeconds", 0))
        spans.append((beat["id"], t, t + float(dur)))
        t += float(dur)
    return spans, t


def beat_at(spans, t):
    names = [bid for bid, start, end in spans if start <= t < end]
    return names[0] if names else None


def check_pace(script):
    flags, warns, notes = [], [], []
    for beat in script["beats"]:
        dur = script.get("timings", {}).get(beat["id"], beat.get("minSeconds", 0))
        words = len(beat.get("voice", "").split())
        if not dur or not words:
            continue
        wpm = words / float(dur) * 60
        notes.append(f"  {beat['id']}: {words} words / {float(dur):.2f}s = {wpm:.0f} wpm")
        if wpm > FLAG_WPM:
            flags.append((beat["id"], 0.0,
                          f"{wpm:.0f} wpm — rushed, listeners lose words",
                          "Split the beat in two or cut words until it is under 200 wpm."))
        elif wpm > WARN_WPM:
            warns.append((beat["id"], 0.0,
                          f"{wpm:.0f} wpm — fast, near the rushed line",
                          "Ear-check this beat before posting; trim a clause if it sounds hurried."))
    return flags, warns, notes


def check_silence(mp4, spans, total):
    flags, warns, notes = [], [], []
    proc = run(["ffmpeg", "-v", "info", "-i", mp4, "-af",
                "silencedetect=noise=-45dB:d=0.3", "-f", "null", "-"])
    text = proc.stderr
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", text)]
    ends = [(float(m.group(1)), float(m.group(2)))
            for m in re.finditer(
                r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", text)]
    if not starts and not ends:
        notes.append("  no silences detected at -45 dB (or silencedetect output unreadable)")
        return flags, warns, notes
    audio_dur = ffprobe_duration(mp4) or total
    silences = []
    for i, start in enumerate(starts):
        if i < len(ends):
            end, dur = ends[i]
        else:
            end, dur = audio_dur, audio_dur - start
        silences.append((start, end, dur))
    for start, end, dur in silences:
        mid = (start + end) / 2
        bid = beat_at(spans, mid)
        where = f"beat {bid}" if bid else "between beats"
        if end >= audio_dur - 0.05 and dur > END_TAIL_MAX:
            flags.append((bid or "cta", end,
                          f"end tail {dur:.2f}s of silence after the last word",
                          "Trim the tail to under 1s — the loop point is where replays die."))
        elif dur >= SILENCE_MIN:
            flags.append((bid or "?", start,
                          f"{dur:.2f}s dead air at {start:.2f}s ({where})",
                          "Trim the gap, or keep it if the pause is deliberate — "
                          "it is the longest silence in the ad."))
        else:
            notes.append(f"  gap {dur:.2f}s at {start:.2f}s ({where}) — under threshold, ok")
    return flags, warns, notes


def check_hold(script, voiceover_dir):
    flags, warns, notes = [], [], []
    for beat in script["beats"]:
        wav = os.path.join(voiceover_dir, f"{beat['id']}.wav")
        dur = script.get("timings", {}).get(beat["id"], beat.get("minSeconds", 0))
        if not os.path.exists(wav):
            notes.append(f"  {beat['id']}: no voiceover wav, hold check skipped")
            continue
        audio = ffprobe_duration(wav)
        if audio is None:
            notes.append(f"  {beat['id']}: could not read wav duration, hold check skipped")
            continue
        hold = float(dur) - audio
        notes.append(f"  {beat['id']}: beat {float(dur):.2f}s, voice {audio:.2f}s, hold {hold:.2f}s")
        if hold > HOLD_MAX:
            flags.append((beat["id"], 0.0,
                          f"beat outlasts its voiceover by {hold:.2f}s",
                          "Shorten minSeconds or extend the voice line — a long silent hold reads as frozen."))
    return flags, warns, notes


def frame_deltas(mp4):
    """Mean per-pixel gray delta between consecutive 2 fps frames."""
    w, h = 64, 114
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", mp4, "-vf",
         f"fps={STASIS_FPS},scale={w}:{h},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    if proc.returncode != 0:
        return None
    size = w * h
    data = proc.stdout
    frames = [data[i:i + size] for i in range(0, len(data) - size + 1, size)]
    deltas = []
    for prev, cur in zip(frames, frames[1:]):
        diff = sum(abs(a - b) for a, b in zip(prev, cur)) / size
        deltas.append(diff)
    return deltas


def check_stasis(mp4, spans, debug=False):
    flags, warns, notes = [], [], []
    deltas = frame_deltas(mp4)
    if deltas is None:
        notes.append("  frame sampling failed, stasis check skipped")
        return flags, warns, notes
    notes.append(f"  {len(deltas) + 1} frames sampled at {STASIS_FPS} fps, "
                 f"mean delta {sum(deltas) / max(len(deltas), 1):.2f}, "
                 f"range {min(deltas):.2f}-{max(deltas):.2f}, "
                 f"{sum(1 for d in deltas if d < STASIS_DELTA)} samples under {STASIS_DELTA}")
    if debug:
        notes.append("  deltas: " + " ".join(f"{d:.1f}" for d in deltas))
    # A stretch is a run of consecutive samples under the delta threshold.
    # Sample i covers t = (i+1)/fps; a run of k low samples spans k/fps seconds.
    run_start = None
    for i, d in enumerate(deltas):
        if d < STASIS_DELTA:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                span_s = (i - run_start) / STASIS_FPS
                if span_s > STASIS_MIN:
                    t0 = (run_start + 1) / STASIS_FPS
                    bid = beat_at(spans, t0 + span_s / 2)
                    flags.append((bid or "?", t0,
                                  f"picture near-frozen for {span_s:.1f}s from {t0:.1f}s",
                                  "Something has to move in this stretch — a pop, a count, a cut — or cut the beat short."))
                run_start = None
    if run_start is not None:
        span_s = (len(deltas) - run_start) / STASIS_FPS
        if span_s > STASIS_MIN:
            t0 = (run_start + 1) / STASIS_FPS
            bid = beat_at(spans, t0 + span_s / 2)
            flags.append((bid or "?", t0,
                          f"picture near-frozen for {span_s:.1f}s from {t0:.1f}s",
                          "Something has to move in this stretch — a pop, a count, a cut — or cut the beat short."))
    return flags, warns, notes


def check_hook(script):
    flags, warns, notes = [], [], []
    hook = next((b for b in script["beats"] if b.get("kind") == "hook"), None)
    if hook is None:
        notes.append("  no hook beat found, hook check skipped")
        return flags, warns, notes
    dur = float(script.get("timings", {}).get(hook["id"], hook.get("minSeconds", 0)))
    words = hook.get("voice", "").split()
    if not words or not dur:
        notes.append("  hook has no voice line, hook check skipped")
        return flags, warns, notes
    idx = None
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-z0-9$-]", "", word.lower())
        base = clean.lstrip("$").split("-")[0]
        if re.search(r"\d", clean) or base in NUMBER_WORDS or clean in NUMBER_WORDS:
            idx = i
            break
    if idx is None:
        notes.append("  no money/number word in hook voice — payoff time not estimated")
        return flags, warns, notes
    est = (idx + 0.5) / len(words) * dur
    notes.append(f"  hook payoff word {idx + 1}/{len(words)} "
                 f"('{words[idx]}'), estimated at ~{est:.2f}s (linear word timing, not measured)")
    if est > HOOK_PAYOFF_MAX:
        flags.append(("hook", est,
                      f"hook payoff estimated at ~{est:.2f}s, past the 3s line",
                      "Move the number/claim to the first line of the hook voice — "
                      "or watch the first 3s: the on-screen payoff may land sooner than the spoken one."))
    return flags, warns, notes


def main():
    parser = argparse.ArgumentParser(description="Pre-post retention check for ClipForge ads.")
    parser.add_argument("--mp4", default="out/receipt-reel-v6.mp4")
    parser.add_argument("--script", default="src/script.json")
    parser.add_argument("--voiceover-dir", default="public/voiceover")
    parser.add_argument("--out", default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    for path in (args.mp4, args.script):
        if not os.path.exists(path):
            print(f"missing file: {path}", file=sys.stderr)
            return 2
    with open(args.script) as f:
        script = json.load(f)

    total_dur = ffprobe_duration(args.mp4)
    spans, total = beat_spans(script)
    if total_dur is None:
        total_dur = total

    lines = []
    lines.append(f"Retention check: {args.mp4}")
    lines.append(f"  script: {args.script} ({script.get('title', 'untitled')})")
    lines.append(f"  video {total_dur:.2f}s, {len(script['beats'])} beats")
    lines.append("")
    lines.append("What this measures (heuristic only — no score, no watch-time prediction):")
    lines.append("  pace (wpm), dead air, beat holds, frozen picture, hook payoff estimate.")
    lines.append("")

    all_flags, all_warns = [], []
    for name, fn, fn_args in [
        ("Pace", check_pace, (script,)),
        ("Silence", check_silence, (args.mp4, spans, total)),
        ("Beat hold", check_hold, (script, args.voiceover_dir)),
        ("Visual stasis", check_stasis, (args.mp4, spans, args.debug)),
        ("Hook payoff (estimate)", check_hook, (script,)),
    ]:
        flags, warns, notes = fn(*fn_args)
        all_flags.extend((name, b, t, msg, fix) for b, t, msg, fix in flags)
        all_warns.extend((name, b, t, msg, fix) for b, t, msg, fix in warns)
        lines.append(f"== {name} ==")
        for note in notes:
            lines.append(note)
        if args.debug:
            for b, t, msg, fix in flags + warns:
                lines.append(f"  [{name}] {b} @ {t:.2f}s: {msg}")
        lines.append("")

    lines.append("== Flags ==")
    if all_flags:
        for name, beat, t, msg, fix in sorted(all_flags, key=lambda x: x[2]):
            lines.append(f"[FLAG] {name} — {beat} @ {t:.2f}s — {msg}")
            lines.append(f"        Fix: {fix}")
    else:
        lines.append("none")
    lines.append("")
    lines.append("== Warnings ==")
    if all_warns:
        for name, beat, t, msg, fix in sorted(all_warns, key=lambda x: x[2]):
            lines.append(f"[WARN] {name} — {beat} @ {t:.2f}s — {msg}")
            lines.append(f"        Fix: {fix}")
    else:
        lines.append("none")
    lines.append("")
    verdict = "REVIEW — flags above, fix them before posting" if all_flags else "PASS — no flags"
    lines.append(f"Verdict: {verdict}")
    lines.append("What this cannot catch: on-screen layout (empty bands, overlaps, text "
                 "collisions), whether a claim is true, whether the hook is interesting, "
                 "or anything about the audience. Watch the render once by eye.")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if args.out:
        with open(args.out, "w") as f:
            f.write(report)
        print(f"Report written to {args.out}")
    return 1 if all_flags else 0


if __name__ == "__main__":
    sys.exit(main())
