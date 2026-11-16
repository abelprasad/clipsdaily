"""Cutter: ffmpeg cuts clips around spikes, makes them vertical 9:16,
transcribes them with faster-whisper (CPU), burns a hook + a clipsdaily
credit in.

Two lengths:
  - 30s (Shorts / Reels): window starts 20s BEFORE the spike and ends
    10s after it. Chat reacts after the moment, so a centered cut
    starts too late and misses the moment itself.
  - 60-90s, target 75s (TikTok): TikTok Creator Rewards only pays for
    clips OVER 60 seconds. Built by extending the same window (20s
    before the spike, run to 75s total). If one moment cannot stretch
    to 60s+ (spike too close to the end of the recording), 2-3 spikes
    from the same stream are stitched into one 60-90s compilation.
    Single extended moment is always preferred; stitch only when one
    moment is too short.
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

TIKTOK_MIN_SECONDS = 60
TIKTOK_TARGET_SECONDS = 75
TIKTOK_MAX_SECONDS = 90


def probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


# Framing (Nov 15, 2026, per Abel: "why's it getting cropped, it
# should be the full clip" — NO CROPPING AT ALL). The whole 16:9
# source frame is scaled to fit the 1080 width (1080x608) and centered
# on a blurred, darkened copy of the same video filling the 1080x1920
# canvas. Nothing from the source frame is cut off — the standard
# full-frame vertical look. This supersedes the zoomed-out center
# crop; there is no crop region anymore.


def _cut_segment(recording, start, length, out_path):
    """ffmpeg: cut one vertical 1080x1920 segment, no captions yet.
    Full frame: the entire source frame is visible."""
    fc = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=30,eq=brightness=-0.25[bg2];"
        "[fg]scale=1080:-2[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[out]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(recording),
        "-t", str(length),
        "-filter_complex", fc,
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", str(out_path),
    ], check=True, capture_output=True)


# Corrections applied to every caption chunk (Whisper mishearings).
CAPTION_FIXES = [
    ("whole co-op", "Hong Kong"),
    ("home call", "Hong Kong"),
    ("TOOSIN'", "CHOOSIN'"),
    ("toosin'", "choosin'"),
]


def _fix_caption_text(text):
    for bad, good in CAPTION_FIXES:
        text = text.replace(bad, good)
    return text


# Hook auto-generation (Nov 15, 2026, per Abel: ONE big hook at the
# start, NO word captions). The overlay plumbing takes an explicit
# hook, but nobody passes one in — so when hook is None, the burn
# step runs Whisper internally, derives the hook from the transcript's
# money line, and writes the SRT (queue titles use it). The hook is
# capped at 6 words / 36 chars so it fits the overlay's 2 lines of
# <=18 chars each. Returns "WAIT FOR IT" when no segment earns it —
# a garbled transcript line must never become the hook.
HOOK_WORDS = {"win", "won", "winning", "trip", "japan", "hong", "kong",
              "dollar", "dollars", "thousand", "give", "gave",
              "giving", "gift", "free", "insane", "crazy", "just",
              "watch", "look", "way", "god", "shot", "live",
              "stop", "wait"}
HOOK_FILLERS = {"bro", "yeah", "um", "uh", "man", "bruh", "like",
                "know", "mean", "right", "okay", "ok", "so", "well",
                "huh", "hey", "yo"}


def _make_hook(result, spike_at, channel):
    best = None
    best_score = -1
    best_money = False
    for seg in result.get("segments", []):
        text = _fix_caption_text(seg.get("text", "").strip())
        if not text:
            continue
        low = text.lower()
        score = 0
        # Whole-word match only: substring matching let "no" fire inside
        # "not" and turned garbled lines into hooks.
        tokens = set(re.findall(r"[a-z0-9]+", low))
        money = "$" in low or bool(HOOK_WORDS & tokens)
        if money:
            score += 3
        if seg.get("start", 0) <= spike_at + 5 and seg.get("end", 0) >= spike_at - 5:
            score += 2
        nwords = len(re.findall(r"[A-Za-z0-9'$%,]+", text))
        if 3 <= nwords <= 8:
            score += 1
        if nwords > 12:
            score -= 2
        if score > best_score:
            best_score = score
            best = text
            best_money = money
    # A line only becomes a hook if it actually contains a hook word.
    # Spike overlap + length alone (score 3) must NOT promote a garbled
    # line — that is how "I DID NOT GOT THROW GUYS" became a hook.
    if not best or not best_money:
        return "WAIT FOR IT"
    words = [w.strip(",") for w in
             re.findall(r"[A-Za-z0-9'$%,]+", best)]
    words = [w for w in words if w.lower() not in HOOK_FILLERS]
    if len(words) < 3:
        words = [w.strip(",") for w in
                 re.findall(r"[A-Za-z0-9'$%,]+", best)]
    words = words[:6]
    while words and words[-1].lower() in HOOK_FILLERS | {"to", "the", "a",
                                                        "and", "of", "for"}:
        words.pop()
    if len(words) < 3:
        return "WAIT FOR IT"
    hook = " ".join(words).upper()
    while len(hook) > 35 and len(words) > 3:
        words.pop()
        hook = " ".join(words).upper()
    if not hook.endswith("!"):
        hook += "!"
    return hook


def _wrap_hook(text, max_len=18):
    # Split a hook line into at most 2 lines of <= max_len chars each.
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= max_len or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:2]


def _transcribe(video, model):
    """Transcribe with faster-whisper, returning an openai-whisper-shaped
    result dict: {"segments": [{"start", "end", "text", "words":
    [{"word", "start", "end"}]}]}. Model is the config name (e.g.
    "base"), run on CPU with int8 compute (fastest on CPU, same
    accuracy class as openai-whisper; ~4x faster, no torch needed).
    faster-whisper's transcribe() returns a segment generator, so it
    is consumed into a list here. Switched Nov 16, 2026 — the note
    taker already uses faster-whisper."""
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = m.transcribe(str(video), word_timestamps=True)
    out = []
    for seg in segments:
        words = [{"word": w.word, "start": w.start, "end": w.end}
                 for w in (seg.words or [])]
        out.append({"start": seg.start, "end": seg.end,
                    "text": seg.text, "words": words})
    return {"segments": out}


def _caption_and_burn(video, stem, channel, model, out_dir,
                          hook=None, spike_at=20):
    # Burn the credit + one big hook overlay into a finished clip.
    # (Changed Nov 15, 2026, per Abel: NO more burned-in Whisper word
    # captions. Instead ONE big hook line at the START of the clip only,
    # first ~3 seconds, big bold centered text, set lower (y=300) to clear
    # the platform top UI. hook is the
    # line, e.g. "SPEED GAVE HIM $10,000"; hook=None means credit only.
    # model is kept for backward compatibility and ignored -- no Whisper
    # runs here anymore, so cuts are much faster.)
    out_dir.mkdir(parents=True, exist_ok=True)
    if hook is None:
        # No hook supplied: transcribe internally (Whisper runs here
        # ONLY to know what was said — nothing is burned as captions),
        # write the SRT for queue titles/debugging, derive the hook.
        # faster-whisper (Nov 16, 2026 — replaces openai-whisper).
        # _transcribe returns the same result shape the chunking +
        # hook code below expects, so nothing else changes.
        result = _transcribe(str(video), model)
        chunks = []
        cur_words, cur_start, cur_end = [], None, None
        for seg in result["segments"]:
            for w in seg.get("words", []):
                word = w["word"].strip()
                if not word:
                    continue
                if cur_start is None:
                    cur_start = w["start"]
                cur_words.append(word)
                cur_end = w["end"]
                if len(cur_words) >= 6 or (cur_end - cur_start) >= 2.5:
                    chunks.append((cur_start, cur_end, " ".join(cur_words)))
                    cur_words, cur_start, cur_end = [], None, None
        if cur_words:
            chunks.append((cur_start, cur_end, " ".join(cur_words)))
        if not chunks:
            for seg in result["segments"]:
                chunks.append((seg["start"], seg["end"], seg["text"].strip()))
        srt = out_dir / f"{stem}.srt"
        with open(srt, "w") as f:
            for i, (s0, e0, text) in enumerate(chunks, 1):
                text = _fix_caption_text(text)
                f.write(f"{i}\n{fmt(s0)} --> {fmt(e0)}\n{text}\n\n")
        hook = _make_hook(result, spike_at, channel)
        print(f"[cutter] hook: {hook!r}", flush=True)
    final = out_dir / f"{stem}.mp4"
    credit = f"clipsdaily • {channel}"
    filters = []
    hook_file = None
    if hook:
        lines = _wrap_hook(hook.upper())
        hook_file = out_dir / f"{stem}_hook.txt"
        hook_file.write_text(chr(10).join(lines))
        # Motion (motion-design skill, LottieFiles — Energetic archetype):
        # entrance 250ms ease-out-expo on position + opacity (slide down
        # 40px into place while fading in), hold, 170ms ease-in fade out.
        # Entrance > exit; decelerate in, accelerate out. Box removed so
        # the fade applies to the whole hook, not just the letters.
        filters.append(
            "drawtext=textfile='%s':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "fontcolor=white:fontsize=84:borderw=4:bordercolor=black:"
            "x=(w-text_w)/2:"
            "y='300-40*pow(2,-10*min(t/0.25,1))':"
            "alpha='(1-pow(2,-10*min(t/0.25,1)))*(1-pow(max(0,(t-2.83)/0.17),2))':"
            "enable='between(t,0,3)'" % hook_file)
    filters.append(
        f"drawtext=text='{credit}':fontcolor=white:fontsize=24:"
        f"box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20")
    vf = ",".join(filters)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", str(final),
    ], check=True, capture_output=True)
    if hook_file is not None:
        hook_file.unlink(missing_ok=True)
    return final



def make_clip(recording, spike_seconds, channel, clip_seconds=30,
              model="base", out_dir=None, pre_seconds=20, hook=None):
    """Cut clip_seconds starting pre_seconds before the spike.
    Default 30s: 20s before, 10s after. Returns the output Path."""
    duration = probe_duration(recording)
    start = max(0.0, spike_seconds - pre_seconds)
    if start + clip_seconds > duration:
        start = max(0.0, duration - clip_seconds)
    print(f"[cutter] window {start:.1f}s-{start + clip_seconds:.1f}s "
          f"(spike @{spike_seconds}s)", flush=True)
    out_dir = Path(out_dir or HERE / "clips")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{channel}_{int(spike_seconds)}s"
    raw = out_dir / f"{stem}_raw.mp4"
    _cut_segment(recording, start, clip_seconds, raw)
    final = _caption_and_burn(raw, stem, channel, model, out_dir, hook=hook,
                              spike_at=pre_seconds)
    raw.unlink(missing_ok=True)
    print(f"[cutter] {final} ({clip_seconds}s, spike @{spike_seconds}s)",
          flush=True)
    return final


def make_tiktok_clip(recording, spikes, channel, model="base",
                     out_dir=None, target_seconds=TIKTOK_TARGET_SECONDS, hook=None):
    """TikTok version: 60-90s, target 75s. Prefers one extended moment
    (20s before the strongest spike, run to target). If the strongest
    spike cannot stretch to 60s+ inside the recording, stitches the
    top 3 spikes (chronological order) into one compilation.
    spikes = list of {seconds_in, intensity}. Returns (Path, method)
    where method is 'single', 'stitched', or (None, 'too_short') when
    the recording itself is under 60s."""
    duration = probe_duration(recording)
    if duration < TIKTOK_MIN_SECONDS:
        print(f"[cutter] recording only {duration:.0f}s, no TikTok "
              "version possible", flush=True)
        return None, "too_short"
    out_dir = Path(out_dir or HERE / "clips")
    out_dir.mkdir(parents=True, exist_ok=True)
    ranked = sorted(spikes, key=lambda s: s.get("intensity", 0),
                    reverse=True)
    best = ranked[0]
    spike = best["seconds_in"]
    # Single extended moment: 20s before, run to target seconds.
    if spike - 20 >= 0 and spike + (target_seconds - 20) <= duration:
        stem = f"{channel}_{int(spike)}s_tiktok"
        raw = out_dir / f"{stem}_raw.mp4"
        _cut_segment(recording, spike - 20, target_seconds, raw)
        final = _caption_and_burn(raw, stem, channel, model, out_dir, hook=hook)
        raw.unlink(missing_ok=True)
        print(f"[cutter] TikTok single {final} ({target_seconds}s, "
              f"spike @{spike}s)", flush=True)
        return final, "single"
    # Stitch: top 3 spikes, chronological, split the target evenly.
    picked = sorted(ranked[:3], key=lambda s: s["seconds_in"])
    seg_len = target_seconds // len(picked)
    parts = []
    for i, s in enumerate(picked):
        start = max(0.0, s["seconds_in"] - 20)
        if start + seg_len > duration:
            seg_len_i = max(0.0, duration - start)
            if seg_len_i < 10:
                continue
        else:
            seg_len_i = seg_len
        part = out_dir / f"{channel}_tt_part{i}.mp4"
        _cut_segment(recording, start, seg_len_i, part)
        parts.append(part)
    if not parts:
        return None, "too_short"
    stem = f"{channel}_{int(picked[0]['seconds_in'])}s_tiktok"
    stitched = out_dir / f"{stem}_raw.mp4"
    concat_list = out_dir / f"{stem}_concat.txt"
    concat_list.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(stitched),
    ], check=True, capture_output=True)
    final = _caption_and_burn(stitched, stem, channel, model, out_dir, hook=hook)
    for p in parts + [stitched, concat_list]:
        p.unlink(missing_ok=True)
    got = probe_duration(final)
    print(f"[cutter] TikTok stitched {final} ({got:.0f}s from "
          f"{len(parts)} moments)", flush=True)
    return final, "stitched"


def fmt(seconds):
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


if __name__ == "__main__":
    recording, spike, channel = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    make_clip(Path(recording), spike, channel)
