"""Eligibility gate — the hard check that stands between a clip and
posting/submitting it to a campaign. Borderline = BLOCKED, never posted.

A clip passes ONLY when all three checks pass:
  (a) WINDOW: clip.vod_id == campaign.vod_id AND the clip's whole VOD
      time range [vod_start_s, vod_end_s] sits inside the campaign's
      eligible window [window_start_s, window_end_s]. window_end_s None
      means "to the end of the stream" (bounded by the VOD duration when
      known). A campaign with no parsed window_start_s can never pass.
  (b) CAPTION: every caption that will be posted (yt/tiktok/ig) contains
      all of campaign.required_mentions (case-insensitive), the
      campaign.required_hashtag (case-insensitive), and — when the clip
      names a destination — that destination string.
  (c) FULL-FRAME: the clip file is 1080x1920 AND is a blur-fill vertical
      (whole 16:9 frame visible), not a center crop. Verified by
      sampling frames: in a blur-fill the top/bottom bands are a blurred,
      darkened copy of the video, so their edge energy is far below the
      sharp center band. In a center crop the top band is as sharp as
      the center. If the check cannot be run or is inconclusive, the
      clip is BLOCKED (cannot verify = blocked).

Usage:
  gate_clip(clip, campaign) -> verdict dict
  python3 eligibility_gate.py --clip clip.json --campaign <id>
      [--campaigns campaigns.json]
  clip json: {"clip_id","vod_id","vod_start_s","vod_end_s",
              "caption_yt","caption_tiktok","caption_ig",
              "destination","clip30","tiktok"}
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FFPROBE = shutil.which("ffprobe") or "/home/abel/.local/bin/ffprobe"
FFMPEG = shutil.which("ffmpeg") or "/home/abel/.local/bin/ffmpeg"


def probe_dims(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60)
    parts = r.stdout.strip().split(",")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def probe_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def _band_energy(png_path):
    """Mean gradient energy of the top, center, and bottom bands of a
    1080x1920 frame. Returns (top, center, bottom) or None.

    Bands are chosen against the blur-fill layout (foreground is the
    whole 16:9 frame scaled to 1080x608, centered at rows 656-1264;
    rows 0-656 and 1264-1920 are blurred, darkened fill):
      top    rows 150-550   (fill zone; avoids the credit box at y~20
                            and the hook caption at y~110-280 while it
                            is visible — samples are taken at t>=5s,
                            after the 3s hook is gone)
      center rows 800-1200  (inside the sharp foreground)
      bottom rows 1400-1800 (fill zone)
    Measured Nov 16, 2026 on real clips (same Speed footage):
      true blur-fill:  top ~0.08, bottom ~0.6, center ~4.7
      center-crop:     top ~2.3,  bottom ~3.2, center ~4.7
    A gblur sigma=30 fill has essentially zero gradient (0.04-0.2);
    even the flattest sharp content (dark wall) stays above ~0.7.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png_path).convert("L")
    w, h = im.size
    if w < 200 or h < 400:
        return None
    px = im.load()

    def energy(y0, y1, x0=100, x1=980):
        total, n = 0.0, 0
        for y in range(y0, y1, 4):
            for x in range(x0, x1, 4):
                total += abs(px[x + 1, y] - px[x, y])
                total += abs(px[x, y + 1] - px[x, y])
                n += 1
        return total / max(n, 1)

    return (energy(150, 550), energy(800, 1200), energy(1400, 1800))


# Blur-fill decision thresholds (empirically calibrated Nov 16, 2026;
# see _band_energy docstring). Top band must be near-zero gradient;
# bottom band is looser (the blurred source bottom keeps some
# texture from on-screen banners); center must be real content.
TOP_MAX = 0.4
BOTTOM_MAX = 1.0
CENTER_MIN = 2.0


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def check_full_frame(path, sample_times=(5, 15, 25)):
    """Returns (ok, detail). ok is True only for proven blur-fill.

    Samples frames at t>=5s (after the 3s hook caption disappears, so
    hook text cannot inflate the top band) and requires the top and
    bottom bands to be blurred fill while the center band is sharp
    foreground. Anything else — including an inconclusive measurement
    — is a FAIL: cannot verify = blocked.
    """
    path = Path(path)
    if not path.exists():
        return False, "file missing: %s" % path
    dims = probe_dims(path)
    if dims != (1080, 1920):
        return False, "dimensions %s, expected (1080, 1920)" % (dims,)
    dur = probe_duration(path) or 30.0
    times = [t for t in sample_times if t < dur]
    if not times:
        times = [min(5.0, dur / 2)]
    tops, centers, bottoms = [], [], []
    with tempfile.TemporaryDirectory() as td:
        for t in times:
            png = str(Path(td) / ("f%d.png" % int(t)))
            r = subprocess.run(
                [FFMPEG, "-y", "-v", "error", "-ss", str(t), "-i", str(path),
                 "-frames:v", "1", png],
                capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                continue
            res = _band_energy(png)
            if res is None:
                return False, "PIL unavailable, cannot verify framing"
            tops.append(res[0])
            centers.append(res[1])
            bottoms.append(res[2])
    if not tops:
        return False, "no frames extracted"
    top, center, bottom = _median(tops), _median(centers), _median(bottoms)
    detail = ("bands top=%.2f center=%.2f bottom=%.2f over %d frames"
              % (top, center, bottom, len(tops)))
    if center < CENTER_MIN:
        return False, "no judgable frames (flat/black video?): " + detail
    if top < TOP_MAX and bottom < BOTTOM_MAX:
        return True, "blur-fill confirmed (" + detail + ")"
    return False, ("center-crop detected (" + detail + "; top/bottom "
                   "bands are sharp, not blurred fill)")


def _check_window(clip, campaign):
    vod_id = str(clip.get("vod_id") or "")
    if not vod_id or vod_id != str(campaign.get("vod_id") or ""):
        return False, ("vod mismatch: clip vod %s vs campaign vod %s"
                       % (vod_id, campaign.get("vod_id")))
    w_start = campaign.get("window_start_s")
    if w_start is None:
        return False, "campaign has no verified eligible window"
    w_end = campaign.get("window_end_s")
    start = clip.get("vod_start_s")
    end = clip.get("vod_end_s")
    if start is None or end is None:
        return False, "clip has no VOD time range recorded"
    if float(start) < float(w_start):
        return False, ("clip starts %.0fs, before window start %.0fs"
                       % (start, w_start))
    if w_end is not None and float(end) > float(w_end):
        return False, ("clip ends %.0fs, after window end %.0fs"
                       % (end, w_end))
    # Exclude ranges (e.g. stream-ending spikes with no campaign content).
    for ex0, ex1 in campaign.get("exclude_ranges") or []:
        if float(start) < float(ex1) and float(end) > float(ex0):
            return False, ("clip overlaps excluded range %.0fs-%.0fs"
                           % (ex0, ex1))
    return True, ("vod %s range %.0fs-%.0fs inside window %.0fs-%s"
                  % (vod_id, start, end, w_start,
                     ("%.0fs" % w_end) if w_end is not None else "end"))


def _check_caption(clip, campaign):
    mentions = [m.lower() for m in campaign.get("required_mentions") or []]
    hashtag = (campaign.get("required_hashtag") or "").lower()
    dest = clip.get("destination")
    problems = []
    for field in ("caption_yt", "caption_tiktok", "caption_ig"):
        cap = clip.get(field)
        if not cap:
            continue
        low = cap.lower()
        for m in mentions:
            if m not in low:
                problems.append("%s missing required mention %r"
                                % (field, m))
        if hashtag and hashtag not in low:
            problems.append("%s missing required hashtag %r"
                            % (field, hashtag))
        if dest and dest.lower() not in low:
            problems.append("%s missing destination %r" % (field, dest))
    if problems:
        return False, "; ".join(problems)
    return True, ("mentions %s, hashtag %s%s all present"
                  % (mentions, hashtag,
                     (", destination %r" % dest) if dest else ""))


def gate_clip(clip, campaign):
    """Full gate. Returns {"ok", "checks": {...}, "block_reason"}."""
    checks = {}
    ok_w, detail_w = _check_window(clip, campaign)
    checks["window"] = {"ok": ok_w, "detail": detail_w}
    ok_c, detail_c = _check_caption(clip, campaign)
    checks["caption"] = {"ok": ok_c, "detail": detail_c}
    files = [("clip30", clip.get("clip30"))]
    if clip.get("tiktok"):
        files.append(("tiktok", clip.get("tiktok")))
    framing_ok, framing_details = True, []
    for name, f in files:
        ok_f, detail_f = check_full_frame(f)
        framing_details.append("%s: %s" % (name, detail_f))
        framing_ok = framing_ok and ok_f
    checks["framing"] = {"ok": framing_ok,
                         "detail": "; ".join(framing_details)}
    ok = ok_w and ok_c and framing_ok
    failed = [k for k, v in checks.items() if not v["ok"]]
    return {
        "ok": ok,
        "checks": checks,
        "block_reason": (
            None if ok else
            "BLOCKED (%s): %s" % (
                ", ".join(failed),
                "; ".join(checks[k]["detail"] for k in failed))),
    }


if __name__ == "__main__":
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--clip", required=True, help="clip JSON file")
    ap.add_argument("--campaign", required=True, help="campaign id")
    ap.add_argument("--campaigns", default=str(HERE / "campaigns.json"))
    args = ap.parse_args()
    clip = json.loads(Path(args.clip).read_text())
    campaigns = json.loads(Path(args.campaigns).read_text())
    campaigns = campaigns.get("campaigns", campaigns)
    campaign = campaigns.get(args.campaign)
    if not campaign:
        print(json.dumps({"ok": False, "error": "campaign not found"}))
        sys.exit(1)
    verdict = gate_clip(clip, campaign)
    print(json.dumps(verdict, indent=2))
    sys.exit(0 if verdict["ok"] else 2)
