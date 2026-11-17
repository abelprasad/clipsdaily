"""Follow-up fix for hourly_poster.py: after a failed reconcile, do NOT
immediately re-upload in the same slot (the identical file would fail
the same way on TikTok's side). Wait for the next slot instead.

Run ON indra as abel:  python3 patch_poster2.py
"""
import shutil
from pathlib import Path

HERE = Path("/home/abel/clipsdaily")


def replace(path, old, new, name):
    text = path.read_text()
    n = text.count(old)
    assert n == 1, f"{path.name} :: {name}: matched {n}x (expected 1)"
    path.write_text(text.replace(old, new))
    print(f"patched {path.name}: {name}")


def main():
    hourly = HERE / "hourly_poster.py"
    shutil.copy2(hourly, str(hourly) + ".bak-20261116-ttapi2")
    replace(hourly, '''    tt_url = entry.get("tt_url") or ""
    if isinstance(tt_url, str) and tt_url.startswith(("PENDING:", "DRAFT:")):''',
            '''    tt_url = entry.get("tt_url") or ""
    reconciled_failed = False
    if isinstance(tt_url, str) and tt_url.startswith(("PENDING:", "DRAFT:")):''',
            "track reconciled_failed")
    replace(hourly, '''            elif res.get("status") == "failed":
                entry["tt_url"] = None
                entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                log(f"{entry['id']}: tiktok {kind} FAILED on TikTok "
                    f"({res.get('fail_reason', '')}) — retry "
                    f"{entry['tt_retries']}")''',
            '''            elif res.get("status") == "failed":
                entry["tt_url"] = None
                entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                # Do NOT re-upload in this same slot: the identical
                # file would fail the same way on TikTok's side.
                reconciled_failed = True
                log(f"{entry['id']}: tiktok {kind} FAILED on TikTok "
                    f"({res.get('fail_reason', '')}) — retry "
                    f"{entry['tt_retries']} next slot")''',
            "failed reconcile waits for next slot")
    replace(hourly, '''    if not entry.get("tt_url"):
        if entry.get("tt_retries", 0) >= MAX_RETRIES:''',
            '''    if not entry.get("tt_url") and not reconciled_failed:
        if entry.get("tt_retries", 0) >= MAX_RETRIES:''',
            "skip upload block after failed reconcile")
    print("ALL PATCHES APPLIED")


if __name__ == "__main__":
    main()
