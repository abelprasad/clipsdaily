"""Sync the TikTok API build from the live pipeline into clipsdaily-repo
(dev copy) and apply the small doc edits. Does NOT commit — the caller
reviews `git status` / `git diff --stat` first, then commits separately.

Run ON indra as abel:  python3 sync_repo.py
"""
import shutil
from pathlib import Path

LIVE = Path("/home/abel/clipsdaily")
REPO = Path("/home/abel/clipsdaily-repo")

AUTO_SECTION = """
## Nov 16, 2026 — TikTok Content Posting API route (off by default)

- New module `tiktok_api.py`: official Content Posting API
  (open.tiktokapis.com) — OAuth (user.info.basic + video.upload +
  video.publish), Direct Post + draft mode, chunked FILE_UPLOAD,
  status polling, token refresh with rotation. No cookies, no
  Playwright. No live TikTok call has been made (no developer app
  exists yet); tested with mocks only.
- `poster.py`: `post_tiktok` routes to the API when `tiktok_api: true`
  in config.yaml, else the Playwright cookie path (unchanged). New
  `allow_short` flag keeps the hourly 30s fallback. `check_tiktok`
  reports the API token when a client file exists.
- `hourly_poster.py`: reads `tiktok_api`/`tiktok_api_mode` from
  config.yaml every slot (no restart to flip); PENDING:/DRAFT:
  publish_ids are reconciled next slot instead of re-uploaded; cap
  hits never burn a retry; a failed reconcile waits for next slot.
- Caps enforced in code: ~15 Direct Posts/day per creator (rolling
  24h counter in `.auth/tiktok_api_usage.json`), 5 pending drafts/24h.
- Full checklist + audit risk: `TIKTOK_API_SETUP.md`. Risk: TikTok
  says apps for private/personal use are not approved — the audit
  may refuse a one-account pipeline; fallbacks are draft mode (no
  audit) or a paid scheduler. App review also needs a website with
  Privacy Policy + Terms; clipsdaily has none yet.
- Tests: `test_tiktok_api.py` 24/24, `test_poster_tiktok_api.py`
  12/12 (both mocked, pass on indra).
"""


def replace(path, old, new, name):
    text = path.read_text()
    n = text.count(old)
    assert n == 1, f"{path} :: {name}: matched {n}x (expected 1)"
    path.write_text(text.replace(old, new))
    print(f"patched {path}: {name}")


def main():
    # 1. Setup doc into the live dir (transferred in with this script;
    # the patch's error message points here).
    assert (LIVE / "TIKTOK_API_SETUP.md").exists(), \
        "TIKTOK_API_SETUP.md missing from live dir"
    print("live: TIKTOK_API_SETUP.md present")

    # 2. Dated section on the live AUTOMATION.md.
    live_auto = LIVE / "AUTOMATION.md"
    if "TikTok Content Posting API route (off by default)" not in \
            live_auto.read_text():
        with open(live_auto, "a") as f:
            f.write(AUTO_SECTION)
        print("patched live AUTOMATION.md")

    # 3. Copy changed sources into the repo dev copy.
    for name in ("tiktok_api.py", "test_tiktok_api.py",
                 "test_poster_tiktok_api.py", "poster.py",
                 "hourly_poster.py"):
        shutil.copy2(LIVE / name, REPO / "src" / "clipsdaily" / name)
        print(f"synced src/clipsdaily/{name}")
    shutil.copy2(LIVE / "TIKTOK_API_SETUP.md",
                 REPO / "docs" / "TIKTOK_API_SETUP.md")
    print("synced docs/TIKTOK_API_SETUP.md")

    # 4. Config template: add the flags (platforms stay all-false here).
    replace(REPO / "config" / "config.yaml.example",
            """platforms:
  instagram: false
  tiktok: false
  youtube: false""",
            """platforms:
  instagram: false
  tiktok: false
  youtube: false

# TikTok Content Posting API (official, no cookies/Playwright).
# tiktok_api: false until the developer app is created, authorized,
# and audited (see docs/TIKTOK_API_SETUP.md). Flip to true only then.
# tiktok_api_mode: direct (publish straight to the profile) or draft
# (lands in the creator inbox; Abel taps publish on his phone).
# Caps are enforced in code: ~15 Direct Posts/day, 5 pending drafts/24h.
tiktok_api: false
tiktok_api_mode: direct""",
            "config example: tiktok_api flags")

    # 5. Pointer at the top of the TikTok notes doc.
    replace(REPO / "docs" / "TIKTOK.md",
            "# TikTok — session notes, blocked status, known bugs\n",
            "# TikTok — session notes, blocked status, known bugs\n"
            "\n"
            "## Content Posting API route (Nov 16, 2026) — see "
            "TIKTOK_API_SETUP.md\n"
            "\n"
            "The durable fix for the blocked cookie session is the "
            "official Content Posting API (`tiktok_api.py`, wired into "
            "`poster.py` / `hourly_poster.py`, off by default behind "
            "`tiktok_api: true`). No developer app exists yet, so no "
            "live call has been made. Risk: TikTok says apps for "
            "private/personal use are not approved — the audit may "
            "refuse a one-account pipeline; fallbacks are draft mode "
            "or a paid scheduler. App review also needs a website "
            "with Privacy Policy + Terms; clipsdaily has none yet.\n",
            "TIKTOK.md: API pointer")

    # 6. Same dated section on the repo's AUTOMATION.md.
    repo_auto = REPO / "docs" / "AUTOMATION.md"
    if "TikTok Content Posting API route (off by default)" not in \
            repo_auto.read_text():
        with open(repo_auto, "a") as f:
            f.write(AUTO_SECTION)
        print("patched repo docs/AUTOMATION.md")

    print("SYNC DONE — review git status before committing")


if __name__ == "__main__":
    main()
