# DEPRECATED (Nov 2026): one-time bootstrap for the flat-script layout.
# The repo is now a package (src/clipsdaily/ + pyproject.toml).
# Do NOT re-run. Use setup.sh (install) / deploy.sh (deploy).
#!/bin/bash
# Assemble the clipsdaily repo on indra. Run as abel.
# Copies (never moves, never edits) the live pipeline code into
# /home/abel/clipsdaily-repo, generates docs/PATHS.md, verifies,
# and makes the first commit. Does NOT touch the running pipeline
# and does NOT push anywhere.
set -e
REPO=/home/abel/clipsdaily-repo
LIVE=/home/abel/clipsdaily
cd "$REPO"

echo "== copy pipeline code from live dir (read-only) =="
cp "$LIVE"/*.py .
cp "$LIVE"/test_e2e.sh .
chmod +x test_e2e.sh setup.sh scripts/*.sh
echo "py files: $(ls *.py | wc -l)"

echo "== generate docs/PATHS.md table =="
python3 - <<'PYEOF'
import re
from pathlib import Path
repo = Path("/home/abel/clipsdaily-repo")
rows = []
portable = []
for p in sorted(repo.glob("*.py")):
    text = p.read_text(errors="replace")
    if "Path(__file__).resolve().parent" in text:
        portable.append(p.name)
    for i, line in enumerate(text.splitlines(), 1):
        if "/home/abel" in line:
            rows.append((p.name, i, line.strip()[:110]))
by_file = {}
for f, n, line in rows:
    by_file.setdefault(f, []).append((n, line))
out = []
out.append("### Files with hardcoded /home/abel paths")
out.append("")
out.append("| File | Lines | Example |")
out.append("|---|---|---|")
for f in sorted(by_file):
    lines = ", ".join(str(n) for n, _ in by_file[f][:6])
    ex = by_file[f][0][1].replace("|", "\\|")
    out.append(f"| `{f}` | {lines} | `{ex}` |")
out.append("")
out.append("### Files that resolve paths from their own location (portable)")
out.append("")
out.append("These use `Path(__file__).resolve().parent` and work wherever the repo is cloned:")
out.append("")
for f in portable:
    out.append(f"- `{f}`")
out.append("")
out.append("Full detail (every matching line):")
out.append("")
out.append("```")
for f, n, line in rows:
    out.append(f"{f}:{n}: {line}")
out.append("```")
table = "\n".join(out)
paths = repo / "docs" / "PATHS.md"
text = paths.read_text()
assert "<!-- GENERATED TABLE BELOW -->" in text, "PATHS.md marker missing"
paths.write_text(text.replace("<!-- GENERATED TABLE BELOW -->", table))
print(f"PATHS.md: {len(rows)} hardcoded-path lines in {len(by_file)} files; {len(portable)} portable files")
PYEOF

echo "== verify: compile all python =="
python3 -m compileall -q *.py && echo "compile OK"
rm -rf __pycache__

echo "== verify: no secrets =="
# Real credential VALUES (not mere references to filenames/env vars).
if grep -rniE "(api[_-]?key|client_secret|passwd|password)[\"']?\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}" --include="*.py" --include="*.sh" --include="*.md" --include="*.json" --include="*.txt" . | grep -v "CLIPSDAILY_IG_PASS\|<password>\|password from env\|password is read"; then
  echo "SECRET SCAN FAILED"; exit 1
fi
if grep -rniE "sessionid\s*=\s*['\"][^'\"]{10,}|sid_tt\s*=\s*['\"][^'\"]{10,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{10,}" --include="*.py" --include="*.sh" --include="*.md" --include="*.json" .; then
  echo "SECRET SCAN FAILED (cookie/token value)"; exit 1
fi
echo "secret scan OK (only filename/env-var references)"
echo "== verify: no forbidden items =="
for bad in .auth queue ig-outbox clips vod recordings logs campaign_work submit-outbox campaigns.json config.yaml; do
  if [ -e "$bad" ]; then echo "FORBIDDEN ITEM PRESENT: $bad"; exit 1; fi
done
find . -name "*.mp4" -o -name "*.srt" -o -name "*.log" | grep . && { echo "media/log files present"; exit 1; } || true
echo "forbidden-items check OK"

echo "== git init + first commit =="
git init -b main -q
git add -A
git status --short | head -5
git -c user.name="Abel Prasad" -c user.email="abelprasad4@gmail.com" commit -q -m "clipsdaily pipeline, portable repo (Nov 16, 2026)

Fully automatic Twitch/Kick/YouTube Live clip pipeline: live
recording, chat-spike cutting, full-frame vertical clips, hourly
posting to YouTube/TikTok/Instagram, campaign automation behind
a strict eligibility gate. Faithful copy of /home/abel/clipsdaily
plus operator scripts and docs. No credentials, no media, no
live state. See README.md and CLAUDE.md."
git log --oneline -1
echo "== tree =="
find . -type f -not -path "./.git/*" | sort
echo "== counts =="
echo "py: $(ls *.py | wc -l)  md: $(find . -name '*.md' -not -path './.git/*' | wc -l)  total files: $(find . -type f -not -path './.git/*' | wc -l)"
du -sh .
