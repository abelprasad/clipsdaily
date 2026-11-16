import re
from pathlib import Path

p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()

# --- 0. import re ---
if "\nimport re\n" not in s:
    s = s.replace("import subprocess\nimport sys\n",
                  "import re\nimport subprocess\nimport sys\n", 1)

# --- 1. hook auto-generation helpers, after _fix_caption_text ---
anchor = '''def _fix_caption_text(text):
    for bad, good in CAPTION_FIXES:
        text = text.replace(bad, good)
    return text
'''
helpers = anchor + '''

# Hook auto-generation (Nov 15, 2026, per Abel: ONE big hook at the
# start, NO word captions). The overlay plumbing takes an explicit
# hook, but nobody passes one in — so when hook is None, the burn
# step runs Whisper internally, derives the hook from the transcript's
# money line, and writes the SRT (queue titles use it). The hook is
# capped at 6 words / 36 chars so it fits the overlay's 2 lines of
# <=18 chars each. Returns "WAIT FOR IT" when no segment earns it —
# a garbled transcript line must never become the hook.
HOOK_WORDS = {"win", "won", "winning", "trip", "japan", "hong", "kong",
              "$", "dollar", "dollars", "thousand", "give", "gave",
              "giving", "gift", "free", "insane", "crazy", "just",
              "watch", "look", "way", "god", "shot", "live",
              "oh", "no", "stop", "wait"}
HOOK_FILLERS = {"bro", "yeah", "um", "uh", "man", "bruh", "like",
                "know", "mean", "right", "okay", "ok", "so", "well",
                "huh", "hey", "yo"}


def _make_hook(result, spike_at, channel):
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
'''
assert anchor in s and "_make_hook" not in s
s = s.replace(anchor, helpers, 1)

# --- 2. _caption_and_burn: auto-generate hook + SRT when hook is None ---
old_sig = "def _caption_and_burn(video, stem, channel, model, out_dir, hook=None):"
new_sig = ("def _caption_and_burn(video, stem, channel, model, out_dir,\n"
           "                          hook=None, spike_at=20):")
assert old_sig in s
s = s.replace(old_sig, new_sig, 1)

old_mkdir = """    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{stem}.mp4\""""
new_mkdir = """    out_dir.mkdir(parents=True, exist_ok=True)
    if hook is None:
        # No hook supplied: transcribe internally (Whisper runs here
        # ONLY to know what was said — nothing is burned as captions),
        # write the SRT for queue titles/debugging, derive the hook.
        import whisper
        m = whisper.load_model(model)
        result = m.transcribe(str(video), fp16=False, word_timestamps=True)
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
                f.write(f"{i}\\n{fmt(s0)} --> {fmt(e0)}\\n{text}\\n\\n")
        hook = _make_hook(result, spike_at, channel)
        print(f"[cutter] hook: {hook!r}", flush=True)
    final = out_dir / f"{stem}.mp4\""""
assert old_mkdir in s, "mkdir/final anchor not found"
s = s.replace(old_mkdir, new_mkdir, 1)

# --- 3. make_clip passes its spike offset through ---
old_call = ("    final = _caption_and_burn(raw, stem, channel, model, out_dir, hook=hook)\n"
            "    raw.unlink(missing_ok=True)\n"
            "    print(f\"[cutter] {final} ({clip_seconds}s, spike @{spike_seconds}s)\",")
new_call = ("    final = _caption_and_burn(raw, stem, channel, model, out_dir, hook=hook,\n"
            "                              spike_at=pre_seconds)\n"
            "    raw.unlink(missing_ok=True)\n"
            "    print(f\"[cutter] {final} ({clip_seconds}s, spike @{spike_seconds}s)\",")
assert old_call in s, "make_clip call anchor not found"
s = s.replace(old_call, new_call, 1)

p.write_text(s)
print("cutter.py patched: hook auto-generation + SRT restored")
