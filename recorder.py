"""Recorder: streamlink records a channel the moment it goes live,
on any supported source platform. No account, no login for any of
these — streamlink resolves the public stream URL directly.

Supported platforms (proven Nov 15, 2026, all without any account):
  - twitch:  https://www.twitch.tv/<channel>
  - kick:    https://kick.com/<channel>
  - youtube: https://www.youtube.com/<@handle>/live, or a watch?v=<id> URL
  - tiktok:  https://www.tiktok.com/@<channel>/live
             (plugin exists; live resolution NOT proven — the three
             test channels were all offline at test time, and TikTok
             gives no public way to find a live channel to test against)
  - facebook: https://www.facebook.com/<channel>/live
              (plugin exists; live resolution NOT proven)
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Absolute path: ~/.local/bin is NOT on PATH in non-interactive shells,
# so bare "streamlink" silently fails and every live-check returns False.
# Found Nov 15, 2026 while testing launch-day live-checks.
import shutil
STREAMLINK = ("/home/abel/.local/bin/streamlink"
              if Path("/home/abel/.local/bin/streamlink").exists()
              else shutil.which("streamlink") or "streamlink")


def stream_url(platform, channel):
    """Public stream URL for a (platform, channel) pair."""
    if platform == "twitch":
        return f"https://www.twitch.tv/{channel}"
    if platform == "kick":
        return f"https://kick.com/{channel}"
    if platform == "youtube":
        if channel.startswith("http"):
            return channel
        if len(channel) == 11 and " " not in channel:
            return f"https://www.youtube.com/watch?v={channel}"
        handle = channel if channel.startswith("@") else f"@{channel}"
        return f"https://www.youtube.com/{handle}/live"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{channel}/live"
    if platform == "facebook":
        return f"https://www.facebook.com/{channel}/live"
    raise ValueError(f"unknown platform: {platform}")


def is_live(platform, channel):
    """True if the channel is live right now (streamlink resolves a
    playable stream). Works for offline channels too: returns False."""
    try:
        r = subprocess.run(
            [STREAMLINK, "--json", stream_url(platform, channel)],
            capture_output=True, text=True, timeout=45)
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        streams = data.get("streams") or {}
        return bool(streams)
    except Exception:
        return False


def record(platform, channel, out_path, quality="best"):
    """Block until the stream ends. Returns the subprocess exit code."""
    cmd = [STREAMLINK, stream_url(platform, channel), quality,
           "-o", str(out_path)]
    if platform == "twitch":
        cmd.append("--twitch-disable-ads")
    print(f"[recorder] {platform}/{channel} -> {out_path}", flush=True)
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    # Usage: recorder.py <platform> <channel> [out]
    platform = sys.argv[1] if len(sys.argv) > 1 else "twitch"
    channel = sys.argv[2] if len(sys.argv) > 2 else "xqc"
    out = sys.argv[3] if len(sys.argv) > 3 else str(
        HERE / "recordings" / f"{platform}_{channel}.ts")
    print("live:", is_live(platform, channel))
    if is_live(platform, channel):
        sys.exit(record(platform, channel, out))
