import json
import subprocess
from pathlib import Path

HERE = Path("/home/abel/clipsdaily")
# 1. stop the maintainer (holds the old word-caption cutter in memory)
subprocess.run(["tmux", "kill-session", "-t", "clipsdaily-queue"],
               capture_output=True)
# 2. kill any stray cutters from that session
subprocess.run("pkill -f 'queue_seed.py'; pkill -f 'ishowspeed_40s_raw' ; sleep 2",
               shell=True, capture_output=True)
# 3. remove the one old-caption queue entry + its files
qfile = HERE / "queue" / "queue.json"
qfile.write_text("[]")
for f in (HERE / "queue" / "clips").glob("ishowspeed-2928036561-9805s_*"):
    f.unlink()
    print("deleted", f.name)
# 4. reset state so the maintainer re-cuts 9805 (new hook code) then 8785
sfile = HERE / "queue" / "state.json"
st = json.loads(sfile.read_text())
st["done_spikes"] = []
for v in st.get("vods", []):
    if v["channel"] == "ishowspeed":
        v["next"] = 0
sfile.write_text(json.dumps(st, indent=2))
print("state reset: ishowspeed next=0, done_spikes cleared")
# 5. restart the maintainer
subprocess.run(["tmux", "new-session", "-d", "-s", "clipsdaily-queue",
                "cd /home/abel/clipsdaily && python3 queue_seed.py --maintain "
                "2>&1 | tee -a logs/queue-20261115.log"], check=True)
print("maintainer restarted")
