import io, json, re, sys, traceback
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from . import poster
CLIPS = Path("/home/abel/clipsdaily/clips")
CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False}}
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
        RESULTS.append({"label": label, "ok": bool(ok), "posted_at": now(),
                        "started_at": started, "output_tail": out.strip().splitlines()[-3:]})
        print(f"[{label}] ok={bool(ok)} at {now()}", flush=True)
        return bool(ok)
    except Exception as e:
        out = buf.getvalue()
        RESULTS.append({"label": label, "ok": False, "posted_at": None,
                        "started_at": started, "error": f"{type(e).__name__}: {e}",
                        "output_tail": out.strip().splitlines()[-5:]})
        print(f"[{label}] FAILED {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return False

ok = run("tt_japan", poster.post_tiktok,
         CLIPS / "speed-expedia-japan_tiktok70s.mp4", "ishowspeed", CONFIG,
         caption="IShowSpeed surprises Hudson with a trip to Japan, thanks to Expedia #IShowSpeed #Expedia #ishowspeed #clipsdaily")
if not ok:
    print("STOP: TikTok failed, no more TikTok attempts", flush=True)
    print(json.dumps(RESULTS, indent=2)); sys.exit(2)
ok = run("tt_hongkong", poster.post_tiktok,
         CLIPS / "speed-expedia-hongkong_tiktok90s.mp4", "ishowspeed", CONFIG,
         caption="IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong #IShowSpeed #Expedia #ishowspeed #clipsdaily")
print(json.dumps(RESULTS, indent=2))
print("DONE", flush=True)
sys.exit(0 if ok else 2)
