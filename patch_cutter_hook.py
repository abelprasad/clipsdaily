import re
from pathlib import Path

p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()

# --- 0. import re at top ---
if "\nimport re\n" not in s:
    s = s.replace("import subprocess\nimport sys\n",
                  "import re\nimport subprocess\nimport sys\n", 1)

# --- 1. add hook generation helpers after _fix_caption_text ---
anchor = '''def _fix_caption_text(text):
    for bad, good in CAPTION_FIXES:
        text = text.replace(bad, good)
    return text
'''
helpers = anchor + '''

# Hook words: lines containing one of these are "money lines" worth
# turning into the big opening hook. Lines with none of them never
# become a hook (a garbled transcript line is worse than no hook).
HOOK_WORDS = {"win", "won", "winning", "trip", "japan", "hong", "kong",
              "$", "dollar", "dollars", "thousand", "give", "gave",
              "giving", "gift", "free", "insane", "crazy", "just",
              "watch", "look", "way", "god", "shot", "moments", "live",
              "oh", "no", "stop", "wait"}
HOOK_FILLERS = {"bro", "yeah", "um", "uh", "man", "bruh", "like",
                "know", "mean", "right", "okay", "ok", "so", "well",
                "huh", "hey", "yo"}
HOOK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _make_hook(result, spike_at, channel):
    """One big clickbaity hook line from the transcript's money line.

    Picks the segment that (a) contains a hook word and (b) overlaps
    the spike. Uppercases it, drops filler words, caps at 8 words.
    Returns "WAIT FOR IT" when no segment earns it — a garbled line
    must never become the hook.
    """
    best = None
    best_score = -1
    for seg in result.get("segments", []):
        text = _fix_caption_text(seg.get("text", "").strip())
        if not text:
            continue
        low = text.lower()
        score = 0
        if any(w in low for w in HOOK_WORDS):
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
    if not best or best_score < 3:
        return "WAIT FOR IT"
    words = [w.strip(",") for w in
             re.findall(r"[A-Za-z0-9'$%,]+", best)]
    words = [w for w in words if w.lower() not in HOOK_FILLERS]
    if len(words) < 3:
        words = [w.strip(",") for w in
                 re.findall(r"[A-Za-z0-9'$%,]+", best)]
    words = words[:8]
    while words and words[-1].lower() in HOOK_FILLERS | {"to", "the", "a",
                                                        "and", "of", "for"}:
        words.pop()
    if len(words) < 3:
        return "WAIT FOR IT"
    hook = " ".join(words).upper()
    if not hook.endswith("!"):
        hook += "!"
    return hook


def _wrap_hook(hook):
    """Split the hook into 1-2 lines and pick a fontsize that fits.

    Returns (lines, fontsize). DejaVu Bold averages ~0.62em per char;
    longest line must fit in 1000px of the 1080px frame.
    """
    words = hook.split()
    lines = [" ".join(words)]
    size = min(84, int(1000 / (max(len(lines[0]), 1) * 0.62)))
    if size < 56 and len(words) > 3:
        half = len(words) // 2
        lines = [" ".join(words[:half]), " ".join(words[half:])]
        size = min(84, int(1000 / (max(len(l) for l in lines) * 0.62)))
    if size < 40:
        words = words[:6]
        half = len(words) // 2
        lines = [" ".join(words[:half]), " ".join(words[half:])]
        size = 44
    return lines, max(size, 36)
'''
assert anchor in s and "_make_hook" not in s
s = s.replace(anchor, helpers, 1)

# --- 2. _caption_and_burn: hook overlay instead of word captions ---
old_sig = '''def _caption_and_burn(video, stem, channel, model, out_dir):
    """Whisper captions (CPU) + burn captions and credit into a
    finished clip. Returns the final Path.

    Captions are word-level chunks (max 6 words / ~2.5s), rendered
    small at the bottom of the frame with outline only (no opaque
    box). Model is "small" for accuracy.
    """'''
new_sig = '''def _caption_and_burn(video, stem, channel, model, out_dir, spike_at=20):
    """Whisper transcript (for the hook + SRT) + burn ONE big hook
    overlay (first 3s only) and the credit into a finished clip.
    Returns the final Path.

    Caption strategy (Nov 15, 2026, per Abel): NO burned-in word
    captions at all. One big clickbaity hook line at the start,
    derived from the transcript's money line, big bold top-center.
    Whisper still runs so the hook is true to the moment, and the SRT
    is still written (queue titles + debugging use it).
    """'''
assert old_sig in s
s = s.replace(old_sig, new_sig, 1)

old_burn = '''    final = out_dir / f"{stem}.mp4"
    credit = f"clipsdaily \\u2022 {channel}"
    vf = (f"subtitles={srt}:force_style='PlayResX=1080,PlayResY=1920,"
         f"Fontsize=64,Bold=1,PrimaryColour=&HFFFFFF&,"
         f"OutlineColour=&H000000&,BorderStyle=1,Outline=2,Alignment=2,"
         f"MarginV=150',"
         f"drawtext=text='{credit}':fontcolor=white:fontsize=24:"
         f"box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", str(final),
    ], check=True, capture_output=True)
    return final'''
new_burn = '''    final = out_dir / f"{stem}.mp4"
    hook = _make_hook(result, spike_at, channel)
    print(f"[cutter] hook: {hook!r}", flush=True)
    lines, fontsize = _wrap_hook(hook)
    hook_file = out_dir / f"{stem}_hook.txt"
    hook_file.write_text("\\n".join(lines))
    credit = f"clipsdaily \\u2022 {channel}"
    vf = (f"drawtext=textfile='{hook_file}':fontfile={HOOK_FONT}:"
         f"fontcolor=white:fontsize={fontsize}:borderw=4:"
         f"bordercolor=black:line_spacing=10:"
         f"x=(w-text_w)/2:y=150:enable='between(t,0,3)',"
         f"drawtext=text='{credit}':fontcolor=white:fontsize=24:"
         f"box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", str(final),
    ], check=True, capture_output=True)
    hook_file.unlink(missing_ok=True)
    return final'''
assert old_burn in s, "old burn block not found"
s = s.replace(old_burn, new_burn, 1)

# --- 3. make_clip passes its spike offset through ---
old_call = '''    stem = f"{channel}_{int(spike_seconds)}s"
    raw = out_dir / f"{stem}_raw.mp4"
    _cut_segment(recording, start, clip_seconds, raw)
    final = _caption_and_burn(raw, stem, channel, model, out_dir)'''
new_call = '''    stem = f"{channel}_{int(spike_seconds)}s"
    raw = out_dir / f"{stem}_raw.mp4"
    _cut_segment(recording, start, clip_seconds, raw)
    final = _caption_and_burn(raw, stem, channel, model, out_dir,
                              spike_at=pre_seconds)'''
assert old_call in s
s = s.replace(old_call, new_call, 1)

p.write_text(s)
print("cutter.py patched: hook overlay, no word captions")
