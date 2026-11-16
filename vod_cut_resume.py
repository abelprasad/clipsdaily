import sys, json, subprocess, os
sys.path.insert(0, "/home/abel/clipsdaily")
from pathlib import Path
from cutter import make_clip, make_tiktok_clip

TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
WORK = Path("/home/abel/clipsdaily/vod")
OUT = Path("/home/abel/clipsdaily/clips/vod_batch")
OUT.mkdir(parents=True, exist_ok=True)

def hms(s):
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

def download_crop(vid, start, end, out):
    if out.exists() and out.stat().st_size > 1000000:
        print(f"[crop] exists {out}", flush=True); return out
    cmd = [TDCLI, "videodownload", "--id", vid, "-o", str(out),
           "--quality", "1080p60", "--collision", "overwrite",
           "-b", hms(start), "-e", hms(end)]
    print(f"[crop] {vid} {hms(start)}-{hms(end)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"videodownload failed: {r.stderr[-400:]}")
    return out

def uniq(clip_path, channel, spike, suffix=""):
    dest = Path(clip_path).parent / f"{channel}_{int(spike)}s{suffix}.mp4"
    if Path(clip_path) != dest:
        os.replace(clip_path, dest)
    return dest

# RESUME: only the items the first run did not finish (SSH broke at 21:00).
# Done already: speed 9805 30s + tiktok(39s), speed 8785 30s,
# jynxzi 2075 30s + tiktok(75s).
PLAN = [
    ("jynxzi", "2928767125", 23305, [
        (22605, 8.92, "THE WORLDS FINAL JUST ENDED")]),
    ("stableronaldo", "2929115707", 5582, [
        (2785, 3.7, "RONALDO JUST HIT 40K VIEWERS"),
        (5115, 4.0, "RONALDO JUST BEAT PUNCH-OUT")]),
]

results = []
for channel, vid, dur, spikes in PLAN:
    for i, (spike, inten, hook) in enumerate(spikes):
        end = min(dur, spike + 120)
        start = max(0, end - 160)
        local = float(spike - start)
        crop = WORK / f"{vid}_{int(spike)}_crop.mp4"
        try:
            download_crop(vid, start, end, crop)
        except Exception as e:
            print(f"{channel} @{spike}: CROP FAIL {e}", flush=True)
            continue
        try:
            clip = make_clip(crop, local, channel, clip_seconds=30, model="small", hook=hook, out_dir=OUT)
            clip = uniq(clip, channel, spike)
            print(f"[done] 30s {clip} hook={hook!r}", flush=True)
            results.append({"channel": channel, "vod": vid, "spike": spike,
                            "intensity": inten, "hook": hook, "clip30": str(clip)})
        except Exception as e:
            print(f"{channel} @{spike}: CUT30 FAIL {e}", flush=True)
            continue
        if channel == "stableronaldo" and i == 0:
            try:
                tt, method = make_tiktok_clip(crop, [{"seconds_in": local, "intensity": inten}],
                                              channel, model="small", hook=hook, out_dir=OUT)
                if tt:
                    tt = uniq(tt, channel, spike, suffix="_tiktok")
                    print(f"[done] tiktok {tt} method={method}", flush=True)
                    results[-1]["tiktok"] = str(tt)
                    results[-1]["tiktok_method"] = method
                else:
                    print(f"[done] tiktok None method={method}", flush=True)
            except Exception as e:
                print(f"{channel} @{spike}: TIKTOK FAIL {e}", flush=True)
        crop.unlink(missing_ok=True)

Path("/tmp/vod_cut_resume_results.json").write_text(json.dumps(results, indent=2))
print(f"[batch-resume] {len(results)} clips cut", flush=True)
for r in results:
    print(json.dumps(r), flush=True)
