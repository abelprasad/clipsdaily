import sys, json
from pathlib import Path
from .vod import download_chat, find_spikes

VODS = [
    ("ishowspeed", "2928036561"),
    ("jynxzi", "2928767125"),
    ("stableronaldo", "2929115707"),
]
work = Path("/home/abel/clipsdaily/vod")
for channel, vid in VODS:
    chat = work / f"{vid}_chat.json"
    if not chat.exists():
        try:
            download_chat(vid, chat)
        except Exception as e:
            print(f"{channel} {vid}: CHAT FAIL {e}", flush=True)
            continue
    try:
        spikes = find_spikes(chat)
    except Exception as e:
        print(f"{channel} {vid}: SPIKE FAIL {e}", flush=True)
        continue
    print(f"== {channel} VOD {vid}: {len(spikes)} spikes ==", flush=True)
    for s in spikes[:6]:
        print(f"   @{s['seconds_in']}s intensity={s['intensity']}x msgs={s['messages']} median={s['median']}", flush=True)
    Path(f"/tmp/spikes_{channel}.json").write_text(json.dumps(spikes[:10]))
