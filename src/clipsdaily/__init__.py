"""ClipForge (formerly ClipsDaily) — fully automatic Twitch/Kick clip pipeline.

Records live streams, finds chat spikes, cuts full-frame vertical clips,
and posts them to YouTube Shorts, TikTok, and Instagram Reels, with
campaign automation behind a strict eligibility gate.

The Python package keeps the import name `clipsdaily` (renaming every
import was not worth the churn); the product, CLI (`clipforge`), and
services are branded ClipForge via clipsdaily.branding.

Zero intervention after one-time setup: `clipforge setup` wires auth
and config, systemd units run every component, the watchdog restarts
dead units, and the dashboard at http://127.0.0.1:8787 shows state.
"""

__version__ = "0.2.0"
