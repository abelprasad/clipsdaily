"""Chat spike detection for every supported source platform.

Shared rule everywhere: count chat messages in 10-second windows. A spike
is a window with at least 3x the median of the recent windows AND at least
spike_min_messages. Spikes are written as one JSON line each to
logs/spikes_<platform>_<channel>_<date>.jsonl with seconds-since-stream-
start, so cutter.py knows where to cut.

Monitors (all read-only, no account, no token, no login):
  - Twitch: anonymous IRC (justinfan login), same as before.
  - Kick: public Kick API to resolve the channel -> chatroom id, then a
    per-channel realtime config (POST, no auth) hands back a fresh Pusher
    app key + cluster. Subscribe to chatrooms.{id}.v2 and count
    ChatMessageEvent. The old hardcoded Pusher key died Oct 2026 (4001
    "not in this cluster"); the per-channel config is the working route,
    proven live Nov 15, 2026 (gaules, 55 msgs in 60s).
  - YouTube Live: yt-dlp downloads the live chat (no API key) while the
    stream runs; the monitor tails the growing file and counts
    addChatItemAction events. First 60s are warm-up (baseline only, no
    spikes) because yt-dlp dumps the chat replay buffer on start.
  - TikTok Live / Facebook Live: no feasible no-login chat reader.
    TikTok chat needs signed requests that break constantly; Facebook
    chat needs a page token. Those platforms are record-only
    (chat_source: none) — the runner still records them but cannot
    spike-detect, so no clips are cut from them.
"""
import json
import re
import socket
import statistics
import subprocess
import sys
import time
import uuid
from collections import deque
from datetime import date
import shutil
from pathlib import Path

import requests

from .paths import runtime_home
HERE = runtime_home()
YT_DLP = shutil.which("yt-dlp") or "yt-dlp"


def detect_spikes(counts, multiplier=3.0, min_messages=20, history=30):
    """Pure function, testable without any chat connection.
    counts = msgs per 10s window. Returns the index of each spike window."""
    spikes = []
    window = deque(maxlen=history)
    for i, c in enumerate(counts):
        if len(window) >= 5:
            med = statistics.median(window)
            if c >= max(multiplier * med, min_messages) and med > 0:
                spikes.append(i)
        window.append(c)
    return spikes


class SpikeTracker:
    """Live version of detect_spikes: feed one window count at a time,
    get a spike record (or None) back. Shared by all monitors."""

    def __init__(self, channel, platform, multiplier=3.0, min_messages=20,
                 window_seconds=10, warmup_windows=0):
        self.channel = channel
        self.platform = platform
        self.multiplier = multiplier
        self.min_messages = min_messages
        self.window_seconds = window_seconds
        self.warmup_windows = warmup_windows
        self.start = time.time()
        self.log = (HERE / "logs" /
                    f"spikes_{platform}_{channel}_{date.today().isoformat()}.jsonl")
        self.history = deque(maxlen=30)
        self.counts = []
        self._window_count = 0
        self._window_start = time.time()

    def bump(self, n=1):
        self._window_count += n

    def tick(self):
        """Call often; when a window closes, maybe emit a spike.
        Returns the spike record or None."""
        now = time.time()
        if now - self._window_start < self.window_seconds:
            return None
        c = self._window_count
        self._window_count = 0
        self._window_start = now
        self.counts.append(c)
        rec = None
        if len(self.counts) > self.warmup_windows and len(self.history) >= 5:
            med = statistics.median(self.history)
            if c >= max(self.multiplier * med, self.min_messages) and med > 0:
                rec = self._emit(c, med)
        self.history.append(c)
        return rec

    def _emit(self, count, median):
        seconds_in = time.time() - self.start
        rec = {"channel": self.channel, "platform": self.platform,
               "seconds_in": round(seconds_in, 1), "messages": count,
               "median": median,
               "intensity": round(count / median, 2) if median else 0,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(self.log, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[chat] SPIKE {self.platform}/{self.channel} @{seconds_in:.0f}s "
              f"({count} msgs, median {median})", flush=True)
        return rec


class TwitchChatMonitor:
    """Anonymous Twitch IRC. No account, no token."""

    def __init__(self, channel, multiplier=3.0, min_messages=20,
                 window_seconds=10):
        self.channel = channel.lower()
        self.tracker = SpikeTracker(channel, "twitch", multiplier,
                                    min_messages, window_seconds)
        self.log = self.tracker.log

    def run(self, stop_check=lambda: False):
        sock = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=30)
        sock.settimeout(5)
        sock.sendall(b"NICK justinfan12345\r\n")
        sock.sendall(f"JOIN #{self.channel}\r\n".encode())
        buf = ""
        while not stop_check():
            try:
                data = sock.recv(4096).decode("utf-8", "ignore")
            except socket.timeout:
                data = ""
            if not data:
                time.sleep(0.5)
                self.tracker.tick()
                continue
            buf += data
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                if line.startswith("PING"):
                    sock.sendall(b"PONG :tmi.twitch.tv\r\n")
                elif "PRIVMSG" in line:
                    self.tracker.bump()
            self.tracker.tick()
        sock.close()


# Backwards-compatible name (runner.py used to import ChatMonitor).
ChatMonitor = TwitchChatMonitor


def kick_channel_info(slug):
    """Public Kick API, no auth. Returns (channel_id, chatroom_id)."""
    r = requests.get(f"https://kick.com/api/v2/channels/{slug}",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.raise_for_status()
    d = r.json()
    return d["id"], d["chatroom"]["id"]


def kick_pusher_credentials(channel_id):
    """Per-channel realtime config, no auth. Kick rotates the Pusher app
    key; asking per channel returns the current one. Returns
    (app_key, cluster). Raises on failure."""
    r = requests.post(
        f"https://web.kick.com/api/v1/realtime/channels/{channel_id}/chat/connection",
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "application/json",
                 "Origin": "https://kick.com",
                 "Referer": "https://kick.com/"},
        json={"client": {"id": str(uuid.uuid4()), "type": "web"},
              "capabilities": {"accepted_providers": [{"provider": "pusher"}]}},
        timeout=15)
    r.raise_for_status()
    conns = (r.json().get("data") or {}).get("connections") or []
    pusher = next((c for c in conns if c.get("provider") == "pusher"),
                  conns[0] if conns else None)
    if not pusher:
        raise RuntimeError("Kick offered no Pusher connection")
    creds = pusher.get("credentials") or {}
    return creds["app_key"], creds["cluster"]


class KickChatMonitor:
    """Kick public chat via Pusher. No account, no token. Reconnects with
    a fresh per-channel config whenever Pusher refuses the key."""

    def __init__(self, channel, multiplier=3.0, min_messages=20,
                 window_seconds=10):
        self.channel = channel.lower()
        self.tracker = SpikeTracker(channel, "kick", multiplier,
                                    min_messages, window_seconds)
        self.log = self.tracker.log

    def _connect(self):
        import websocket
        channel_id, chatroom_id = kick_channel_info(self.channel)
        app_key, cluster = kick_pusher_credentials(channel_id)
        url = (f"wss://ws-{cluster}.pusher.com/app/{app_key}"
               "?protocol=7&client=js&version=7.6.0&flash=false")
        ws = websocket.create_connection(url, timeout=30)
        ws.send(json.dumps({
            "event": "pusher:subscribe",
            "data": {"auth": "",
                     "channel": f"chatrooms.{chatroom_id}.v2"}}))
        return ws

    def run(self, stop_check=lambda: False):
        import websocket
        while not stop_check():
            try:
                ws = self._connect()
            except Exception as e:
                print(f"[chat] kick connect failed ({self.channel}): {e}",
                      flush=True)
                time.sleep(10)
                continue
            ws.settimeout(5)
            try:
                while not stop_check():
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        self.tracker.tick()
                        continue
                    except Exception:
                        break
                    if not raw:
                        continue
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("event") == "App\\Events\\ChatMessageEvent":
                        self.tracker.bump()
                    self.tracker.tick()
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
            if not stop_check():
                print(f"[chat] kick socket dropped ({self.channel}), "
                      "reconnecting with fresh config", flush=True)
                time.sleep(5)


class YouTubeChatMonitor:
    """YouTube Live chat via yt-dlp, no API key. yt-dlp dumps the live
    chat (including a replay-buffer burst on start, hence the 60s
    warm-up) to a growing .live_chat.json file; we tail it and count
    addChatItemAction events per window."""

    def __init__(self, channel, multiplier=3.0, min_messages=20,
                 window_seconds=10, video_url=None):
        self.channel = channel
        self.video_url = video_url
        self.tracker = SpikeTracker(channel, "youtube", multiplier,
                                    min_messages, window_seconds,
                                    warmup_windows=6)
        self.log = self.tracker.log

    def _video_url(self):
        if self.video_url:
            return self.video_url
        ch = self.channel
        if ch.startswith("http"):
            return ch
        if len(ch) == 11 and " " not in ch:
            return f"https://www.youtube.com/watch?v={ch}"
        handle = ch if ch.startswith("@") else f"@{ch}"
        return f"https://www.youtube.com/{handle}/live"

    def run(self, stop_check=lambda: False):
        out_base = f"/tmp/ytchat_{self.channel.lstrip('@')}"
        cmd = [YT_DLP, "--skip-download", "--write-subs",
               "--sub-langs", "live_chat", "--sub-format", "json3",
               "-o", out_base, self._video_url()]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        chat_file = Path(out_base + ".live_chat.json")
        seen = 0
        try:
            while not stop_check():
                if proc.poll() is not None:
                    print(f"[chat] yt-dlp ended ({self.channel}), "
                          "restarting", flush=True)
                    time.sleep(5)
                    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
                    seen = 0
                    continue
                if chat_file.exists():
                    try:
                        data = chat_file.read_bytes()
                    except OSError:
                        data = b""
                    if len(data) > seen:
                        new = data[seen:]
                        seen = len(data)
                        self.tracker.bump(new.count(b"addChatItemAction"))
                self.tracker.tick()
                time.sleep(1)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


def make_monitor(platform, channel, config, video_url=None):
    """Factory. Returns a monitor instance or None for chat_source none
    (record-only platform). chat_source comes from the streamer entry,
    defaulting per platform."""
    defaults = {"twitch": "twitch_irc", "kick": "kick_api",
                "youtube": "youtube_ytdlp", "tiktok": "none",
                "facebook": "none"}
    source = defaults.get(platform, "none")
    if isinstance(config, dict) and config.get("chat_source"):
        source = config["chat_source"]
    if isinstance(config, dict):
        kw = {"multiplier": config.get("spike_threshold_multiplier", 3.0),
              "min_messages": config.get("spike_min_messages", 20),
              "window_seconds": config.get("spike_window_seconds", 10)}
    else:
        kw = {"multiplier": 3.0, "min_messages": 20, "window_seconds": 10}
    if source == "twitch_irc":
        return TwitchChatMonitor(channel, **kw)
    if source == "kick_api":
        return KickChatMonitor(channel, **kw)
    if source == "youtube_ytdlp":
        return YouTubeChatMonitor(channel, video_url=video_url, **kw)
    if source == "none":
        return None
    raise ValueError(f"unknown chat_source: {source}")


if __name__ == "__main__":
    # Usage: chat.py <platform> <channel> [video_url]
    platform = sys.argv[1] if len(sys.argv) > 1 else "twitch"
    channel = sys.argv[2] if len(sys.argv) > 2 else "xqc"
    video_url = sys.argv[3] if len(sys.argv) > 3 else None
    mon = make_monitor(platform, channel, {}, video_url=video_url)
    if mon is None:
        print(f"no chat monitor for {platform} (record-only)")
    else:
        mon.run()
