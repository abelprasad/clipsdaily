from pathlib import Path
p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()
old = """    best = None
    best_score = -1
    for seg in result.get("segments", []):
        text = _fix_caption_text(seg.get("text", "").strip())
        if not text:
            continue
        low = text.lower()
        score = 0
        # Whole-word match only: substring matching let "no" fire inside
        # "not" and turned garbled lines into hooks.
        tokens = set(re.findall(r"[a-z0-9]+", low))
        if "$" in low or (HOOK_WORDS & tokens):
            score += 3"""
new = """    best = None
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
            score += 3"""
assert old in s
s = s.replace(old, new, 1)
old2 = """        if score > best_score:
            best_score = score
            best = text
    if not best or best_score < 3:
        return "WAIT FOR IT\""""
new2 = """        if score > best_score:
            best_score = score
            best = text
            best_money = money
    # A line only becomes a hook if it actually contains a hook word.
    # Spike overlap + length alone (score 3) must NOT promote a garbled
    # line — that is how "I DID NOT GOT THROW GUYS" became a hook.
    if not best or not best_money:
        return "WAIT FOR IT\""""
assert old2 in s
s = s.replace(old2, new2, 1)
p.write_text(s)
print("hook gate fixed: money word required")
