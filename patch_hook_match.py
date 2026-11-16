from pathlib import Path
p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()
old = '''        low = text.lower()
        score = 0
        if any(w in low for w in HOOK_WORDS):
            score += 3'''
new = '''        low = text.lower()
        score = 0
        # Whole-word match only: substring matching let "no" fire inside
        # "not" and turned garbled lines into hooks.
        tokens = set(re.findall(r"[a-z0-9]+", low))
        if "$" in low or (HOOK_WORDS & tokens):
            score += 3'''
assert old in s
s = s.replace(old, new, 1)
old2 = '''HOOK_WORDS = {"win", "won", "winning", "trip", "japan", "hong", "kong",
              "$", "dollar", "dollars", "thousand", "give", "gave",
              "giving", "gift", "free", "insane", "crazy", "just",
              "watch", "look", "way", "god", "shot", "live",
              "oh", "no", "stop", "wait"}'''
new2 = '''HOOK_WORDS = {"win", "won", "winning", "trip", "japan", "hong", "kong",
              "dollar", "dollars", "thousand", "give", "gave",
              "giving", "gift", "free", "insane", "crazy", "just",
              "watch", "look", "way", "god", "shot", "live",
              "stop", "wait"}'''
assert old2 in s
s = s.replace(old2, new2, 1)
p.write_text(s)
print("hook matcher fixed: whole-word only")
