import io, json, re, sys, traceback
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/abel/clipsdaily")
import poster

CLIPS = Path("/home/abel/clipsdaily/clips")
CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False}}
CHANNEL = "ishowspeed"
RESULTS = []

def now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

def run(label, fn, *args, **kwargs):
    buf = io.StringIO()
    started = now()
    try:
        with redirect_stdout(buf):
            ok = fn(*args, **kwargs)
        out = buf.getvalue()
        url = None
        m = re.search(r"https://youtube\.com/shorts/([A-Za-z0-9_-]+)", out)
        if m:
            url = m.group(0)
        RESULTS.append({"label": label, "ok": bool(ok), "url": url,
                        "posted_at": now(), "started_at": started,
                        "output_tail": out.strip().splitlines()[-3:]})
        print(f"[{label}] ok={bool(ok)} url={url} at {now()}", flush=True)
        return bool(ok)
    except Exception as e:
        out = buf.getvalue()
        RESULTS.append({"label": label, "ok": False, "url": None,
                        "posted_at": None, "started_at": started,
                        "error": f"{type(e).__name__}: {e}",
                        "output_tail": out.strip().splitlines()[-5:]})
        print(f"[{label}] FAILED {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return False

# a. Japan 30s -> YouTube
ok = run("yt_japan", poster.post_youtube,
         CLIPS / "speed-expedia-japan_30s.mp4", CHANNEL, CONFIG,
         caption="IShowSpeed surprises Hudson with a trip to Japan, thanks to Expedia. clipsdaily \u2022 ishowspeed\n#IShowSpeed #Expedia #ishowspeed #clipsdaily",
         title="IShowSpeed gives a fan a trip to Japan with Expedia | clipsdaily #shorts")
if not ok:
    print("STOP: YouTube Japan failed, aborting all", flush=True)
    print(json.dumps(RESULTS, indent=2)); sys.exit(1)

# b. Hong Kong 30s -> YouTube
ok = run("yt_hongkong", poster.post_youtube,
         CLIPS / "speed-expedia-hongkong_30s.mp4", CHANNEL, CONFIG,
         caption="IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong. clipsdaily \u2022 ishowspeed\n#IShowSpeed #Expedia #ishowspeed #clipsdaily",
         title="IShowSpeed gives a fan $10,000 from Expedia for Hong Kong | clipsdaily #shorts")
if not ok:
    print("STOP: YouTube Hong Kong failed, aborting TikTok", flush=True)
    print(json.dumps(RESULTS, indent=2)); sys.exit(1)

# c. Japan 70s -> TikTok (ONE attempt only; on failure stop TikTok)
ok = run("tt_japan", poster.post_tiktok,
         CLIPS / "speed-expedia-japan_tiktok70s.mp4", CHANNEL, CONFIG,
         caption="IShowSpeed surprises Hudson with a trip to Japan, thanks to Expedia #IShowSpeed #Expedia #ishowspeed #clipsdaily")
if not ok:
    print("STOP: TikTok failed once, no more TikTok attempts", flush=True)
    print(json.dumps(RESULTS, indent=2)); sys.exit(2)

# d. Hong Kong 90s -> TikTok
ok = run("tt_hongkong", poster.post_tiktok,
         CLIPS / "speed-expedia-hongkong_tiktok90s.mp4", CHANNEL, CONFIG,
         caption="IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong #IShowSpeed #Expedia #ishowspeed #clipsdaily")
print(json.dumps(RESULTS, indent=2))
print("DONE", flush=True)
sys.exit(0 if ok else 2)
