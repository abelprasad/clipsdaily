"""Delete the 2 flawed live YouTube Shorts, then verify they're gone."""
import sys
from . import poster

IDS = ["UTEfAl0SGt0", "mqp_YZ-Eah8"]  # flawed Japan, flawed Hong Kong
yt = poster._yt_service()
for vid in IDS:
    try:
        yt.videos().delete(id=vid).execute()
        print(f"deleted {vid}", flush=True)
    except Exception as e:
        print(f"delete {vid} FAILED: {type(e).__name__}: {e}", flush=True)
# verify: videos().list should return no items for deleted ids
for vid in IDS:
    try:
        resp = yt.videos().list(part="id", id=vid).execute()
        items = resp.get("items", [])
        print(f"verify {vid}: {'GONE (0 items)' if not items else 'STILL THERE: ' + str(items)}", flush=True)
    except Exception as e:
        print(f"verify {vid} error: {type(e).__name__}: {e}", flush=True)
print("DELETE DONE", flush=True)
