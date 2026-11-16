#!/usr/bin/env python3
"""Regenerate the Star History chart snippet in README.md.

The chart itself is served live by star-history.com (it always shows
current data), so this script only keeps the snippet between the
<!-- STAR-HISTORY:START --> and <!-- STAR-HISTORY:END --> markers in
README.md up to date. Run it by hand or via the daily workflow
(.github/workflows/star-history.yml); it changes nothing when the
snippet is already current.

Usage: python3 scripts/gen_star_history.py [--check]
  --check: exit 1 if the snippet would change (CI mode).
"""
import sys
from pathlib import Path

REPO = "abelprasad/clipsdaily"
START = "<!-- STAR-HISTORY:START -->"
END = "<!-- STAR-HISTORY:END -->"

SNIPPET = (
    f"[![Star History Chart](https://api.star-history.com/svg?repos={REPO}&type=Date)]"
    f"(https://star-history.com/#{REPO}&Date)\n"
)


def main() -> int:
    readme = Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text()
    if START not in text or END not in text:
        print(f"README.md has no {START}..{END} markers — nothing to do")
        return 0
    before, rest = text.split(START, 1)
    _old, after = rest.split(END, 1)
    new = before + START + "\n" + SNIPPET + END + after
    if new == text:
        print("star history snippet already current")
        return 0
    if "--check" in sys.argv:
        print("star history snippet is stale")
        return 1
    readme.write_text(new)
    print("star history snippet updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
